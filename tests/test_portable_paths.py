"""Portable path configuration tests."""
from scripts import portable_paths


def test_keys_dir_defaults_inside_talk_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TALK_HOME", str(tmp_path))
    monkeypatch.delenv("TALK_KEYS_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert portable_paths.keys_dir() == (tmp_path / "data" / "keys").resolve()


def test_keys_dir_override_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("TALK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TALK_KEYS_DIR", str(tmp_path / "outside" / ".." / "custom"))
    assert portable_paths.keys_dir() == (tmp_path / "custom").resolve()
