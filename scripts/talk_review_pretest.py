"""复核预跑：在仓库内用普通用户令牌跑测试并留日志，供只读复核者阅读。

Codex 的 Windows 沙箱无法运行本项目的完整 346（数据库/私有 ACL/用户环境），
所以测试由服务在沙箱外预跑；复核者只读代码、git 和这份日志，不获得写权限。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

SCHEMA = "talk-review-pretest-1"


def _repo_root(value: str | None) -> Path:
    root = Path(value).resolve() if value else Path(__file__).resolve().parents[1]
    if not (root / ".git").exists():
        raise SystemExit("repo_root_invalid: " + str(root))
    return root


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run(root: Path, command: str, task_id: int | None, log: str | None, timeout: int) -> dict:
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    before = _git(root, "status", "--porcelain").stdout.strip()
    log_path = Path(log).resolve() if log else (
        root / ".tmp" / "codex-review" / "pretest" / (str(task_id or "task") + ".log")
    ).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # TEMP 必须在仓库外：套件的 key_root_inside_repo 校验会把“临时目录在仓库内”
    # 判成非法，346 里有 23 项会因此失败。
    temp = Path(tempfile.mkdtemp(prefix="talk-review-pretest-"))
    env = dict(os.environ)
    env["TEMP"] = str(temp)
    env["TMP"] = str(temp)
    # 346 依赖仓库内路径与未跟踪状态；保持仓库在 PYTHONPATH 首位。
    root_resolved = root.resolve()
    pythonpath = [str(root)] + [
        item for item in env.get("PYTHONPATH", "").split(os.pathsep)
        if item and Path(item).resolve() != root_resolved
    ]
    venv = root / ".venv" / "Lib" / "site-packages"
    if venv.is_dir() and str(venv) not in pythonpath:
        pythonpath.append(str(venv))
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    started = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            command,
            cwd=str(root),
            env=env,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        output = ""
        for stream in (exc.stdout, exc.stderr):
            if isinstance(stream, str):
                output += stream
            elif isinstance(stream, bytes):
                output += stream.decode("utf-8", "replace")
        code = 124
        timed_out = True
    log_path.write_text(output, encoding="utf-8")
    shutil.rmtree(temp, ignore_errors=True)
    after = _git(root, "status", "--porcelain").stdout.strip()
    return {
        "schema": SCHEMA,
        "state": "passed" if code == 0 else "failed",
        "task_id": task_id,
        "command": command,
        "exit_code": code,
        "timeout": timed_out,
        "duration_seconds": round(time.monotonic() - started, 1),
        "head": head,
        "git_status_before": before.splitlines(),
        "git_status_after": after.splitlines(),
        "log": str(log_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="仓库根；默认取脚本所在仓库")
    parser.add_argument("--task-id", type=int, help="关联任务号（用于日志名）")
    parser.add_argument("--command", dest="run_command", required=True, help="要预跑的命令")
    parser.add_argument("--log", help="日志路径；默认 .tmp/codex-review/pretest/<任务号>.log")
    parser.add_argument("--timeout", type=int, default=1800, help="超时秒数；默认 1800")
    args = parser.parse_args(argv)
    root = _repo_root(args.repo)
    print(json.dumps(run(root, args.run_command, args.task_id, args.log, args.timeout), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
