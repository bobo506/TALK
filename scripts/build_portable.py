"""Build a Windows portable TALK directory and optional zip."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
PYTHON_ZIP = "python-3.12.1-embed-amd64.zip"
PYTHON_URL = "https://www.python.org/ftp/python/3.12.1/" + PYTHON_ZIP
ALLOW = ("server", "web", "scripts", "bridges", "cli", "docs", "examples", "TALK", "requirements.txt", "README.md", "start.bat", "stop.bat", "status.bat", "start-gui.bat")
EXCLUDED = {"tests", ".git", ".venv", ".talk", ".agents", ".codex", "__pycache__", "logs", "backups", "storage", "workspaces", "keys", "node_modules"}
SECRET = re.compile(rb"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}|\bsk-[A-Za-z0-9_-]{32,})")
README = """TALK 便携包（Windows x64）\n\n需要 Microsoft Edge。双击 start-gui.bat，首次启动会初始化配置和本地项目并打开窗口。关闭窗口后等待后台服务停止。start.bat 使用默认浏览器；stop.bat 可停止服务。\n配置在 config，数据库、项目、上传及日志在 data。管理员 Key 默认在 %LOCALAPPDATA%\\TALK\\keys；可用 TALK_KEYS_DIR 指定其他位置。请妥善保管数据和 Key。\n卸载：关闭 TALK 后删除本文件夹；如不再需要，可另行删除 Key 目录。\n"""


def excluded(path):
    name = path.name.lower()
    return (name in EXCLUDED or name.startswith(('.tmp', '.env')) or name.endswith(('.pyc', '.pyo', '.key', '.p12', '.pfx', '.sqlite', '.sqlite3', '.sqlite-wal', '.sqlite-shm', '.sqlite3-wal', '.sqlite3-shm', '.db', '.db-wal', '.db-shm')))


def copy_entry(src, dest):
    if src.is_symlink() or excluded(src):
        return
    if src.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir():
            copy_entry(child, dest / child.name)
    elif src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def verify_ssl(exe, cwd, attempts=10):
    time.sleep(3)
    for attempt in range(1, attempts + 1):
        result = subprocess.run([str(exe), '-B', '-c', 'import _ssl'], cwd=cwd,
                                capture_output=True, text=True, errors='replace')
        print(f'_ssl import attempt {attempt}/{attempts}: exit={result.returncode}', flush=True)
        if result.stdout:
            print(result.stdout, end='', flush=True)
        if result.stderr:
            print(result.stderr, end='', file=sys.stderr, flush=True)
        if result.returncode == 0:
            return
        if attempt < attempts:
            time.sleep(3)
    raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)


def install_python(target, archive):
    target.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            dest = (target / info.filename).resolve()
            if not dest.is_relative_to(target.resolve()):
                raise ValueError('unsafe Python archive path')
        z.extractall(target)
    exe = target / 'python.exe'
    if not exe.is_file() or not (target / 'python312.zip').is_file():
        raise ValueError('expected Python 3.12 embeddable archive')
    (target / 'python312._pth').write_text('python312.zip\n.\nLib\\site-packages\n..\\..\n', encoding='utf-8')
    subprocess.run([str(exe), '-c', 'import sys; assert sys.version_info[:3] == (3,12,1)'], check=True)
    site = target / 'Lib' / 'site-packages'
    # Host pip resolves Windows CPython 3.12 wheels; no pip is required in the package.
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-compile', '--only-binary=:all:', '--platform', 'win_amd64', '--implementation', 'cp', '--python-version', '3.12', '--abi', 'cp312', '--target', str(site), '-r', str(ROOT / 'requirements.txt')], check=True)
    verify_ssl(exe, target)
    # Generated console entry points include the build machine's absolute Python path.
    for name in ('bin', 'Scripts'):
        directory = site / name
        if directory.is_dir():
            shutil.rmtree(directory)
    for directory in sorted(site.rglob('tests'), key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir() and not directory.is_symlink():
            shutil.rmtree(directory)
    subprocess.run([str(exe), '-B', '-c', 'import fastapi, uvicorn, sqlmodel, httpx, yaml; from TALK.client import TalkClient'], cwd=target, check=True)


def scan(stage):
    count = 0
    for path in stage.rglob('*'):
        relative = path.relative_to(stage)
        if path.is_symlink():
            raise ValueError(f'symlink in package: {relative}')
        in_dependencies = relative.parts[:4] == ('runtime', 'python', 'Lib', 'site-packages')
        if not in_dependencies and any(excluded(Path(part)) for part in relative.parts):
            raise ValueError(f'excluded path in package: {relative}')
        if not path.is_file():
            continue
        count += 1
        if excluded(path) and not (in_dependencies and path.name.lower() in EXCLUDED):
            raise ValueError(f'excluded file in package: {relative}')
        data = path.read_bytes()
        if data.startswith(b'SQLite format 3\x00'):
            raise ValueError(f'database in package: {relative}')
        if SECRET.search(data):
            raise ValueError(f'possible secret in package: {relative}')
        if relative.parts[0] not in {'server', 'web', 'scripts', 'bridges', 'cli', 'docs', 'examples', 'TALK'} and b'd:\\claude-test' in data.lower():
            raise ValueError(f'development path in package: {relative}')
    return count


def build(out, make_zip=False, python_zip=None, skip_python=False):
    out = Path(out).resolve()
    stage = out / 'TALK'
    if any(stage.is_relative_to((ROOT / name).resolve()) for name in ALLOW if (ROOT / name).is_dir()):
        raise ValueError('output cannot be inside a source directory')
    if stage.exists():
        raise FileExistsError(f'output already exists: {stage}')
    out.mkdir(parents=True, exist_ok=True)
    stage.mkdir()
    for item in ALLOW:
        src = ROOT / item
        if not src.exists():
            raise FileNotFoundError(src)
        copy_entry(src, stage / item)
    version_file = ROOT / 'VERSION'
    version = version_file.read_text(encoding='utf-8').strip() if version_file.is_file() else '0.1.0'
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', version):
        raise ValueError('invalid VERSION')
    if version_file.is_file():
        copy_entry(version_file, stage / 'VERSION')
    for name in ('config', 'data'):
        (stage / name).mkdir()
    (stage / 'README-PORTABLE.txt').write_text(README, encoding='utf-8')
    if not skip_python:
        archive = Path(python_zip).resolve() if python_zip else out / PYTHON_ZIP
        if not archive.is_file():
            if python_zip:
                raise FileNotFoundError(archive)
            with urllib.request.urlopen(PYTHON_URL, timeout=60) as response, archive.open('xb') as target:
                shutil.copyfileobj(response, target)
        install_python(stage / 'runtime' / 'python', archive)
    count = scan(stage)
    if make_zip:
        zip_path = out / f'TALK-portable-{version}.zip'
        with zipfile.ZipFile(zip_path, 'x', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for path in sorted(stage.rglob('*')):
                if path.is_file() or (path.is_dir() and not any(path.iterdir())):
                    archive.write(path, Path('TALK') / path.relative_to(stage))
        digest = hashlib.sha256()
        with zip_path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        print(f'zip={zip_path} bytes={zip_path.stat().st_size} files={count} sha256={digest.hexdigest()}')
    else:
        print(f'directory={stage} files={count} bytes={sum(p.stat().st_size for p in stage.rglob("*") if p.is_file())}')
    return stage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--zip', action='store_true')
    parser.add_argument('--python-zip', type=Path)
    parser.add_argument('--skip-python', action='store_true')
    args = parser.parse_args()
    build(args.out, args.zip, args.python_zip, args.skip_python)


if __name__ == '__main__':
    main()
