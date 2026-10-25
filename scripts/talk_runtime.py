"""TALK统一启动入口：持有API/宿主Popen，配置worker随同就绪，角色仍按页面意图启停。"""
from __future__ import annotations
import argparse
import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import role_service_host as rsh
from scripts.role_provision import key_file_path
from scripts.role_provision_worker import RoleProvisionWorker
from scripts.role_service_recovery import recorded_process_state


class RuntimeErrorCode(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def process_parents():
    """Read only PID ancestry (never command lines or credentials)."""
    if os.name!="nt":
        return {}
    import ctypes
    from ctypes import wintypes as w
    class Entry(ctypes.Structure):
        _fields_=[("dwSize",w.DWORD),("cntUsage",w.DWORD),("pid",w.DWORD),
            ("heap",ctypes.c_size_t),("module",w.DWORD),("threads",w.DWORD),
            ("parent",w.DWORD),("priority",w.LONG),("flags",w.DWORD),("exe",w.WCHAR*260)]
    k=ctypes.WinDLL("kernel32",use_last_error=True)
    k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];k.CreateToolhelp32Snapshot.restype=w.HANDLE
    k.Process32FirstW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)];k.Process32FirstW.restype=w.BOOL
    k.Process32NextW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)];k.Process32NextW.restype=w.BOOL
    k.CloseHandle.argtypes=[w.HANDLE];k.CloseHandle.restype=w.BOOL
    handle=k.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value:
        return {}
    try:
        row=Entry();row.dwSize=ctypes.sizeof(row);parents={}
        more=k.Process32FirstW(handle,ctypes.byref(row))
        while more:
            parents[row.pid]=row.parent
            more=k.Process32NextW(handle,ctypes.byref(row))
        return parents
    finally:
        k.CloseHandle(handle)


def is_owned_descendant(original_pid, reported_pid, parents):
    """Windows venv redirectors have a separate interpreter PID; retain original Popen."""
    seen=set()
    while isinstance(reported_pid,int) and reported_pid>0 and reported_pid not in seen:
        if reported_pid==original_pid:return True
        seen.add(reported_pid);reported_pid=parents.get(reported_pid)
    return False


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config,dict) or config.get("schema") != "talk-runtime-config-1" or config.get("version") != 1 or not isinstance(config.get("project_id"),str) or not config["project_id"].strip():
        raise RuntimeErrorCode("runtime_config_invalid")
    url = urlparse(config.get("base_url", ""))
    if url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost") or url.username or url.password or url.query or url.fragment or url.path not in ("","/"):
        raise RuntimeErrorCode("runtime_loopback_required")
    for key in ("project_root", "operator_key_file", "key_root", "state_dir"):
        if not isinstance(config.get(key), str) or not Path(config[key]).is_absolute():
            raise RuntimeErrorCode("runtime_path_invalid")
    if not Path(config["project_root"]).is_dir():
        raise RuntimeErrorCode("runtime_project_missing")
    if any(Path(config[k]).resolve().is_relative_to(Path(config["project_root"]).resolve()) for k in ("key_root","operator_key_file")):
        raise RuntimeErrorCode("runtime_key_root_inside_project")
    specs = config.get("hosts", [])
    if not isinstance(specs, list) or any(not isinstance(s,dict) or not isinstance(s.get("member_id"),str) or not s["member_id"].strip() for s in specs) or len({s.get("member_id") for s in specs}) != len(specs):
        raise RuntimeErrorCode("runtime_host_config_invalid")
    commands = [config.get("api_argv")] + [s.get("argv") for s in specs]
    for argv in commands:
        if not isinstance(argv, list) or not argv or any(not isinstance(v, str) or not v for v in argv):
            raise RuntimeErrorCode("runtime_argv_invalid")
        if not Path(argv[0]).is_absolute() or not Path(argv[0]).is_file() or any(v.split("=",1)[0] in ("--key", "--api-key", "--operator-key") for v in argv):
            raise RuntimeErrorCode("runtime_argv_invalid")
    for spec in specs:
        if not spec.get("member_id") or not all(Path(spec.get(k, "")).is_absolute() for k in ("health_file", "drain_file")):
            raise RuntimeErrorCode("runtime_host_config_invalid")
        if not all(Path(spec[k]).resolve().is_relative_to(Path(config["state_dir"]).resolve()) for k in ("health_file", "drain_file")):
            raise RuntimeErrorCode("runtime_host_path_escape")
    if "{control_file}" not in config["api_argv"]:
        raise RuntimeErrorCode("runtime_api_control_required")
    recipe=config.get("workbuddy")
    if recipe is not None and (not isinstance(recipe,dict) or any(not isinstance(recipe.get(k),str) or not Path(recipe[k]).is_absolute() for k in ("executable","models_home")) or not isinstance(recipe.get("key_files",{}),dict)):
        raise RuntimeErrorCode("runtime_workbuddy_config_invalid")
    return config


