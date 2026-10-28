"""本次角色准备进程的私有回执；先核验并停止旧进程，再允许新进程。

只管理本次授权自建进程组，不扫描或接管其他角色、对话或运行器服务。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import signal
import tempfile
import time
import uuid

from scripts import role_service_host as host
from scripts.role_provision import release_lock


class ProcessError(RuntimeError):
    pass


_owned = {}


class _WindowsAuthorizationJob:
    """仅包含本次授权入口及其子进程；控制器退出时由内核清理。"""
    def __init__(self, generation, *, open_existing=False):
        class Basic(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),
                ('flags',wintypes.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),
                ('active_limit',wintypes.DWORD),('affinity',ctypes.c_size_t),
                ('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_=[(name,ctypes.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
        class Limits(ctypes.Structure):
            _fields_=[('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),
                ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        k=self.kernel
        k.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];k.CreateJobObjectW.restype=wintypes.HANDLE
        k.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        k.SetInformationJobObject.restype=wintypes.BOOL
        k.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];k.AssignProcessToJobObject.restype=wintypes.BOOL
        k.TerminateJobObject.argtypes=[wintypes.HANDLE,wintypes.UINT];k.TerminateJobObject.restype=wintypes.BOOL
        k.QueryInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p]
        k.QueryInformationJobObject.restype=wintypes.BOOL
        k.CloseHandle.argtypes=[wintypes.HANDLE]
        name='Local\\TALK-native-setup-'+generation
        if open_existing:
            k.OpenJobObjectW.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR]
            k.OpenJobObjectW.restype=wintypes.HANDLE
            self.handle=k.OpenJobObjectW(0x0004|0x0008,False,name)
            if not self.handle and ctypes.get_last_error()!=2:
                raise ProcessError('native_previous_process_unverified')
            return
        self.handle=k.CreateJobObjectW(None,name)
        if self.handle and ctypes.get_last_error()==183:
            self.close();raise ProcessError('native_process_scope_unavailable')
        limits=Limits();limits.basic.flags=0x2000
        if not self.handle or not k.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            self.close();raise ProcessError('native_process_scope_unavailable')

    def attach_and_resume(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle,int(process._handle)):
            raise ProcessError('native_process_scope_unavailable')
        # Popen关闭了CreateProcess返回的线程句柄；只恢复本次挂起入口的初始线程。
        class ThreadEntry(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('thread',wintypes.DWORD),
                ('owner',wintypes.DWORD),('priority',wintypes.LONG),('delta',wintypes.LONG),('flags',wintypes.DWORD)]
        k=self.kernel
        k.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD];k.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
        k.Thread32First.argtypes=[wintypes.HANDLE,ctypes.POINTER(ThreadEntry)];k.Thread32First.restype=wintypes.BOOL
        k.Thread32Next.argtypes=[wintypes.HANDLE,ctypes.POINTER(ThreadEntry)];k.Thread32Next.restype=wintypes.BOOL
        k.OpenThread.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenThread.restype=wintypes.HANDLE
        k.ResumeThread.argtypes=[wintypes.HANDLE];k.ResumeThread.restype=wintypes.DWORD
        snapshot=k.CreateToolhelp32Snapshot(4,0)
        if snapshot in (None,ctypes.c_void_p(-1).value):
            raise ProcessError('native_process_scope_unavailable')
        try:
            entry=ThreadEntry();entry.size=ctypes.sizeof(entry)
            found=k.Thread32First(snapshot,ctypes.byref(entry))
            while found:
                if entry.owner==process.pid:
                    thread=k.OpenThread(2,False,entry.thread)
                    if not thread:
                        break
                    try:
                        if k.ResumeThread(thread)==1:
                            return
                    finally:
                        k.CloseHandle(thread)
                    break
                found=k.Thread32Next(snapshot,ctypes.byref(entry))
        finally:
            k.CloseHandle(snapshot)
        raise ProcessError('native_process_scope_unavailable')

    def empty(self):
        class Accounting(ctypes.Structure):
            _fields_=[('user',ctypes.c_longlong),('kernel',ctypes.c_longlong),
                ('period_user',ctypes.c_longlong),('period_kernel',ctypes.c_longlong),
                ('faults',wintypes.DWORD),('total',wintypes.DWORD),('active',wintypes.DWORD),('terminated',wintypes.DWORD)]
        value=Accounting()
        if not self.kernel.QueryInformationJobObject(self.handle,1,ctypes.byref(value),ctypes.sizeof(value),None):
            raise ProcessError('native_previous_process_stop_unconfirmed')
        return value.active==0

    def stop(self):
        if not self.kernel.TerminateJobObject(self.handle,1):
            raise ProcessError('native_previous_process_stop_unconfirmed')
        self.wait_empty(5)

    def wait_empty(self, timeout):
        deadline=time.monotonic()+timeout
        while not self.empty():
            if time.monotonic()>=deadline:
                raise ProcessError('native_previous_process_stop_unconfirmed')
            time.sleep(.01)

    def close(self):
        if getattr(self,'handle',None):
            self.kernel.CloseHandle(self.handle);self.handle=None


class _OwnedProcess:
    def __init__(self, process, job, created_at):
        self.process,self.job,self.created_at=process,job,created_at
    def __getattr__(self,name):
        return getattr(self.process,name)
    def poll(self):
        result=self.process.poll()
        return result if result is not None and (self.job.handle is None or self.job.empty()) else None
    def wait(self,timeout=None):
        result=self.process.wait(timeout=timeout)
        if self.job.handle is not None:self.job.wait_empty(5 if timeout is None else timeout)
        return result
    def terminate(self):
        self.job.stop()
    kill=terminate


def _path(home):
    return host.assert_inside_root(Path(home), Path('native-setup-process.json'))


def _read(home, project, member):
    path = _path(home)
    if not path.exists():
        return None
    if host._is_reparse_point(path) or not path.is_file() or path.stat().st_size > 16384:
        raise ProcessError('native_previous_process_unverified')
    value = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(value, dict) or value.get('schema') != 'talk-native-setup-process-1'
            or value.get('project_id') != project or value.get('member_id') != member
            or value.get('lock_name', 'kimi-role-setup') not in ('kimi-role-setup', 'codex-role-setup')
            or not isinstance(value.get('generation'), str) or len(value['generation'])!=32
            or any(c not in '0123456789abcdef' for c in value['generation'])):
        raise ProcessError('native_previous_process_unverified')
    return value


def _write(home, value):
    path = _path(home)
    raw = (json.dumps(value, ensure_ascii=False) + '\n').encode('utf-8')
    temporary = None
    try:
        if os.name == 'nt':
            temporary = host._windows_publish_temp_file(path, raw)
        else:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def stop_recorded_process(pid, created_at):
    """使用同一内核句柄核对创建时间、停止和等待，拒绝PID复用。"""
    if type(pid) is not int or pid <= 0 or type(created_at) not in (int, float) or not math.isfinite(created_at):
        raise ProcessError('native_previous_process_unverified')
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.c_void_p] * 4
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateProcess.restype = wintypes.BOOL
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        handle = kernel.OpenProcess(0x100000 | 0x1000 | 0x0001, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return
            raise ProcessError('native_previous_process_unverified')
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise ProcessError('native_previous_process_unverified')
            if code.value != 259:
                return
            times = [ctypes.c_ulonglong() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                raise ProcessError('native_previous_process_unverified')
            actual = times[0].value / 10000000.0 - 11644473600.0
            if abs(actual - created_at) > 0.000001:
                raise ProcessError('native_previous_process_identity_changed')
            if not kernel.TerminateProcess(handle, 1) or kernel.WaitForSingleObject(handle, 5000) != 0:
                raise ProcessError('native_previous_process_stop_unconfirmed')
        finally:
            kernel.CloseHandle(handle)
        return
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise ProcessError('native_previous_process_unverified')
    try:
        handle = os.pidfd_open(pid)
    except ProcessLookupError:
        return
    try:
        actual = host.process_creation_time(pid)
        if actual is None or abs(actual - created_at) > 0.1:
            raise ProcessError('native_previous_process_identity_changed')
        signal.pidfd_send_signal(handle, signal.SIGTERM)
        import select
        poller = select.poll()
        poller.register(handle, select.POLLIN)
        if not poller.poll(5000):
            signal.pidfd_send_signal(handle, signal.SIGKILL)
            if not poller.poll(5000):
                raise ProcessError('native_previous_process_stop_unconfirmed')
    finally:
        os.close(handle)


def stop_previous(home, project, member):
    record = _read(home, project, member)
    if record is None:
        return
    if record.get('state') != 'exited':
        owned=_owned.get(record['generation'])
        if owned is not None:
            if record.get('pid') != owned.pid or record.get('created_at') != owned.created_at:
                raise ProcessError('native_previous_process_identity_changed')
            owned.terminate();owned.wait(timeout=5)
        else:
            job=_WindowsAuthorizationJob(record['generation'],open_existing=True) if os.name=='nt' and record.get('job_scope') is True else None
            try:
                if job is not None and job.handle is not None:
                    job.stop()
                else:
                    stop_recorded_process(record.get('pid'), record.get('created_at'))
            finally:
                if job is not None:job.close()
    # 只正常释放该授权回执记录的锁代次，不清其它锁或猜测归属。
    token = record.get('lock_token')
    if isinstance(token, str) and token:
        from scripts.role_provision import lock_path_for
        name = record.get('lock_name', 'kimi-role-setup')
        if name not in ('kimi-role-setup', 'codex-role-setup'):
            raise ProcessError('native_previous_process_unverified')
        release_lock(lock_path_for(Path(home) / name), {'token': token})
    _path(home).unlink(missing_ok=True)
    owned=_owned.pop(record['generation'],None)
    if owned is not None:
        owned.job.close()


def spawn_recorded(home, project, member, lock, spawn, *, lock_name='kimi-role-setup'):
    if lock_name not in ('kimi-role-setup', 'codex-role-setup'):
        raise ProcessError('native_process_identity_unverified')
    generation = uuid.uuid4().hex
    record = {'schema': 'talk-native-setup-process-1', 'project_id': project,
              'member_id': member, 'generation': generation, 'state': 'launching',
              'pid': None, 'created_at': None, 'lock_token': lock.get('token'), 'lock_name': lock_name}
    _write(home, record)
    job=None
    try:
        job=_WindowsAuthorizationJob(generation) if os.name=='nt' else None
        process = spawn(4 if job is not None else 0)  # CREATE_SUSPENDED：入Job后才允许执行。
    except Exception:
        if job is not None:job.close()
        record['state'] = 'exited'
        _write(home, record)
        raise
    try:
        created = host.process_creation_time(process.pid)
        if created is None:
            raise ProcessError('native_process_identity_unverified')
        record.update(state='running', pid=process.pid, created_at=created, job_scope=job is not None)
        _write(home, record)
        if job is not None:
            job.attach_and_resume(process)
            process=_OwnedProcess(process,job,created)
            _owned[generation]=process
        return process, generation
    except Exception:
        if job is not None:job.close()
        process.terminate()
        process.wait(timeout=5)
        record['state'] = 'exited'
        _write(home, record)
        raise


def finish_record(home, project, member, generation, process):
    if process.poll() is None:
        raise ProcessError('native_previous_process_stop_unconfirmed')
    record = _read(home, project, member)
    if record is not None and record['generation'] == generation:
        _path(home).unlink(missing_ok=True)
    owned=_owned.pop(generation,None)
    if owned is not None:owned.job.close()
