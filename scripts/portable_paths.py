"""Paths for a portable TALK instance; importing this module has no side effects."""
import os
import sys
from pathlib import Path


def talk_home():
    return Path(os.environ.get("TALK_HOME") or Path(__file__).resolve().parent.parent).resolve()


def config_dir():
    return talk_home() / "config"


def config_path():
    return Path(os.environ.get("TALK_CONFIG") or config_dir() / "config.toml").resolve()


def keys_dir():
    default = Path(os.environ["LOCALAPPDATA"]) / "TALK" / "keys" if os.name == "nt" and os.environ.get("LOCALAPPDATA") else Path.home() / ".talk" / "keys"
    return Path(os.environ.get("TALK_KEYS_DIR") or default).resolve()


def data_dir():
    return talk_home() / "data"


def storage_dir(): return data_dir() / "storage"
def logs_dir(): return data_dir() / "logs"
def backups_dir(): return data_dir() / "backups"
def state_dir(): return data_dir() / "state"
def workspaces_dir(): return data_dir() / "workspaces"
def project_dir(): return data_dir() / "project"


def python_executable():
    for candidate in (talk_home() / "runtime/python/python.exe", talk_home() / ".venv/Scripts/python.exe"):
        if candidate.is_file():
            return candidate
    return Path(sys.executable).absolute()


def ensure_portable_dirs():
    for path in (config_dir(), data_dir(), storage_dir(), logs_dir(), backups_dir(), state_dir(), workspaces_dir(), project_dir(), keys_dir()):
        path.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    if sys.argv[1:] != ["--port"]:
        raise SystemExit("usage: python -m scripts.portable_paths --port")
    import tomllib
    with config_path().open("rb") as stream:
        port = tomllib.load(stream)["server"]["port"]
    if type(port) is not int or not 1 <= port <= 65535:
        raise SystemExit("invalid configured port")
    print(port)