@contextlib.contextmanager
def launcher_lock(private):
    """OS锁随原进程退出释放；不依赖健康文件PID，也不接管其它进程。"""
    handle=(private/"launcher.lock").open("a+b")
    try:
        handle.seek(0,2)
        if handle.tell()==0:
            handle.write(b"0");handle.flush()
        handle.seek(0)
        try:
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeErrorCode("runtime_already_running") from exc
        yield
    finally:
        handle.close()


class TalkRuntime:
    def __init__(self, config, *, client=None, spawn=None, clock=time.monotonic, sleeper=time.sleep, attach_api=False, diagnostics=None, config_path=None):
        self.config = config
        self.config_path = Path(config_path) if config_path else None
        self.project = config["project_id"]
        self.project_root = Path(config["project_root"])
        self.private = Path(config["state_dir"]) / "runtime"
        self.client = client
        self.spawn_override = spawn
        self.clock, self.sleep = clock, sleeper
        self.api = None
        self.attach_api = attach_api
        self.api_control_file = None
        self.hosts = {}
        self.statuses = {}
        self.worker = None
        self.worker_thread = None
        self.worker_error = None
        self.worker_completed_at = None
        self.activation_id = uuid.uuid4().hex
        self.startup_client = client
        self.startup_thread = None
        self.startup_state = "pending"
        self.startup_attempts = 0
        self.startup_next = 0.0
        self.startup_error = None
        self.stopping = False
        self.started_at = utcnow()
        self.operator = None
        self.failures = {}
        self.diagnostics = diagnostics or {}
        self._backend_state = None
        self._backend_seen = 0.0

    def event(self, event, *, context=None, exc=None, component="runtime"):
        journal = self.diagnostics.get(component)
        if journal:
            journal.emit(event, context=context, exc=exc)

    def request(self, method, path, body=None):
        return self.client.request(method, path, body)

    def roles(self):
        result = self.request("GET", f"/api/projects/{self.project}/roles")
        return result.get("data", []) if isinstance(result, dict) else result

    def spawn(self, label, argv):
        if self.spawn_override:
            return self.spawn_override(label, argv)
        with (self.private / (label + ".out")).open("ab") as stdout, (self.private / (label + ".err")).open("ab") as stderr:
            return subprocess.Popen(argv, cwd=self.project_root, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                startupinfo=rsh._hidden_startupinfo(), **({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}))

    def health(self, state="running"):
        if self._backend_state != state or time.monotonic()-self._backend_seen >= 30:
            event = "backend_stopped" if state == "stopped" else "backend_heartbeat"
            self.event(event, context={"stage": "serve", "state": state})
            self._backend_state, self._backend_seen = state, time.monotonic()
        value = {"schema":"talk-runtime-health-1", "pid":os.getpid(), "started_at":self.started_at,
            "project_id":self.project, "activation_id":self.activation_id,
            "startup_state":self.startup_state, "startup_attempts":self.startup_attempts,
            "startup_error":self.startup_error,
            "seen_at":utcnow(), "state":state, "stopping":self.stopping,
            "child_pid":self.api.pid if self.api else None,
            "owns_original_popen":self.api is not None, "automatic_restart":False,
            "api_mode":"external" if self.attach_api else "owned",
            "hosts":self.statuses, "worker_in_flight":bool((self.worker_thread and self.worker_thread.is_alive())
                or (self.startup_thread and self.startup_thread.is_alive())),
            "worker_error":self.worker_error}
        value["worker_completed_at"]=self.worker_completed_at
        try:
            rsh._publish_private_bytes(self.private / "health.json", json.dumps(value).encode())
        except (OSError, rsh.HostError):
            print("runtime_health_write_failed",file=sys.stderr)
        if self.api:
            compatibility = {"launcher_pid":os.getpid(),"child_pid":self.api.pid,
                "child_created_epoch":rsh.process_creation_time(self.api.pid),"state":state,
                "at_utc":utcnow(),"owns_original_popen":True,"automatic_restart":False}
            try:
                rsh._publish_private_bytes(Path(self.config["state_dir"]) / "api-service" / "health.json", json.dumps(compatibility).encode())
            except (OSError, rsh.HostError):
                print("runtime_api_health_write_failed",file=sys.stderr)

    def start_api(self):
        parsed = urlparse(self.config["base_url"])
        with socket.socket() as s:
            s.settimeout(.2)
            if s.connect_ex((parsed.hostname, parsed.port or 80)) == 0:
                raise RuntimeErrorCode("runtime_api_already_running")
        self.api_control_file = self.private / ("api-"+uuid.uuid4().hex+".stop")
        self.api = self.spawn("api", [str(self.api_control_file) if a=="{control_file}" else a for a in self.config["api_argv"]])

    def wait_api(self, seconds=30):
        deadline = self.clock() + seconds
        while self.clock() < deadline:
            if self.api is not None and self.api.poll() is not None:
                raise RuntimeErrorCode("runtime_api_exited")
            try:
                me = self.request("GET", "/api/members/me")
                if me.get("kind") != "human":
                    raise RuntimeErrorCode("runtime_operator_not_human")
                return
            except rsh.HostError:
                self.sleep(.25)
        raise RuntimeErrorCode("runtime_api_not_ready")

    def worker_tick(self):
        if self.stopping or self.worker is None or (self.worker_thread and self.worker_thread.is_alive()):
            return
        def run():
            try:
                self.worker.run_round()
                self.worker_error = None
                self.worker_completed_at = utcnow()
            except Exception as exc:
                # Only type/code goes into health; no HTTP body/Key/exception text.
                self.worker_error = getattr(exc, "code", None) or type(exc).__name__
                self.event("worker_exception", component="provision_worker", context={"stage": "serve", "error_code": self.worker_error}, exc=exc)
        self.worker_thread = threading.Thread(target=run, name="talk-provision", daemon=True)
        self.worker_thread.start()

    def startup_tick(self):
        """One bounded HTTP round off the health loop; never replay a completed boot."""
        if (self.stopping or self.startup_state in ("complete","failed")
                or (self.startup_thread and self.startup_thread.is_alive()) or self.clock()<self.startup_next):
            return
        if self.startup_attempts>=8:
            self.startup_state="failed"
            self.startup_error=self.startup_error or "startup_round_limit"
            return
        self.startup_attempts+=1
        self.startup_state="processing"
        def run():
            delay=5
            try:
                result=self.startup_client.request("POST",f"/api/projects/{self.project}/role-services/startup",
                    {"activation_id":self.activation_id})
                if (isinstance(result,dict) and result.get("activation_id")==self.activation_id
                        and result.get("complete") is True):
                    self.startup_state="complete";self.startup_error=None
                else:
                    self.startup_state="pending"
                    retry=result.get("retry_after_seconds") if isinstance(result,dict) else None
                    if type(retry) is int:delay=max(5,min(120,retry))
            except Exception as exc:
                self.startup_state="pending"
                # HostError codes are local stable codes; never copy an HTTP body.
                self.startup_error=type(exc).__name__
                delay=min(30,5*2**min(self.startup_attempts-1,3))
            finally:
                self.startup_next=self.clock()+delay
        self.startup_thread=threading.Thread(target=run,name="talk-project-startup",daemon=True)
        self.startup_thread.start()

    def workbuddy_spec(self, role):
        recipe = self.config.get("workbuddy")
        if not recipe or role.get("archived") or role.get("binding_state") != "bound" or role.get("runner", {}).get("runtime") != "workbuddy":
            return None
        member = role["member_id"]
        key = Path(recipe.get("key_files", {}).get(member) or key_file_path(Path(self.config["key_root"]), member))
        if not key.is_file():
            self.statuses[member] = {"state":"key_not_configured"}
            return None
        identity = self.client.request("GET", "/api/members/me", key=key.read_text(encoding="utf-8").strip())
        if identity.get("id") != member or identity.get("kind") != "agent":
            self.statuses[member] = {"state":"identity_mismatch"}
            return None
        private = Path(self.config["state_dir"]) / "workbuddy-native" / rsh._sanitize_token(self.project) / rsh._sanitize_token(member)
        argv = [sys.executable,"-B","-X","utf8","-m","scripts.workbuddy_role_host","serve",
            "--project",self.project,"--member",member,"--state-dir",self.config["state_dir"],
            "--project-root",str(self.project_root),"--base-url",self.config["base_url"],
            "--workbuddy-executable",recipe["executable"],"--workbuddy-models-home",recipe["models_home"],
            "--workbuddy-display-name",identity["display_name"],"--role-key-file",str(key),
            "--operator-key-file",self.config["operator_key_file"],"--runtime-verified","workbuddy","--apply"]
        return {"member_id":member,"argv":argv,"health_file":str(private/"manager-health.json"),"drain_file":str(private/"drain.request")}

    def reconcile_hosts(self, roles):
        parents=process_parents()
        by_id = {r["member_id"]:r for r in roles}
        specs = {s["member_id"]:dict(s) for s in self.config.get("hosts", [])}
        for role in roles:
            if role["member_id"] not in specs:
                try:
                    spec = self.workbuddy_spec(role)
                except (rsh.HostError,OSError,ValueError):
                    self.statuses[role["member_id"]]={"state":"identity_check_failed"}
                    continue
                if spec:
                    specs[spec["member_id"]] = spec
        for member, spec in specs.items():
            role = by_id.get(member)
            if role is None or role.get("archived"):
                continue
            owned = self.hosts.get(member)
            if owned:
                if owned["process"].poll() is None:
                    state="starting"
                    try:
                        facts=json.loads(Path(spec["health_file"]).read_text(encoding="utf-8"))
                        seen=rsh._parse_iso(facts.get("seen_at"))
                        if is_owned_descendant(owned["process"].pid,facts.get("pid"),parents) and facts.get("state")=="serving" and seen and (datetime.now(timezone.utc)-seen).total_seconds()<30:
                            state="serving"
                        else:
                            state="manager_unverified"
                    except (OSError,ValueError):
                        pass
                    self.statuses[member] = {"state":state,"pid":owned["process"].pid}
                    if state=="serving":self.statuses[member]["interpreter_pid"]=facts["pid"]
                    continue
                # An exited manager never grants adoption of its previous native children.
                self.event("host_exited", context={"member_id": member, "returncode": owned["process"].poll(), "outcome": "failed"})
                self.hosts.pop(member)
                prior = self.failures.get(member,{"count":0})
                self.failures[member] = {"count":prior["count"]+1,"generation":(role.get("service") or {}).get("generation"),"retry_at":self.clock()+min(30,2**(prior["count"]+1))}
            service = role.get("service") or {}
            failures = self.failures.get(member)
            if failures and failures["generation"] != service.get("generation"):
                self.failures.pop(member); failures = None
            if failures and (failures["count"]>=3 or self.clock()<failures["retry_at"]):
                self.statuses[member] = {"state":"manager_failed","attempts":failures["count"]}
                continue
            existing = None
            health = Path(spec["health_file"])
            if health.is_file():
                try:
                    existing = json.loads(health.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    self.statuses[member] = {"state":"health_unreadable"}
                    continue
            if existing:
                process_state=recorded_process_state(existing.get("pid"), existing.get("seen_at"))
                if process_state not in ("absent","exited","previous_boot","pid_reused"):
                    self.statuses[member] = {"state":"external_manager" if process_state=="present" else "external_manager_unverified","pid":existing.get("pid")}
                    continue
            if service.get("ownership_held"):
                self.statuses[member] = {"state":"recovery_required"}
                continue
            if Path(spec["drain_file"]).exists():
                self.statuses[member] = {"state":"drain_marker_present"}
                continue
            try:
                process = self.spawn("host-"+rsh._sanitize_token(member), spec["argv"])
            except OSError as exc:
                self.event("host_start_failed", context={"member_id": member, "stage": "startup"}, exc=exc)
                count=self.failures.get(member,{"count":0})["count"]+1
                self.failures[member]={"count":count,"generation":service.get("generation"),"retry_at":self.clock()+min(30,2**count)}
                self.statuses[member]={"state":"manager_failed","attempts":count}
                continue
            self.hosts[member] = {"process":process,"spec":spec}
            self.statuses[member] = {"state":"starting","pid":process.pid}
            self.event("host_started", context={"member_id": member, "child_pid": process.pid, "stage": "startup"})

    def reconcile_deletions(self, roles):
        from scripts.role_delete import cleanup
        from urllib.parse import quote
        for role in roles:
            deletion = role.get("deletion") or {}
            if deletion.get("status") not in ("pending", "cleaning"):
                continue
            expiry = rsh._parse_iso(deletion.get("lease_expires_at"))
            if deletion.get("status") == "cleaning" and expiry and expiry > datetime.now(timezone.utc):
                continue
            member = role["member_id"]
            base = f"/api/projects/{quote(self.project,safe='')}/roles/{quote(member,safe='')}/deletion"
            receipt = self.request("POST", base+"/claim", {"revision":deletion["revision"]})
            project = self.request("GET", f"/api/projects/{quote(self.project,safe='')}")
            registered = project.get("project_root_path")
            import hashlib
            digest = hashlib.sha256(json.dumps(self.config,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
            if not registered or Path(registered).resolve() != self.project_root.resolve() or receipt.get("cleanup_config_digest") != digest:
                from scripts.role_delete import STEPS
                result = {"outcome":"failed", "steps":{step:"failed" if step=="manager" else "pending" for step in STEPS},
                          "error_code":"local_runtime_required" if not receipt.get("cleanup_config_digest") else "runtime_config_changed"}
            else:
                result = cleanup(self, member, receipt)
            self.request("POST", base+"/report", {"lease_token":receipt["lease_token"],
                "revision":receipt["revision"], **result})
            break  # One bounded cleanup per tick; roles/API/worker remain responsive.

    def reload_api(self):
        if self.api is None:
            raise RuntimeErrorCode("runtime_api_not_owned")
        self._stop_api()
        self.start_api()
        self.wait_api()
        # Existing hosts/Popen owners deliberately remain untouched.

    def _stop_api(self):
        if self.api and self.api.poll() is None:
            if self.api_control_file is None:
                raise RuntimeErrorCode("runtime_api_control_missing")
            self.api_control_file.write_text("talk-runtime-stop\n",encoding="utf-8")
            try:
                self.api.wait(timeout=30)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeErrorCode("runtime_api_stop_timeout") from exc
            if self.api_control_file.read_text(encoding="utf-8")=="talk-runtime-stop\n":
                self.api_control_file.unlink()

    def stop(self):
        self.stopping = True
        self.health("stopping")  # Invalidates the startup writer before awaiting its request.
        self.event("backend_stopping", context={"stage": "shutdown"})
        if self.startup_thread and self.startup_thread.is_alive():
            self.startup_thread.join(timeout=70)
            if self.startup_thread.is_alive():
                raise RuntimeErrorCode("runtime_startup_stop_timeout")
        if self.worker:
            self.worker.request_stop()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=130)
            if self.worker_thread.is_alive():
                raise RuntimeErrorCode("runtime_worker_stop_timeout")
        for member, owned in self.hosts.items():
            if owned["process"].poll() is None:
                # Human-authenticated ordinary stop; the original manager verifies its Popen.
                roles = {r["member_id"]:r for r in self.roles()}
                service = roles.get(member, {}).get("service") or {}
                if service.get("can_stop"):
                    self.request("POST", f"/api/projects/{self.project}/roles/{member}/service/stop")
        deadline = self.clock() + 90
        while self.clock() < deadline:
            roles = {r["member_id"]:r for r in self.roles()}
            waiting = [member for member in self.hosts if roles.get(member, {}).get("service", {}).get("ownership_held")]
            if not waiting:
                break
            self.sleep(.5)
        else:
            raise RuntimeErrorCode("runtime_role_stop_timeout")
        for owned in self.hosts.values():
            if owned["process"].poll() is not None:
                marker=Path(owned["spec"]["drain_file"])
                if owned.get("drain_marker_written") and marker.is_file() and marker.read_text(encoding="utf-8")=="talk-runtime-stop\n":
                    marker.unlink()
                continue
            health = json.loads(Path(owned["spec"]["health_file"]).read_text(encoding="utf-8"))
            if health.get("owned_launches"):
                deadline = self.clock() + 10
                while health.get("owned_launches") and self.clock() < deadline:
                    self.sleep(.25)
                    health = json.loads(Path(owned["spec"]["health_file"]).read_text(encoding="utf-8"))
                if health.get("owned_launches"):
                    raise RuntimeErrorCode("runtime_manager_not_drained")
            marker = Path(owned["spec"]["drain_file"])
            if marker.exists() and not owned.get("drain_marker_written"):
                raise RuntimeErrorCode("runtime_existing_drain_marker")
            if not owned.get("drain_marker_written"):
                marker.write_text("talk-runtime-stop\n",encoding="utf-8")
                owned["drain_marker_written"]=True
            try:
                owned["process"].wait(timeout=25)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeErrorCode("runtime_host_stop_timeout") from exc
            if marker.read_text(encoding="utf-8") == "talk-runtime-stop\n":
                marker.unlink()
        self._stop_api()
        self.health("stopped")

    def serve(self):
        if not self.diagnostics:
            from bridges.backend_diagnostics import runtime_journals
            self.diagnostics = runtime_journals(self.project_root, self.project)
        self.event("backend_starting", context={"stage": "startup"})
        try:
            self._serve()
        except BaseException as exc:
            self.event("backend_failed", context={"stage": "shutdown" if self.stopping else "startup",
                "error_code": getattr(exc, "code", None)}, exc=exc)
            raise
        finally:
            for journal in self.diagnostics.values():
                journal.close()

    def _serve(self):
        rsh.ensure_private_dir(self.private)
        rsh.ensure_private_dir(Path(self.config["state_dir"])/"api-service")
        self.operator = Path(self.config["operator_key_file"]).read_text(encoding="utf-8").strip()
        for journal in self.diagnostics.values():
            journal.secrets = (*journal.secrets, self.operator)
        self.client = self.client or rsh.TalkHostClient(self.config["base_url"],self.operator,timeout=5)
        self.startup_client = self.startup_client or rsh.TalkHostClient(self.config["base_url"],self.operator,timeout=65)
        try:
            if not self.attach_api:
                self.start_api()
            self.health("waiting_api")
            self.wait_api()
            if self.config.get("provision_worker", True):
                self.event("backend_starting", component="provision_worker", context={"stage": "startup"})
                self.worker = RoleProvisionWorker(project_id=self.project,host_label=self.config.get("host") or socket.gethostname(),
                    project_root=self.project_root,key_root=Path(self.config["key_root"]),operator_key=self.operator,
                    base_url=self.config["base_url"],enabled=True,apply=True,timeout_seconds=5,io_budget_seconds=120,
                    cli_executable=self.config.get("provision_cli_executable"), diagnostics=self.diagnostics.get("provision_worker"))
                self.event("backend_ready", component="provision_worker", context={"stage": "startup"})
            self.event("backend_ready", context={"stage": "startup"})
        except Exception as exc:
            self.event("backend_failed", context={"stage": "startup", "error_code": getattr(exc, "code", None)}, exc=exc)
            # Startup has not created a manager yet; close only our API child.
            self._stop_api()
            self.health("startup_failed")
            raise
        while not self.stopping:
            if (self.private/"stop.request").exists():
                break
            reload_file = self.private/"reload-api.request"
            if reload_file.exists():
                try:
                    self.reload_api()
                    reload_file.unlink()
                except (RuntimeErrorCode,rsh.HostError,OSError) as exc:
                    self.worker_error=getattr(exc,"code",None) or type(exc).__name__
                    self.event("runtime_exception", context={"stage": "serve", "error_code": self.worker_error}, exc=exc)
            if self.api is not None and self.api.poll() is not None:
                # Keep every original host Popen alive. A user reload can restore API;
                # this is deliberately not unbounded role/API auto-restart.
                self.health("api_exited")
                self.sleep(2)
                continue
            try:
                self.health()
                self.startup_tick()
                # Keep the old manager evidence intact until cold-boot recovery
                # has finished. Provisioning can also create replacement hosts.
                self.health()
                if self.startup_state not in ("complete","failed") or (self.startup_thread and self.startup_thread.is_alive()):
                    self.sleep(2)
                    continue
                self.worker_tick()
                roles = self.roles()
                self.reconcile_deletions(roles)
                self.reconcile_hosts(roles)
            except (rsh.HostError, OSError, ValueError) as exc:
                self.worker_error = getattr(exc, "code", None) or type(exc).__name__
                self.event("runtime_exception", context={"stage": "serve", "error_code": self.worker_error}, exc=exc)
            self.health()
            self.sleep(2)
        self.health("stopping")
        while True:
            try:
                if self.api is not None and self.api.poll() is not None:
                    self.reload_api()
                self.stop()
                break
            except (RuntimeErrorCode,rsh.HostError,OSError,ValueError) as exc:
                # A failed shutdown must never abandon the original owners.
                self.worker_error=getattr(exc,"code",None) or type(exc).__name__
                self.event("runtime_exception", context={"stage": "shutdown", "error_code": self.worker_error}, exc=exc)
                self.health("stop_blocked")
                self.sleep(2)
        self.event("backend_stopped", component="provision_worker", context={"stage": "shutdown"})


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["serve","stop","reload-api","status"],nargs="?",default="serve")
    parser.add_argument("--config",required=True)
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--detach",action="store_true")
    parser.add_argument("--attach-api",action="store_true",help="只运行本机宿主/worker，观察已由其它入口启动的API，不接管或关闭API")
    args=parser.parse_args(argv)
    config=load_config(args.config)
    private=Path(config["state_dir"])/"runtime"
    if args.action=="status":
        value=json.loads((private/"health.json").read_text(encoding="utf-8"))
        value["process_state"]=recorded_process_state(value["pid"],value.get("seen_at"))
        value["process_present"]=value["process_state"]=="present"
        print(json.dumps(value,ensure_ascii=False));return 0
    if not args.apply:
        print(json.dumps({"mode":"dry_run","action":args.action,"project_id":config["project_id"],"configured_hosts":len(config.get("hosts",[])),"workbuddy_dynamic":bool(config.get("workbuddy"))}));return 0
    rsh.ensure_private_dir(private)
    if args.action in ("stop","reload-api"):
        health=json.loads((private/"health.json").read_text(encoding="utf-8"))
        if recorded_process_state(health["pid"],health.get("seen_at"))!="present":raise RuntimeErrorCode("runtime_not_running")
        if args.action=="reload-api" and health.get("api_mode")=="external":raise RuntimeErrorCode("runtime_api_not_owned")
        (private/("stop.request" if args.action=="stop" else "reload-api.request")).write_text(utcnow(),encoding="utf-8")
        return 0
    health_file=private/"health.json"
    # PID可能在电脑重启后复用；单实例由下方OS锁证明，旧健康PID不能阻止恢复。
    stop_file=private/"stop.request"
    if stop_file.exists():
        if not health_file.exists() or json.loads(health_file.read_text(encoding="utf-8")).get("state")!="stopped":raise RuntimeErrorCode("runtime_stop_marker_requires_review")
        stop_file.unlink()
    if args.detach:
        command=[sys.executable,"-B","-X","utf8","-m","scripts.talk_runtime","serve","--config",str(Path(args.config).resolve()),"--apply"]
        if args.attach_api:command.append("--attach-api")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW | subprocess.CREATE_BREAKAWAY_FROM_JOB if os.name=="nt" else 0
        with (private/"launcher.out").open("ab") as out,(private/"launcher.err").open("ab") as err:
            child=subprocess.Popen(command,cwd=config["project_root"],stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                **({"creationflags":flags,"startupinfo":rsh._hidden_startupinfo()} if os.name=="nt" else {"start_new_session":True}))
        print(json.dumps({"started_launcher_pid":child.pid,"note":"Check status for actual readiness."}));return 0
    if not args.attach_api:
        from server.local_runtime import bind_local_runtime
        bind_local_runtime(args.config, config)
    runtime=TalkRuntime(config,attach_api=args.attach_api,config_path=Path(args.config).resolve())
    def stopping(*_):runtime.stopping=True
    signal.signal(signal.SIGINT,stopping)
    if hasattr(signal,"SIGBREAK"):signal.signal(signal.SIGBREAK,stopping)
    with launcher_lock(private):
        runtime.serve()
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (RuntimeErrorCode,rsh.HostError) as exc:
        print(json.dumps({"ok":False,"error_code":getattr(exc,"code",None) or str(exc)}))
        raise SystemExit(1)
