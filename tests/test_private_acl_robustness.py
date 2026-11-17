import os
import subprocess

import pytest

from scripts import role_provision as rp

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows ACL tests")


def acl(path, *args):
    result = subprocess.run(["icacls", str(path), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def parent_with_acl(tmp_path, hostile=False):
    parent = tmp_path / "parent"
    parent.mkdir()
    user = rp._windows_current_user_sid()
    acl(parent, "/inheritance:r", "/grant:r", f"*{user}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F")
    if hostile:
        acl(parent, "/grant", "*S-1-1-0:(OI)(CI)R")
    return parent


def test_trusted_inherited_and_repair(tmp_path):
    parent = parent_with_acl(tmp_path)
    child = parent / "key"
    child.write_text("test", encoding="utf-8")
    before = rp._windows_verify_private_acl(child)
    print("trusted inherited:", before)
    assert before[0] and ":inherited" in before[1]
    after = rp._windows_harden_trusted_inherited_acl(child)
    assert after[0] and ":inherited" not in after[1]
    assert child.read_text(encoding="utf-8") == "test"


def test_untrusted_inherited_rejected_and_protected_creation(tmp_path):
    parent = parent_with_acl(tmp_path, hostile=True)
    child = parent / "ordinary"
    child.write_text("test", encoding="utf-8")
    result = rp._windows_verify_private_acl(child)
    print("foreign inherited:", result)
    assert not result[0] and "S-1-1-0:inherited" in result[1]
    assert not rp._windows_harden_trusted_inherited_acl(child)[0]
    protected = parent / "protected"
    rp._windows_create_file_with_private_acl(protected, b"test")
    result = rp._windows_verify_private_acl(protected)
    assert result[0], result
    assert ":inherited" not in result[1]
    published = rp._windows_publish_temp_file(parent / "target", b"test")
    assert rp._windows_verify_private_acl(published)[0]


def _run_codex_host(key_path, monkeypatch):
    import json
    from unittest.mock import Mock
    from scripts import codex_role_host as host

    client = Mock()
    role = {"member_id": "member", "binding_state": "bound",
            "runner": {"runtime": "codex"},
            "model": {"choice_id": "choice", "model_alias": "model"}}
    def request(method, path, **kwargs):
        if path.endswith("/roles"):
            return [role]
        if kwargs.get("key"):
            return {"id": "member", "kind": "agent", "display_name": "test"}
        return {"kind": "human"}
    client.request.side_effect = request
    manager = Mock()
    manager.serve.side_effect = host.Drained()
    monkeypatch.setattr(host.rsh, "load_operator_key", lambda *a: "operator")
    monkeypatch.setattr(host.rsh, "TalkHostClient", lambda *a: client)
    monkeypatch.setattr(host, "CodexRoleHost", lambda *a, **kw: manager)
    args = ["--project", "project", "--member", "member", "--project-root", str(key_path.parent),
            "--state-dir", str(key_path.parent), "--base-url", "http://unused",
            "--operator-key-file", "unused", "--role-key-file", str(key_path),
            "--expected-choice-id", "choice", "--expected-model-alias", "model",
            "--codex-executable", "unused", "--apply"]
    return host.main(args), client, manager


def test_codex_host_repairs_trusted_inheritance_before_read(tmp_path, monkeypatch):
    parent = parent_with_acl(tmp_path)
    key = parent / "key"
    key.write_text("test", encoding="utf-8")
    assert ":inherited" in rp._windows_verify_private_acl(key)[1]
    result, client, manager = _run_codex_host(key, monkeypatch)
    assert result == 0
    ok, detail = rp._windows_verify_private_acl(key)
    assert ok and ":inherited" not in detail
    assert any(call.kwargs.get("key") == "test" for call in client.request.call_args_list)
    manager.serve.assert_called_once()


@pytest.mark.parametrize("sid", ["S-1-1-0", "S-1-5-32-545"])
def test_codex_host_rejects_foreign_inheritance_before_read(tmp_path, monkeypatch, capsys, sid):
    import json
    parent = parent_with_acl(tmp_path)
    acl(parent, "/grant", f"*{sid}:(OI)(CI)R")
    key = parent / "key"
    key.write_text("secret-test-value", encoding="utf-8")
    result, client, manager = _run_codex_host(key, monkeypatch)
    output = json.loads(capsys.readouterr().out)
    assert result == 1 and output["error_code"] == "key_permissions_failed"
    assert sid in output["detail"] and "inherited" in output["detail"]
    assert str(key) not in output["detail"] and "secret-test-value" not in output["detail"]
    assert not any(call.kwargs.get("key") for call in client.request.call_args_list)
    manager.serve.assert_not_called()
