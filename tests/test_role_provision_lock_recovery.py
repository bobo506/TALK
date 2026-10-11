# -*- coding: utf-8 -*-
"""R1-2 定向补正（TALK #221）：H2 锁原子发布/中断恢复 + H3 guard 链接保护。

覆盖范围
--------
- H2：可见锁记录改为**原子发布**（完整记录写临时文件 → flush+fsync → ``os.link``）。
  真实受控子进程在 record-write / flush / before-publish / after-publish / after-reclaim
  各边界被终止后，同路径重试都能完成且最多一个 owner；本协议自己残留的发布临时文件在
  下一次持守卫时按 pid 清理；旧协议/未知来源的不可解析锁仍 fail closed（不按年龄抢占）。
- H3：新增 ``<lock>.guard`` 与可见锁一并纳入「自身/祖先/声明根」链接保护，任何
  open/write 之前拒绝 reparse point（真实 junction 证明 + 文件符号链接形状的定序证明）。

全部用例使用隔离临时文件树与受控子进程，只终止本测试自己 ``Popen`` 得到的进程；
Windows 下 junction 用 ``mklink /J`` 创建并只用 ``rmdir`` 摘除，绝不跟随递归删除。
本机不具备创建**文件**符号链接的权限（WinError 1314），因此文件符号链接形状用
受控的 ``_is_reparse_point`` 注入验证定序，并在报告里如实标注 not_run 的真实能力限制。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(ROOT), str(ROOT / "scripts")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import role_provision as rp  # noqa: E402

# Windows venv 的 python.exe 可能是另起解释器的启动器。固定文本子进程只用
# 标准库和仓库模块，直接使用同版本的基础解释器，使 Popen 控制实际锁 owner。
CHILD_PYTHON = (
    getattr(sys, "_base_executable", sys.executable)
    if os.name == "nt"
    else sys.executable
)

#: 与 role_provision 内部命名保持一致的发布临时文件后缀（测试断言用）。
LOCK_TEMP_SUFFIX = rp.LOCK_PUBLISH_TEMP_SUFFIX


def _wait_for_marker(marker: Path, proc: subprocess.Popen, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if marker.exists():
            return True
        if proc.poll() is not None:
            return False
        time.sleep(0.02)
    return marker.exists()


# ══════════════════════════════════════════════════════════════════════
# H2：原子发布各边界的真实中断与恢复
# ══════════════════════════════════════════════════════════════════════

_BOUNDARY_CHILD = r'''
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import role_provision as rp

boundary = sys.argv[2]
lock = Path(sys.argv[3])
marker = Path(sys.argv[4])


def pause(tag):
    marker.write_text(tag, encoding="utf-8")
    while True:
        time.sleep(0.02)


if boundary == "record-write":
    class Paused:
        def __init__(self, fd, mode, **kwargs):
            self.fd = fd

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def write(self, content):
            pause("record-write")

    rp.os.fdopen = Paused
elif boundary == "flush":
    def slow_fsync(fd):
        pause("flush")

    rp.os.fsync = slow_fsync
elif boundary == "before-publish":
    def slow_link(src, dst, **kwargs):
        pause("before-publish")

    rp.os.link = slow_link
elif boundary == "after-publish":
    real_link = rp.os.link

    def link_then_pause(src, dst, **kwargs):
        result = real_link(src, dst, **kwargs)
        pause("after-publish")
        return result

    rp.os.link = link_then_pause
elif boundary == "after-reclaim":
    real_remove = rp.os.remove

    def remove_then_pause(path):
        result = real_remove(path)
        pause("after-reclaim")
        return result

    rp.os.remove = remove_then_pause
else:
    raise SystemExit(4)

handle = rp.acquire_lock(lock, 0)
marker.write_text("acquired:" + handle["token"], encoding="utf-8")
'''

_CONTENDER_CHILD = r'''
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import role_provision as rp

base = Path(sys.argv[2])
name = sys.argv[3]
peers = sys.argv[4].split(",")
lock = base / "target.lock"
(base / ("ready-" + name)).write_text("1", encoding="utf-8")
deadline = time.time() + 30
while not all((base / ("ready-" + peer)).exists() for peer in peers):
    if time.time() > deadline:
        raise SystemExit(3)
    time.sleep(0.01)
result = {"name": name}
handle = None
try:
    handle = rp.acquire_lock(lock, 0)
    result.update(
        {"acquired": True, "token": handle["token"], "reclaimed": handle["reclaimed"]}
    )
except rp.ProvisionError as exc:
    result.update({"acquired": False, "code": exc.code})
(base / ("result-" + name + ".json")).write_text(
    json.dumps(result), encoding="utf-8"
)
if handle is not None:
    deadline = time.time() + 30
    while not (base / "release").exists() and time.time() < deadline:
        time.sleep(0.02)
    rp.release_lock(lock, handle)
'''


class _LockCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-lock-recovery-"))
        self.addCleanup(lambda: shutil.rmtree(self._tmp, ignore_errors=True))
        self.procs: list[subprocess.Popen] = []

    def tearDown(self) -> None:
        (self._tmp / "release").write_text("1", encoding="utf-8")
        for proc in self.procs:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:  # pragma: no cover - 兜底清理
                    pass

    def _spawn(self, code: str, *args: str, log_name: str = "child.log") -> subprocess.Popen:
        log = (self._tmp / log_name).open("w", encoding="utf-8")
        self.addCleanup(log.close)
        proc = subprocess.Popen(
            [CHILD_PYTHON, "-c", code, str(ROOT / "scripts"), *args],
            stdout=log,
            stderr=log,
            cwd=str(ROOT),
        )
        self.procs.append(proc)
        return proc

    def _kill_and_confirm_dead(self, proc: subprocess.Popen) -> None:
        proc.kill()
        proc.wait(timeout=15)
        deadline = time.time() + 15
        while time.time() < deadline and rp._process_is_alive(proc.pid) is not False:
            time.sleep(0.05)
        self.assertIs(rp._process_is_alive(proc.pid), False)

    def _write_dead_lock(self, lock: Path) -> int:
        dead = subprocess.Popen(
            [CHILD_PYTHON, "-c", "pass"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        dead.wait(timeout=10)
        self.assertIs(rp._process_is_alive(dead.pid), False)
        lock.write_text(
            json.dumps(
                {
                    "schema": rp.LOCK_SCHEMA,
                    "token": "recovery-dead-token",
                    "pid": dead.pid,
                    "started_at": "2000-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        old = 1_000_000.0
        os.utime(lock, (old, old))
        return dead.pid

    def _temp_files(self, lock: Path) -> list[Path]:
        return sorted(
            lock.parent.glob(
                f"{lock.name}{rp.LOCK_PUBLISH_MARKER}*{rp.LOCK_PUBLISH_TEMP_SUFFIX}"
            )
        )


class LockAtomicPublishTests(_LockCase):
    def test_each_publish_boundary_interruption_then_retry_completes(self):
        """record-write/flush/before-publish/after-publish/after-reclaim 各边界。"""
        expectations = {
            "record-write": False,
            "flush": False,
            "before-publish": False,
            "after-publish": True,
            "after-reclaim": False,
        }
        for boundary, visible_after_crash in expectations.items():
            with self.subTest(boundary=boundary):
                case_dir = self._tmp / boundary
                case_dir.mkdir()
                lock = case_dir / "target.lock"
                marker = case_dir / "marker"
                if boundary == "after-reclaim":
                    self._write_dead_lock(lock)

                proc = self._spawn(
                    _BOUNDARY_CHILD,
                    boundary,
                    str(lock),
                    str(marker),
                    log_name=f"{boundary}.log",
                )
                self.assertTrue(
                    _wait_for_marker(marker, proc),
                    f"{boundary}: 受控子进程未到达边界",
                )
                self.assertEqual(marker.read_text(encoding="utf-8"), boundary)
                self._kill_and_confirm_dead(proc)

                # 协议不变式：可见锁要么不存在，要么就是完整记录（绝不 0 字节）。
                if lock.exists():
                    record = rp._read_lock_record(lock)
                    self.assertIsNotNone(
                        record, f"{boundary}: 中断后留下了半截可见锁 {lock.stat().st_size}B"
                    )
                    self.assertEqual(record.get("pid"), proc.pid)
                self.assertEqual(
                    lock.exists(),
                    visible_after_crash,
                    f"{boundary}: 中断后可见锁存在性与预期不符",
                )

                # 死 owner 的守卫由 OS 释放后，同路径重试必须完成。
                if lock.exists():
                    old = 1_000_000.0
                    os.utime(lock, (old, old))
                handle = rp.acquire_lock(lock, 0)
                try:
                    record = json.loads(lock.read_text(encoding="utf-8"))
                    self.assertEqual(record["schema"], rp.LOCK_SCHEMA)
                    self.assertEqual(record["token"], handle["token"])
                    self.assertEqual(record["pid"], os.getpid())
                    self.assertEqual(handle["reclaimed"], visible_after_crash)
                finally:
                    self.assertTrue(rp.release_lock(lock, handle))
                self.assertFalse(lock.exists())
                # 本协议自己残留的发布临时文件已被清理，永久守卫不被删除。
                self.assertEqual(self._temp_files(lock), [])
                guard = rp.lock_guard_path_for(lock)
                self.assertTrue(guard.exists())
                self.assertFalse(rp._is_reparse_point(guard))
                self.assertGreaterEqual(guard.stat().st_size, 1)

    def test_legacy_unparseable_lock_fails_closed_without_stealing(self):
        """旧协议 0 字节/坏 JSON 残留：明确 fail closed，不按年龄/内容抢占。"""
        for label, payload in (("zero-byte", b""), ("broken-json", b"{not-json")):
            with self.subTest(label=label):
                case_dir = self._tmp / f"legacy-{label}"
                case_dir.mkdir()
                lock = case_dir / "target.lock"
                lock.write_bytes(payload)
                old = 1_000_000.0
                os.utime(lock, (old, old))

                with self.assertRaises(rp.ProvisionError) as ctx:
                    rp.acquire_lock(lock, 0)
                self.assertEqual(ctx.exception.code, "provision_lock_busy")
                self.assertIn("不可解析", ctx.exception.detail)
                self.assertEqual(lock.read_bytes(), payload)

                # 守卫本身可再次获取：busy 来自显式 fail closed，不是守卫卡死。
                fd = rp._lock_guard_acquire(lock)
                self.assertIsNotNone(fd)
                rp._lock_guard_release(fd)

    def test_dead_publisher_temp_is_swept_but_live_publisher_temp_is_kept(self):
        dead = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        dead.wait(timeout=10)
        self.assertIs(rp._process_is_alive(dead.pid), False)
        dead_temp = self._tmp / (
            f"target.lock{rp.LOCK_PUBLISH_MARKER}{dead.pid}-dead{LOCK_TEMP_SUFFIX}"
        )
        dead_temp.write_bytes(b"")

        live = self._spawn("import time\ntime.sleep(120)\n", log_name="live.log")
        live_temp = self._tmp / (
            f"target.lock{rp.LOCK_PUBLISH_MARKER}{live.pid}-live{LOCK_TEMP_SUFFIX}"
        )
        live_temp.write_bytes(b"")

        handle = rp.acquire_lock(self._tmp / "target.lock", 0)
        try:
            self.assertFalse(dead_temp.exists(), "死 pid 的残留发布临时文件未被清理")
            self.assertTrue(live_temp.exists(), "活 pid 的临时文件被误删")
        finally:
            self.assertTrue(rp.release_lock(self._tmp / "target.lock", handle))

    def test_three_contenders_with_leftover_dead_temp_have_single_owner(self):
        lock = self._tmp / "target.lock"
        dead = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        dead.wait(timeout=10)
        (self._tmp / f"target.lock{rp.LOCK_PUBLISH_MARKER}{dead.pid}-left{LOCK_TEMP_SUFFIX}").write_bytes(
            b""
        )

        names = ["a", "b", "c"]
        for name in names:
            self._spawn(
                _CONTENDER_CHILD,
                str(self._tmp),
                name,
                ",".join(names),
                log_name=f"contender-{name}.log",
            )
        deadline = time.time() + 30
        while time.time() < deadline:
            if all((self._tmp / f"result-{name}.json").exists() for name in names):
                break
            time.sleep(0.02)
        rows = {
            name: json.loads(
                (self._tmp / f"result-{name}.json").read_text(encoding="utf-8")
            )
            for name in names
        }
        winners = [row for row in rows.values() if row["acquired"]]
        self.assertEqual(len(winners), 1, rows)
        for row in rows.values():
            if not row["acquired"]:
                self.assertEqual(row["code"], "provision_lock_busy")
        disk = json.loads(lock.read_text(encoding="utf-8"))
        self.assertEqual(disk["token"], winners[0]["token"])
        self.assertEqual(self._temp_files(lock), [])


# ══════════════════════════════════════════════════════════════════════
# H3：guard / 锁目录的链接与逃逸保护
# ══════════════════════════════════════════════════════════════════════


class LockGuardLinkProtectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-lock-guard-"))
        self.addCleanup(self._cleanup)
        self.lock_path = self._tmp / "target.lock"
        self._junctions: list[Path] = []

    def _cleanup(self) -> None:
        # 先摘除 junction 再删目录：绝不跟随 reparse point 递归删除。
        for link in reversed(self._junctions):
            if rp._is_reparse_point(link):
                try:
                    os.rmdir(link)
                except OSError:  # pragma: no cover - 仅清理
                    pass
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _junction(self, link: Path, target: Path) -> bool:
        if os.name != "nt":  # pragma: no cover - 本环境为 Windows
            return False
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            self._junctions.append(link)
            return True
        return False

    def test_normal_guard_path_acquires_and_guard_is_plain_file(self):
        handle = rp.acquire_lock(self.lock_path, 0)
        try:
            guard = rp.lock_guard_path_for(self.lock_path)
            self.assertTrue(guard.exists())
            self.assertFalse(rp._is_reparse_point(guard))
            self.assertGreaterEqual(guard.stat().st_size, 1)
            self.assertEqual(
                json.loads(self.lock_path.read_text(encoding="utf-8"))["token"],
                handle["token"],
            )
        finally:
            self.assertTrue(rp.release_lock(self.lock_path, handle))

    def test_guard_junction_is_refused_and_outside_untouched(self):
        self._tmp.joinpath("outside").mkdir()
        outside_marker = self._tmp / "outside" / "marker.txt"
        outside_marker.write_text("outside-original", encoding="utf-8")
        guard = rp.lock_guard_path_for(self.lock_path)
        if not self._junction(guard, self._tmp / "outside"):
            self.skipTest("宿主无法创建 junction")
        self.assertTrue(rp._is_reparse_point(guard))

        with self.assertRaises(rp.ProvisionError) as ctx:
            rp.acquire_lock(self.lock_path, 0)
        self.assertEqual(ctx.exception.code, "symlink_refused")
        self.assertEqual(
            sorted(path.name for path in (self._tmp / "outside").iterdir()),
            ["marker.txt"],
        )
        self.assertEqual(
            outside_marker.read_text(encoding="utf-8"), "outside-original"
        )
        self.assertFalse(self.lock_path.exists())

    def test_lock_file_junction_is_refused(self):
        self._tmp.joinpath("outside-lock").mkdir()
        marker = self._tmp / "outside-lock" / "marker.txt"
        marker.write_text("outside-original", encoding="utf-8")
        if not self._junction(self.lock_path, self._tmp / "outside-lock"):
            self.skipTest("宿主无法创建 junction")

        with self.assertRaises(rp.ProvisionError) as ctx:
            rp.acquire_lock(self.lock_path, 0)
        self.assertEqual(ctx.exception.code, "symlink_refused")
        self.assertEqual(marker.read_text(encoding="utf-8"), "outside-original")
        self.assertFalse(rp.lock_guard_path_for(self.lock_path).exists())

    def test_linked_lock_directory_ancestor_is_refused(self):
        self._tmp.joinpath("outside-dir").mkdir()
        marker = self._tmp / "outside-dir" / "marker.txt"
        marker.write_text("outside-original", encoding="utf-8")
        linked_root = self._tmp / "linked-root"
        if not self._junction(linked_root, self._tmp / "outside-dir"):
            self.skipTest("宿主无法创建 junction")

        with self.assertRaises(rp.ProvisionError) as ctx:
            rp.acquire_lock(linked_root / "target.lock", 0)
        self.assertEqual(ctx.exception.code, "symlink_refused")
        self.assertEqual(
            sorted(path.name for path in (self._tmp / "outside-dir").iterdir()),
            ["marker.txt"],
        )
        self.assertEqual(marker.read_text(encoding="utf-8"), "outside-original")

    def test_linked_ancestor_is_refused_before_missing_parent_is_created(self):
        outside = self._tmp / "outside-missing-parent"
        outside.mkdir()
        marker = outside / "marker.txt"
        marker.write_text("outside-original", encoding="utf-8")
        linked_root = self._tmp / "linked-missing-parent"
        if not self._junction(linked_root, outside):
            self.skipTest("宿主无法创建 junction")

        # lock.parent 尚不存在；拒绝不能先经链接在外部创建 newdir。
        with self.assertRaises(rp.ProvisionError) as ctx:
            rp.acquire_lock(linked_root / "newdir" / "target.lock", 0)
        self.assertEqual(ctx.exception.code, "symlink_refused")
        self.assertEqual(sorted(path.name for path in outside.iterdir()), ["marker.txt"])
        self.assertEqual(marker.read_text(encoding="utf-8"), "outside-original")

    def test_guard_file_symlink_shape_is_refused_before_any_open(self):
        """文件符号链接形状：宿主无法真实创建（WinError 1314），用注入验证定序。"""
        guard = rp.lock_guard_path_for(self.lock_path)
        opened: list[str] = []
        real_open = rp.os.open

        def spy_open(file, flags, mode=0o777, **kwargs):
            opened.append(str(file))
            return real_open(file, flags, mode, **kwargs)

        with patch.object(rp, "_is_reparse_point", lambda path: Path(path) == guard):
            with patch.object(rp.os, "open", spy_open):
                with self.assertRaises(rp.ProvisionError) as ctx:
                    rp.acquire_lock(self.lock_path, 0)
        self.assertEqual(ctx.exception.code, "symlink_refused")
        self.assertEqual(opened, [], "拒绝前已经 open 了文件")
        self.assertFalse(guard.exists())
        self.assertFalse(self.lock_path.exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
