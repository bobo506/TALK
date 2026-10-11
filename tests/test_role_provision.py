# -*- coding: utf-8 -*-
"""``scripts/role_provision.py``（R1-2 B 片）单元与行为测试。

测试真实性约定
--------------
- **只用假 HTTP 传输**：不导入 ``server.*``、不连真实网络、不写生产 HTTP；
- 全部目标根都落在隔离临时目录：``repo``（仓库内）与 ``keys``（仓库外），
  不触碰真实仓库、真实 Key、生产配置；
- 角色 Key / operator Key 都是明显 canary 值，用于锁定“绝不出现在 stdout/stderr”；
- 不启动任何 CLI：``--cli-executable`` 只做存在性检查。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path_entry in (str(PROJECT_ROOT), str(PROJECT_ROOT / "scripts")):
    if _path_entry not in sys.path:
        sys.path.insert(0, _path_entry)

import role_provision as rp  # noqa: E402
from cli.profiles import member_dir_name  # noqa: E402

PROJECT_ID = "prj_canary"
MEMBER_ID = "agent:prj-canary.dev-1234abcd"
OPERATION_KEY = "op-1234567890abcdef"
CANARY_KEY = "role-canary-0123456789abcdef"
CANARY_OPERATOR = "operator-canary-abcdef0123456789"
BASE_URL = "http://fake.test"

PROVISION_PATH = rp._provision_path(PROJECT_ID, MEMBER_ID)
ROSTER_PATHS_PATH = rp._provision_roster_paths_path(PROJECT_ID, MEMBER_ID)
ROSTER_PATH = rp._roster_path(PROJECT_ID)
ROLES_PATH = rp._roles_path(PROJECT_ID)
BINDING_PATH = rp._agent_sub_path(PROJECT_ID, MEMBER_ID, "binding")
PROFILE_PATH = rp._agent_sub_path(PROJECT_ID, MEMBER_ID, "profile")
ROSTER_RELATIVE_PATHS = rp._roster_relative_paths(MEMBER_ID)


def _url_path(url: str) -> str:
    return urlsplit(url).path


class _Route:
    def __init__(self, method: str, predicate, responses: list) -> None:
        self.method = method.upper()
        self.predicate = predicate
        self.responses = list(responses)

    def take(self, method=None, url=None, body=None):
        if len(self.responses) > 1:
            response = self.responses.pop(0)
        else:
            response = self.responses[0]
        if callable(response):
            return response(method=method, url=url, body=body)
        return response


class FakeTransport:
    """记录全部调用的假 HTTP 边界；未命中的请求返回 404。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.routes: list[_Route] = []

    def add(self, method: str, predicate, *responses) -> None:
        self.routes.append(_Route(method, predicate, list(responses)))

    def add_path(self, method: str, path: str, *responses) -> None:
        self.add(method, lambda url: _url_path(url) == path, *responses)

    def request_json(self, method: str, url: str, *, api_key=None, body=None, timeout=None):
        self.calls.append(
            {
                "method": method.upper(),
                "url": url,
                "api_key": api_key,
                "body": body,
            }
        )
        for route in self.routes:
            if route.method == method.upper() and route.predicate(url):
                return route.take(method=method, url=url, body=body)
        return rp.HttpResponse(status=404, payload=None)

    # -- 断言辅助 -------------------------------------------------------
    def calls_of(self, method: str) -> list[dict]:
        return [call for call in self.calls if call["method"] == method.upper()]

    def urls(self) -> list[str]:
        return [call["url"] for call in self.calls]


def _roster_row(*, paths: bool = True, member_id: str = MEMBER_ID) -> dict:
    base = f".talk/agents/{member_dir_name(member_id)}"
    return {
        "member_id": member_id,
        "identity_path": f"{base}/IDENTITY.md" if paths else None,
        "soul_path": f"{base}/SOUL.md" if paths else None,
        "user_path": f"{base}/USER.md" if paths else None,
        "memory_pointer": None,
        "business_role": "dev",
        "decision_tier": "execution",
        "capability_summary": [],
    }


def _roles_item(
    *,
    runner_id: str = "runner-canary",
    model_id: str = "model-canary",
    model_alias: str = "alias-canary",
    binding_state: str = "bound",
    choice_source: str = "creation_operation",
    choice_id: str = "rmc_canary",
    choice_binding_mismatch: bool = False,
) -> dict:
    return {
        "member_id": MEMBER_ID,
        "role_name": "dev",
        "origin": "managed",
        "identity": "managed",
        "archived": False,
        "identity_exclusive": True,
        "runner": {"runner_id": runner_id, "runtime": "dsh", "display_name": "fake", "status": "ready"},
        "model": {
            "choice_id": choice_id,
            "choice_source": choice_source,
            "choice_binding_mismatch": choice_binding_mismatch,
            "model_id": model_id,
            "model_alias": model_alias,
        },
        "role_description": None,
        "binding_state": binding_state,
        "service": None,
    }


def _binding_out(
    *,
    runner_id: str = "runner-canary",
    model_id: str = "model-canary",
    model_alias: str = "alias-canary",
    binding_state: str = "bound",
    binding_fingerprint: object = "f" * 64,
) -> dict:
    return {
        "project_id": PROJECT_ID,
        "member_id": MEMBER_ID,
        "binding": {
            "runner_id": runner_id,
            "model_source": "builtin",
            "provider_id": "provider-canary",
            "connection_ref": "connection-canary",
            "model_id": model_id,
            "model_alias": model_alias,
            "model_display_name": "fake",
            "binding_fingerprint": binding_fingerprint,
        },
        "binding_state": binding_state,
    }


def _provision_job(
    *,
    revision: int = 3,
    attempts: int = 1,
    credential_version: int = 1,
    role_credential_version: object = "same",
    expected_binding_fingerprint: object = "f" * 64,
) -> dict:
    if role_credential_version == "same":
        role_credential_version = credential_version
    return {
        "operation_key": OPERATION_KEY,
        "project_id": PROJECT_ID,
        "member_id": MEMBER_ID,
        "status": "pending",
        "revision": revision,
        "credential_version": credential_version,
        # 补正 G1：读取时角色行当前的凭据版本（默认与作业快照一致 = 未轮换）。
        "role_credential_version": role_credential_version,
        # 补正 G3：创建操作所选 choice 的预期绑定指纹（默认与 _binding_out 一致）。
        "expected_binding_fingerprint": expected_binding_fingerprint,
        "resume_of": None,
        "steps": {
            step: {
                "state": "pending",
                "attempts": attempts,
                "error_code": None,
                "updated_at": None,
            }
            for step in rp.STEP_ORDER
        },
        "created_by": "human:canary",
        "created_at": None,
        "updated_at": None,
    }


def _dynamic_ack(method=None, url=None, body=None) -> rp.HttpResponse:
    """ACK 成功响应：revision 由**本次 ACK 请求**推进，attempt/凭据版本回显请求值。"""
    request = body if isinstance(body, dict) else {}
    revision = int(request.get("revision") or 0) + 1
    job = _provision_job(
        revision=revision,
        attempts=int(request.get("attempt") or 1),
        credential_version=int(request.get("credential_version") or 1),
    )
    step = request.get("step")
    if step in job["steps"]:
        job["steps"][step]["state"] = str(request.get("state") or "pending")
        job["steps"][step]["error_code"] = request.get("error_code")
    return rp.HttpResponse(200, job)


def happy_transport(
    *,
    me_id: str = MEMBER_ID,
    me_status: int = 200,
    roster_paths: bool = True,
    roster_responses: list | None = None,
    binding: object = "default",
    roles: object = "default",
    register_status: int = 200,
    ack_status: int = 200,
    job_get_status: int = 200,
    job_get_responses: list | None = None,
    job_post_status: int = 201,
    revision: int = 3,
    attempts: int = 1,
) -> FakeTransport:
    transport = FakeTransport()
    transport.add_path("GET", rp._me_path(), rp.HttpResponse(me_status, {"id": me_id, "kind": "agent"}))
    if roster_responses is None:
        roster_responses = [rp.HttpResponse(200, [_roster_row(paths=roster_paths)])]
    transport.add_path("GET", ROSTER_PATH, *roster_responses)
    if roles == "default":
        roles = [ _roles_item() ]
    transport.add_path("GET", ROLES_PATH, rp.HttpResponse(200, roles))
    if binding == "default":
        binding = _binding_out()
    transport.add_path("GET", BINDING_PATH, rp.HttpResponse(200, binding))
    transport.add_path("POST", ROSTER_PATHS_PATH, rp.HttpResponse(register_status, {}))
    if job_get_responses is None:
        job_get_payload = (
            _provision_job(revision=revision, attempts=attempts)
            if job_get_status == 200
            else None
        )
        job_get_responses = [rp.HttpResponse(job_get_status, job_get_payload)]
    transport.add_path("GET", PROVISION_PATH, *job_get_responses)
    transport.add_path(
        "POST",
        PROVISION_PATH,
        rp.HttpResponse(
            job_post_status,
            _provision_job(revision=revision, attempts=attempts)
            if job_post_status in (200, 201)
            else {"detail": "provision_job_failed"},
        ),
    )
    if ack_status == 200:
        # 成功 ACK 的 revision 由本次请求推进（补正 F1：脚本不再用新的 GET 取 revision）。
        transport.add_path("POST", PROVISION_PATH + "/ack", _dynamic_ack)
    else:
        transport.add_path("POST", PROVISION_PATH + "/ack", rp.HttpResponse(ack_status, _provision_job()))
    return transport


class RoleProvisionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-role-provision-"))
        self.addCleanup(lambda: shutil.rmtree(self._tmp, ignore_errors=True))
        self.repo = self._tmp / "repo"
        self.repo.mkdir()
        self.project_root = self._tmp / "proj"
        self.project_root.mkdir()
        self.key_root = self._tmp / "keys"  # 仓库之外
        self.env_happy = {
            "TALK_ROLE_API_KEY": CANARY_KEY,
            "TALK_OPERATOR_API_KEY": CANARY_OPERATOR,
        }

    # -- 辅助 -----------------------------------------------------------
    def key_file(self) -> Path:
        return self.key_root / f"{member_dir_name(MEMBER_ID)}.key"

    def seed_key_file(self, content: str = CANARY_KEY) -> Path:
        """用脚本自己的私有权限写入路径落一个 Key 文件（Windows 上必须真过 ACL 核验）。"""
        self.key_root.mkdir(parents=True, exist_ok=True)
        rp._write_key_file(self.key_file(), content)
        return self.key_file()

    def profile_path(self, filename: str) -> Path:
        return (
            self.project_root
            / ".talk"
            / "agents"
            / member_dir_name(MEMBER_ID)
            / filename
        )

    def run_script(
        self,
        transport,
        *,
        apply: bool = True,
        steps=None,
        env=None,
        member_id: str = MEMBER_ID,
        key_root=None,
        project_root=None,
        overwrite_profile: bool = False,
        key_input_file=None,
        cli_executable=None,
        resume: bool = False,
        resume_steps=None,
        lock_stale_seconds: float = rp.DEFAULT_LOCK_STALE_SECONDS,
    ):
        # preflight 需要已验证的角色 Key：单独跑 preflight 时先落一个可核验的 Key 文件。
        selected = None if steps is None else (
            steps.split(",") if isinstance(steps, str) else list(steps)
        )
        if selected is not None and "preflight" in selected and not self.key_file().exists():
            self.seed_key_file()
        if (
            selected is not None
            and "preflight" in selected
            and "profile" not in selected
        ):
            # F4：preflight 要求三档真实可读；单独跑 preflight 时先落下身份档。
            for kind in rp.PROFILE_KINDS:
                target = rp.profile_target_paths(
                    project_root if project_root is not None else self.project_root,
                    member_id,
                )[kind]
                if not target.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(f"# seeded {kind}\n", encoding="utf-8")
        if resume_steps is None and selected is not None:
            # 与 CLI 一致：显式 --steps 才把该列表作为 resume steps；默认传 null。
            resume_steps = selected
        return rp.run_provision(
            project_id=PROJECT_ID,
            member_id=member_id,
            operation_key=OPERATION_KEY,
            project_root=project_root if project_root is not None else self.project_root,
            key_root=key_root if key_root is not None else self.key_root,
            base_url=BASE_URL,
            apply=apply,
            overwrite_profile=overwrite_profile,
            steps=steps,
            resume=resume,
            resume_steps=resume_steps,
            key_input_file=key_input_file,
            cli_executable=cli_executable,
            lock_stale_seconds=lock_stale_seconds,
            transport=transport,
            environ=dict(env or {}),
            repo_root=self.repo,
        )


# ---------------------------------------------------------------------------
# dry-run：零写入、零 HTTP、完全离线
# ---------------------------------------------------------------------------


class DryRunTests(RoleProvisionTestCase):
    def test_default_dry_run_zero_writes_zero_http(self):
        transport = FakeTransport()  # 任何请求都不会被应答 → 必须一个都不发
        doc, code = self.run_script(transport, apply=False, env=self.env_happy)

        self.assertEqual(code, 0)
        self.assertEqual(doc["conclusion"], "planned")
        self.assertEqual(doc["mode"], "dry-run")
        self.assertEqual(transport.calls, [])
        self.assertFalse(self.key_root.exists())
        self.assertEqual(list(self.project_root.rglob("*")), [])
        self.assertEqual(doc["ack"], {"sent": False, "reason": "not_apply_mode", "results": []})
        self.assertEqual(doc["job"], {"action": "none", "status": None, "revision": None})
        self.assertIsNone(doc["error_code"])

    def test_dry_run_reports_steps_as_planned(self):
        doc, code = self.run_script(FakeTransport(), apply=False, env=self.env_happy)
        self.assertEqual(code, 0)
        self.assertEqual(doc["steps"]["profile"]["state"], "planned")
        self.assertIn("IDENTITY.md", doc["steps"]["profile"]["detail"])
        self.assertEqual(doc["steps"]["key_file"]["state"], "planned")
        self.assertIn("TALK_ROLE_API_KEY", doc["steps"]["key_file"]["detail"])
        self.assertEqual(doc["steps"]["preflight"]["state"], "planned")
        self.assertIn("cli_entry=not_checked", doc["steps"]["preflight"]["detail"])

    def test_dry_run_existing_key_file_is_read_only(self):
        self.key_root.mkdir(parents=True, exist_ok=True)
        self.key_file().write_text(CANARY_KEY, encoding="utf-8")
        doc, code = self.run_script(FakeTransport(), apply=False, env={})
        self.assertEqual(code, 0)
        self.assertEqual(doc["steps"]["key_file"]["state"], "planned")
        self.assertIn("--apply", doc["steps"]["key_file"]["detail"])
        self.assertEqual(self.key_file().read_text(encoding="utf-8"), CANARY_KEY)

    def test_dry_run_missing_key_source_is_role_key_unknown(self):
        doc, code = self.run_script(FakeTransport(), apply=False, steps="key_file", env={})
        self.assertEqual(code, 1)
        self.assertEqual(doc["conclusion"], "failed")
        self.assertEqual(doc["error_code"], "role_key_unknown")
        self.assertEqual(doc["steps"]["key_file"]["state"], "failed")
        self.assertFalse(self.key_root.exists())

    def test_dry_run_unselected_steps_stay_pending(self):
        doc, code = self.run_script(FakeTransport(), apply=False, steps="profile", env={})
        self.assertEqual(code, 0)
        self.assertEqual(doc["steps"]["key_file"]["state"], "pending")
        self.assertEqual(doc["steps"]["preflight"]["state"], "pending")


# ---------------------------------------------------------------------------
# profile 步骤
# ---------------------------------------------------------------------------


class ProfileStepTests(RoleProvisionTestCase):
    def test_apply_writes_profile_and_key(self):
        transport = happy_transport()
        doc, code = self.run_script(transport, env=self.env_happy)

        self.assertEqual(code, 0)
        self.assertEqual(doc["conclusion"], "applied")
        self.assertEqual(doc["steps"]["profile"]["state"], "succeeded")
        self.assertEqual(doc["steps"]["key_file"]["state"], "succeeded")
        self.assertEqual(doc["steps"]["preflight"]["state"], "succeeded")

        identity = self.profile_path("IDENTITY.md")
        self.assertTrue(identity.is_file())
        self.assertTrue(self.profile_path("SOUL.md").is_file())
        self.assertTrue(self.profile_path("USER.md").is_file())
        content = identity.read_text(encoding="utf-8")
        self.assertIn("# IDENTITY", content)
        self.assertIn(MEMBER_ID, content)

        self.assertTrue(self.key_file().is_file())
        self.assertEqual(self.key_file().read_text(encoding="utf-8"), CANARY_KEY + "\n")
        self.assertIn("permissions=", doc["steps"]["key_file"]["detail"])
        self.assertTrue(doc["ack"]["sent"])
        self.assertEqual(len(doc["ack"]["results"]), 3)

    def test_existing_identity_content_preserved(self):
        identity = self.profile_path("IDENTITY.md")
        identity.parent.mkdir(parents=True, exist_ok=True)
        identity.write_text("HUMAN EDIT KEEP ME", encoding="utf-8")

        doc, code = self.run_script(happy_transport(), env=self.env_happy)

        self.assertEqual(code, 0)
        self.assertEqual(identity.read_text(encoding="utf-8"), "HUMAN EDIT KEEP ME")
        self.assertTrue(self.profile_path("SOUL.md").is_file())
        self.assertTrue(self.profile_path("USER.md").is_file())
        self.assertIn("IDENTITY.md", doc["steps"]["profile"]["detail"])

    def test_partial_profile_fill_only_missing_files(self):
        soul = self.profile_path("SOUL.md")
        soul.parent.mkdir(parents=True, exist_ok=True)
        soul.write_text("SOUL HUMAN EDIT", encoding="utf-8")

        doc, code = self.run_script(happy_transport(), env=self.env_happy)

        self.assertEqual(code, 0)
        self.assertEqual(soul.read_text(encoding="utf-8"), "SOUL HUMAN EDIT")
        self.assertTrue(self.profile_path("IDENTITY.md").is_file())
        self.assertTrue(self.profile_path("USER.md").is_file())

    def test_overwrite_profile_replaces_existing(self):
        for name in ("IDENTITY.md", "SOUL.md", "USER.md"):
            self.profile_path(name).parent.mkdir(parents=True, exist_ok=True)
            self.profile_path(name).write_text("OLD", encoding="utf-8")

        doc, code = self.run_script(
            happy_transport(), env=self.env_happy, overwrite_profile=True
        )

        self.assertEqual(code, 0)
        for name in ("IDENTITY.md", "SOUL.md", "USER.md"):
            self.assertNotEqual(self.profile_path(name).read_text(encoding="utf-8"), "OLD")
        self.assertIn("IDENTITY.md", doc["steps"]["profile"]["detail"])

    def test_skipped_when_all_profiles_exist(self):
        for name in ("IDENTITY.md", "SOUL.md", "USER.md"):
            self.profile_path(name).parent.mkdir(parents=True, exist_ok=True)
            self.profile_path(name).write_text("KEEP", encoding="utf-8")

        doc, code = self.run_script(happy_transport(), env=self.env_happy, steps="profile")
        self.assertEqual(code, 0)
        self.assertEqual(doc["steps"]["profile"]["state"], "skipped")
        for name in ("IDENTITY.md", "SOUL.md", "USER.md"):
            self.assertEqual(self.profile_path(name).read_text(encoding="utf-8"), "KEEP")

    def test_unselected_key_step_not_acked(self):
        doc, code = self.run_script(happy_transport(), env=self.env_happy, steps="profile")
        self.assertEqual(code, 0)
        self.assertEqual(doc["steps"]["key_file"]["state"], "pending")
        self.assertEqual(
            doc["ack"]["results"],
            [
                {
                    "step": "profile",
                    "sent": True,
                    "http_status": 200,
                    "state": "succeeded",
                    "attempt": 1,
                    "revision": 4,
                    "credential_version": 1,
                }
            ],
        )
        self.assertFalse(self.key_file().exists())


# ---------------------------------------------------------------------------
# key_file 步骤
# ---------------------------------------------------------------------------


class KeyStepTests(RoleProvisionTestCase):
    def test_existing_key_verified_is_skipped_without_rewrite(self):
        self.key_root.mkdir(parents=True, exist_ok=True)
        # 用脚本自己的私有权限路径落盘：内容无换行 = 未被改写。
        rp._write_key_file(self.key_file(), CANARY_KEY)
        before = self.key_file().read_bytes()

        transport = happy_transport()
        doc, code = self.run_script(transport, env=self.env_happy, steps="key_file")

        self.assertEqual(code, 0)
        self.assertEqual(doc["steps"]["key_file"]["state"], "skipped")
        self.assertEqual(self.key_file().read_bytes(), before)
        self.assertIn("permissions=", doc["steps"]["key_file"]["detail"])
        ack_posts = [c for c in transport.calls_of("POST")]
        self.assertEqual(ack_posts[0]["body"]["state"], "skipped")
        self.assertIsNone(ack_posts[0]["body"]["error_code"])

    def test_role_key_stale_when_existing_key_rejected(self):
        self.key_root.mkdir(parents=True, exist_ok=True)
        rp._write_key_file(self.key_file(), "stale-canary-key-0001")
        before = self.key_file().read_bytes()

        transport = happy_transport(me_status=401)
        doc, code = self.run_script(transport, env=self.env_happy, steps="key_file")

        self.assertEqual(code, 1)
        self.assertEqual(doc["conclusion"], "failed")
        self.assertEqual(doc["error_code"], "role_key_stale")
        self.assertEqual(doc["steps"]["key_file"]["state"], "failed")
        self.assertEqual(self.key_file().read_bytes(), before)
        ack_posts = transport.calls_of("POST")
        self.assertEqual(ack_posts[0]["body"]["state"], "failed")
        self.assertEqual(ack_posts[0]["body"]["error_code"], "role_key_stale")

    def test_identity_mismatch_when_key_belongs_to_other_member(self):
        self.key_root.mkdir(parents=True, exist_ok=True)
        rp._write_key_file(self.key_file(), "other-member-canary-key")
        before = self.key_file().read_bytes()

        transport = happy_transport(me_id="agent:other.member-9999")
        doc, code = self.run_script(transport, env=self.env_happy, steps="key_file")

        self.assertEqual(code, 1)
        self.assertEqual(doc["error_code"], "identity_mismatch")
        self.assertEqual(self.key_file().read_bytes(), before)

    def test_existing_key_file_without_private_acl_fails_closed(self):
        """F6：已有 Key 文件权限不私有 → 如实失败，绝不按 succeeded/skipped 上报。"""
        self.key_root.mkdir(parents=True, exist_ok=True)
        self.key_file().write_text(CANARY_KEY, encoding="utf-8")

        transport = happy_transport()
        doc, code = self.run_script(transport, env=self.env_happy, steps="key_file")

        if os.name == "nt":
            self.assertEqual(doc["steps"]["key_file"]["state"], "failed")
            self.assertEqual(doc["error_code"], "key_permissions_failed")
            self.assertEqual(code, 1)
        else:
            os.chmod(self.key_file(), 0o600)
            doc, code = self.run_script(
                happy_transport(), env=self.env_happy, steps="key_file"
            )
            self.assertEqual(doc["steps"]["key_file"]["state"], "skipped")
            self.assertEqual(code, 0)

    def test_missing_key_source_apply_role_key_unknown(self):
        transport = happy_transport()
        doc, code = self.run_script(transport, env={}, steps="key_file")

        self.assertEqual(code, 1)
        self.assertEqual(doc["error_code"], "role_key_unknown")
        self.assertEqual(doc["steps"]["key_file"]["state"], "failed")
        self.assertFalse(self.key_file().exists())
        # 未 ACK 前不写任何 Key；缺 operator 时也不 ACK。
        self.assertFalse(transport.calls)

    def test_key_input_file_is_the_key_source(self):
        key_input = self._tmp / "role-key-input.txt"
        key_input.write_text(CANARY_KEY + "\n", encoding="utf-8")
        transport = happy_transport()

        doc, code = self.run_script(
            transport, env=self.env_happy, steps="key_file", key_input_file=key_input
        )

        self.assertEqual(code, 0)
        self.assertEqual(doc["steps"]["key_file"]["state"], "succeeded")
        self.assertEqual(self.key_file().read_text(encoding="utf-8"), CANARY_KEY + "\n")

    def test_key_root_inside_repo_refused_before_any_write(self):
        transport = happy_transport()
        doc, code = self.run_script(
            transport, env=self.env_happy, key_root=self.repo / "keys"
        )

        self.assertEqual(code, 1)
        self.assertEqual(doc["error_code"], "key_root_inside_repo")
        self.assertEqual(doc["conclusion"], "failed")
        self.assertEqual(transport.calls, [])
        self.assertEqual(list(self.project_root.rglob("*")), [])


# ---------------------------------------------------------------------------
# 路径安全
# ---------------------------------------------------------------------------


class PathSafetyTests(RoleProvisionTestCase):
    def test_path_escape_refused(self):
        transport = happy_transport()
        doc, code = self.run_script(
            transport, env=self.env_happy, member_id="agent:../evil"
        )
        self.assertEqual(code, 1)
        self.assertEqual(doc["error_code"], "path_escape_refused")
        self.assertEqual(transport.calls, [])
        self.assertEqual(list(self.project_root.rglob("*")), [])

    def test_symlink_refused_real_or_guard_directly(self):
        outside = self._tmp / "outside"
        outside.mkdir()
        link = self.project_root / ".talk"
        created = False
        try:
            os.symlink(outside, link, target_is_directory=True)
            created = True
        except (OSError, NotImplementedError, AttributeError):
            created = False

        if created:
            with self.assertRaises(rp.ProvisionError) as ctx:
                rp.profile_target_paths(self.project_root, MEMBER_ID)
            self.assertEqual(ctx.exception.code, "symlink_refused")
            transport = happy_transport()
            doc, code = self.run_script(transport, env=self.env_happy)
            self.assertEqual(code, 1)
            self.assertEqual(doc["error_code"], "symlink_refused")
            self.assertEqual(transport.calls, [])
        else:
            # 本机不允许建符号链接：直接断言守卫函数本身。
            target = self.project_root / "nested" / "IDENTITY.md"
            with mock.patch.object(
                rp, "_is_reparse_point", side_effect=lambda p: str(p).endswith("nested")
            ):
                with self.assertRaises(rp.ProvisionError) as ctx:
                    rp.assert_inside_root(self.project_root, target)
            self.assertEqual(ctx.exception.code, "symlink_refused")
            self.assertFalse(target.parent.exists())

    def test_reparse_point_flag_detection(self):
        flag = 0x400
        fake_info = types.SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=flag)
        with mock.patch.object(rp.os, "lstat", return_value=fake_info), mock.patch.object(
            rp.stat, "FILE_ATTRIBUTE_REPARSE_POINT", flag, create=True
        ):
            self.assertTrue(rp._is_reparse_point(Path("C:/fake/junction")))

    def test_key_file_path_guard_rejects_escape(self):
        with self.assertRaises(rp.ProvisionError) as ctx:
            rp.key_file_path(self.key_root, "agent:../../escape")
        self.assertEqual(ctx.exception.code, "path_escape_refused")


# ---------------------------------------------------------------------------
# 独占锁
# ---------------------------------------------------------------------------


class LockTests(RoleProvisionTestCase):
    def test_lock_busy_when_held(self):
        lock_path = rp.lock_path_for(self.key_file())
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        # 不可解析的锁内容 = 无法判定持有者存活 → fail closed（绝不按年龄抢占）。
        lock_path.write_text("held-by-concurrent-run", encoding="utf-8")

        transport = happy_transport()
        doc, code = self.run_script(transport, env=self.env_happy, steps="profile")

        self.assertEqual(code, 1)
        self.assertEqual(doc["error_code"], "provision_lock_busy")
        self.assertEqual(transport.calls, [])
        self.assertFalse(self.profile_path("IDENTITY.md").exists())
        self.assertTrue(lock_path.exists())
        # 身份档锁在 Key 锁失败后必须被反向释放，不留残锁。
        self.assertFalse(rp.profile_lock_path_for(self.project_root, MEMBER_ID).exists())

    def test_live_lock_is_never_reclaimed_by_age(self):
        """F5：首 owner 仍存活时，超龄 mtime 也不能被第二 owner 回收。"""
        lock_path = rp.lock_path_for(self.key_file())
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "schema": rp.LOCK_SCHEMA,
            "token": "live-owner-token",
            "pid": os.getpid(),  # 当前进程 = 确认存活
            "started_at": "2020-01-01T00:00:00+00:00",
        }
        lock_path.write_text(json.dumps(record), encoding="utf-8")
        old = 1_000_000.0
        os.utime(lock_path, (old, old))

        doc, code = self.run_script(
            happy_transport(), env=self.env_happy, steps="profile", lock_stale_seconds=0
        )
        self.assertEqual(code, 1)
        self.assertEqual(doc["error_code"], "provision_lock_busy")
        self.assertTrue(lock_path.exists())
        self.assertEqual(json.loads(lock_path.read_text(encoding="utf-8"))["token"], "live-owner-token")

    def test_stale_lock_with_dead_owner_reclaimed_and_recorded(self):
        lock_path = rp.lock_path_for(self.key_file())
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "schema": rp.LOCK_SCHEMA,
            "token": "dead-owner-token",
            "pid": 0x7FFFFFF0,  # 远大于本机 pid 上限：确认不存在
            "started_at": "2020-01-01T00:00:00+00:00",
        }
        lock_path.write_text(json.dumps(record), encoding="utf-8")
        old = 1_000_000.0
        os.utime(lock_path, (old, old))

        transport = happy_transport()
        doc, code = self.run_script(
            transport, env=self.env_happy, steps="profile", lock_stale_seconds=900
        )

        self.assertEqual(code, 0)
        self.assertTrue(doc["lock"]["reclaimed"])
        self.assertFalse(lock_path.exists())
        self.assertFalse(rp.profile_lock_path_for(self.project_root, MEMBER_ID).exists())
        self.assertTrue(self.profile_path("IDENTITY.md").is_file())

    def test_unknown_owner_lock_fails_closed(self):
        lock_path = rp.lock_path_for(self.key_file())
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("{not-json", encoding="utf-8")
        old = 1_000_000.0
        os.utime(lock_path, (old, old))

        doc, code = self.run_script(
            happy_transport(), env=self.env_happy, steps="profile", lock_stale_seconds=0
        )
        self.assertEqual(code, 1)
        self.assertEqual(doc["error_code"], "provision_lock_busy")
        self.assertTrue(lock_path.exists())

    def test_release_only_removes_own_generation(self):
        """F5：旧 owner 不能删除新 owner 的锁；释放只认自己的 token。"""
        lock_path = self._tmp / "keys" / "generation.lock"
        handle = rp.acquire_lock(lock_path)
        self.assertTrue(lock_path.exists())

        # 模拟「首 owner 的锁被回收后，第二 owner 建了新锁」。
        replacement = {
            "schema": rp.LOCK_SCHEMA,
            "token": "second-owner-token",
            "pid": 0x7FFFFFF0,
            "started_at": "2020-01-01T00:00:00+00:00",
        }
        lock_path.write_text(json.dumps(replacement), encoding="utf-8")

        self.assertFalse(rp.release_lock(lock_path, handle))  # 旧代际：不删
        self.assertTrue(lock_path.exists())
        self.assertEqual(
            json.loads(lock_path.read_text(encoding="utf-8"))["token"], "second-owner-token"
        )
        # 没有 handle（无法证明所有权）时也绝不删。
        self.assertFalse(rp.release_lock(lock_path))
        self.assertTrue(lock_path.exists())
        # 用第二 owner 自己的 handle 才能释放。
        self.assertTrue(rp.release_lock(lock_path, {"token": "second-owner-token"}))
        self.assertFalse(lock_path.exists())

    def test_same_profile_different_key_root_serialises(self):
        """F5：同一身份档 + 不同 Key 根也必须串行（身份档锁独立于 Key 锁）。"""
        other_key_root = self._tmp / "other-keys"
        profile_lock = rp.profile_lock_path_for(self.project_root, MEMBER_ID)
        profile_lock.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "schema": rp.LOCK_SCHEMA,
            "token": "profile-owner-token",
            "pid": os.getpid(),
            "started_at": "2020-01-01T00:00:00+00:00",
        }
        profile_lock.write_text(json.dumps(record), encoding="utf-8")

        doc, code = self.run_script(
            happy_transport(),
            env=self.env_happy,
            steps="profile",
            key_root=other_key_root,
        )
        self.assertEqual(code, 1)
        self.assertEqual(doc["error_code"], "provision_lock_busy")
        self.assertFalse(self.profile_path("IDENTITY.md").exists())
        self.assertFalse(other_key_root.exists())


# ---------------------------------------------------------------------------
# 原子写：注入失败不留半截文件
# ---------------------------------------------------------------------------


class AtomicWriteTests(RoleProvisionTestCase):
    def test_injected_replace_failure_leaves_no_half_file(self):
        transport = happy_transport()
        with mock.patch("cli.profiles.os.replace", side_effect=OSError("injected")):
            doc, code = self.run_script(transport, env=self.env_happy, steps="profile")

        self.assertEqual(code, 1)
        self.assertEqual(doc["steps"]["profile"]["state"], "failed")
        self.assertEqual(doc["error_code"], "profile_root_invalid")
        self.assertFalse(self.profile_path("IDENTITY.md").exists())
        profile_dir = self.profile_path("IDENTITY.md").parent
        self.assertTrue(profile_dir.is_dir())
        # G2：OS 互斥守卫文件是刻意保留的稳定 inode（删掉会重新引入 ABA 抢占窗口），
        # 不计入“半截身份档”。
        guard_name = rp.PROFILE_LOCK_FILENAME + rp.LOCK_GUARD_SUFFIX
        self.assertEqual(
            [path.name for path in profile_dir.iterdir()], [guard_name]
        )


# ---------------------------------------------------------------------------
# ACK
# ---------------------------------------------------------------------------


class AckTests(RoleProvisionTestCase):
    def test_ack_payload_exactness(self):
        transport = happy_transport()
        doc, code = self.run_script(transport, env=self.env_happy)
        self.assertEqual(code, 0)

        ack_posts = transport.calls_of("POST")
        self.assertEqual(len(ack_posts), 3)
        for call in ack_posts:
            self.assertEqual(_url_path(call["url"]), PROVISION_PATH + "/ack")
            self.assertEqual(call["api_key"], CANARY_OPERATOR)
            self.assertEqual(
                set(call["body"].keys()),
                {
                    "operation_key",
                    "step",
                    "attempt",
                    "revision",
                    "credential_version",
                    "state",
                    "error_code",
                },
            )
            self.assertEqual(call["body"]["operation_key"], OPERATION_KEY)
            self.assertEqual(call["body"]["attempt"], 1)
            self.assertEqual(call["body"]["credential_version"], 1)
            self.assertEqual(call["body"]["state"], "succeeded")
            self.assertIsNone(call["body"]["error_code"])
        # revision 只由**捕获代际 + 本次 ACK 响应**推进：3 → 4 → 5。
        self.assertEqual(
            [call["body"]["revision"] for call in ack_posts], [3, 4, 5]
        )
        self.assertEqual(
            [call["body"]["step"] for call in ack_posts], ["profile", "key_file", "preflight"]
        )

        job_gets = [
            call
            for call in transport.calls_of("GET")
            if _url_path(call["url"]) == PROVISION_PATH
        ]
        # 补正 F1：只在本地副作用之前 GET 一次捕获代际；ACK 阶段不再重新 GET。
        self.assertEqual(len(job_gets), 1)
        for call in job_gets:
            self.assertIn("operation_key=" + OPERATION_KEY, call["url"])
            self.assertEqual(call["api_key"], CANARY_OPERATOR)
        self.assertEqual(doc["job"]["action"], "existing")
        self.assertEqual(
            [
                call
                for call in transport.calls_of("POST")
                if _url_path(call["url"]) == PROVISION_PATH
            ],
            [],
        )

    def test_operator_key_missing_does_not_ack(self):
        transport = happy_transport()
        doc, code = self.run_script(
            transport, env={"TALK_ROLE_API_KEY": CANARY_KEY}
        )

        self.assertEqual(code, 1)
        self.assertEqual(doc["conclusion"], "partial")
        self.assertEqual(doc["error_code"], "operator_key_missing")
        self.assertEqual(
            doc["ack"], {"sent": False, "reason": "operator_key_missing", "results": []}
        )
        self.assertEqual(doc["job"]["action"], "none")
        self.assertEqual(transport.calls_of("POST"), [])
        self.assertEqual(
            [c for c in transport.calls if _url_path(c["url"]) == PROVISION_PATH], []
        )
        # 本地步骤仍然完成。
        self.assertTrue(self.key_file().is_file())
        self.assertTrue(self.profile_path("IDENTITY.md").is_file())

    def test_operator_key_file_is_used_for_ack(self):
        operator_key_file = self._tmp / "operator.key"
        operator_key_file.write_text(CANARY_OPERATOR + "\n", encoding="utf-8")
        transport = happy_transport()
        env = {
            "TALK_ROLE_API_KEY": CANARY_KEY,
            "TALK_OPERATOR_KEY_FILE": str(operator_key_file),
        }
        doc, code = self.run_script(transport, env=env)
        self.assertEqual(code, 0)
        self.assertTrue(doc["ack"]["sent"])
        self.assertEqual(transport.calls_of("POST")[0]["api_key"], CANARY_OPERATOR)

    def test_ack_revision_conflict_is_ack_stale(self):
        transport = happy_transport(ack_status=409)
        doc, code = self.run_script(transport, env=self.env_happy)
        self.assertEqual(code, 1)
        self.assertEqual(doc["conclusion"], "partial")
        # 409 = 代际冲突（revision/attempt/凭据版本），与普通传输失败区分。
        self.assertEqual(doc["error_code"], "ack_stale")
        self.assertFalse(doc["ack"]["sent"])
        self.assertEqual(doc["ack"]["reason"], "ack_stale")


# ---------------------------------------------------------------------------
# 作业存在性（GET → create / --resume / existing；再 ACK）
# ---------------------------------------------------------------------------


def _job_posts(transport):
    return [
        call
        for call in transport.calls_of("POST")
        if _url_path(call["url"]) == PROVISION_PATH
    ]


def _ack_posts(transport):
    return [
        call
        for call in transport.calls_of("POST")
        if _url_path(call["url"]) == PROVISION_PATH + "/ack"
    ]


class JobEnsureTests(RoleProvisionTestCase):
    def test_get_404_creates_job_with_exact_body_then_acks(self):
        transport = happy_transport(
            job_get_responses=[
                rp.HttpResponse(404, {"detail": "provision_job_not_found"}),
                rp.HttpResponse(200, _provision_job()),
            ]
        )
        doc, code = self.run_script(transport, env=self.env_happy)

        self.assertEqual(code, 0)
        self.assertEqual(doc["conclusion"], "applied")
        self.assertEqual(doc["job"]["action"], "created")
        self.assertEqual(doc["job"]["status"], "pending")
        self.assertEqual(doc["job"]["revision"], 3)
        create_posts = _job_posts(transport)
        self.assertEqual(len(create_posts), 1)
        self.assertEqual(
            create_posts[0]["body"],
            {"operation_key": OPERATION_KEY, "resume": False, "steps": None},
        )
        self.assertEqual(create_posts[0]["api_key"], CANARY_OPERATOR)
        self.assertEqual(len(_ack_posts(transport)), 3)
        self.assertTrue(doc["ack"]["sent"])

    def test_resume_true_posts_exact_body_with_selected_steps(self):
        transport = happy_transport()  # GET 200 → 作业已存在
        doc, code = self.run_script(
            transport, env=self.env_happy, steps="key_file,preflight", resume=True
        )

        self.assertEqual(code, 0)
        self.assertEqual(doc["job"]["action"], "resumed")
        posts = _job_posts(transport)
        self.assertEqual(len(posts), 1)
        self.assertEqual(
            posts[0]["body"],
            {
                "operation_key": OPERATION_KEY,
                "resume": True,
                "steps": ["key_file", "preflight"],
            },
        )
        self.assertEqual(posts[0]["api_key"], CANARY_OPERATOR)
        self.assertEqual(len(_ack_posts(transport)), 2)

    def test_resume_with_default_steps_sends_null(self):
        transport = happy_transport()
        doc, code = self.run_script(transport, env=self.env_happy, resume=True)

        self.assertEqual(code, 0)
        self.assertEqual(doc["job"]["action"], "resumed")
        posts = _job_posts(transport)
        self.assertEqual(len(posts), 1)
        self.assertEqual(
            posts[0]["body"],
            {"operation_key": OPERATION_KEY, "resume": True, "steps": None},
        )

    def test_existing_job_without_resume_is_left_untouched(self):
        transport = happy_transport()
        doc, code = self.run_script(transport, env=self.env_happy)

        self.assertEqual(code, 0)
        self.assertEqual(doc["job"]["action"], "existing")
        self.assertEqual(_job_posts(transport), [])

    def test_create_failure_aborts_before_local_side_effects(self):
        """G1：作业创建失败时明确失败并**不继续本地副作用**，也不改判成功。"""
        transport = happy_transport(
            job_get_responses=[rp.HttpResponse(404, None)],
            job_post_status=500,
        )
        doc, code = self.run_script(transport, env=self.env_happy)

        self.assertEqual(code, 1)
        self.assertEqual(doc["conclusion"], "failed")
        self.assertEqual(doc["job"]["action"], "none")
        self.assertEqual(doc["job"]["error_code"], "http_error")
        self.assertIn("HTTP 500", doc["job"]["detail"])
        self.assertEqual(doc["error_code"], "http_error")
        self.assertFalse(doc["ack"]["sent"])
        self.assertEqual(doc["ack"]["reason"], "ack_failed")
        self.assertEqual(_ack_posts(transport), [])
        # 作业无法确认 → 不写身份档、不写 Key 文件。
        self.assertFalse(self.key_file().is_file())
        self.assertFalse(self.profile_path("IDENTITY.md").is_file())

    def test_job_get_unexpected_status_yields_no_ack(self):
        transport = happy_transport(job_get_responses=[rp.HttpResponse(500, None)])
        doc, code = self.run_script(transport, env=self.env_happy)

        self.assertEqual(code, 1)
        self.assertEqual(doc["conclusion"], "failed")
        self.assertEqual(doc["job"]["action"], "none")
        self.assertEqual(doc["job"]["error_code"], "http_error")
        self.assertIn("HTTP 500", doc["job"]["detail"])
        self.assertEqual(doc["error_code"], "http_error")
        self.assertEqual(_ack_posts(transport), [])
        self.assertEqual(_job_posts(transport), [])
        self.assertFalse(self.key_file().is_file())

    def test_resume_pending_status_200_is_accepted(self):
        transport = happy_transport(job_post_status=200)
        doc, code = self.run_script(transport, env=self.env_happy, resume=True)
        self.assertEqual(code, 0)
        self.assertEqual(doc["job"]["action"], "resumed")
        self.assertTrue(doc["ack"]["sent"])

    def test_resume_post_non_2xx_yields_no_ack(self):
        transport = happy_transport(job_post_status=409)
        doc, code = self.run_script(transport, env=self.env_happy, resume=True)
        self.assertEqual(code, 1)
        self.assertEqual(doc["conclusion"], "failed")
        self.assertEqual(doc["job"]["error_code"], "http_error")
        self.assertIn("HTTP 409", doc["job"]["detail"])
        self.assertEqual(_ack_posts(transport), [])
        # G1：非精确终态的 409（此处作业仍是 pending）不得改判成功，也不继续本地副作用。
        self.assertFalse(self.key_file().is_file())

    def test_dry_run_and_no_operator_make_no_job_calls(self):
        dry_transport = FakeTransport()
        doc, code = self.run_script(dry_transport, apply=False, env=self.env_happy)
        self.assertEqual(code, 0)
        self.assertEqual(dry_transport.calls, [])
        self.assertEqual(doc["job"]["action"], "none")

        no_operator = happy_transport()
        doc, code = self.run_script(no_operator, env={"TALK_ROLE_API_KEY": CANARY_KEY})
        self.assertEqual(code, 1)
        self.assertEqual(doc["job"]["action"], "none")
        self.assertEqual(doc["error_code"], "operator_key_missing")
        self.assertEqual(_job_posts(no_operator), [])
        self.assertEqual(
            [
                call
                for call in no_operator.calls_of("GET")
                if _url_path(call["url"]) == PROVISION_PATH
            ],
            [],
        )


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------


class PreflightTests(RoleProvisionTestCase):
    def test_preflight_happy_path_reports_configurable_facts(self):
        transport = happy_transport()
        doc, code = self.run_script(transport, env=self.env_happy, steps="preflight")

        self.assertEqual(code, 0)
        self.assertEqual(doc["steps"]["preflight"]["state"], "succeeded")
        detail = doc["steps"]["preflight"]["detail"]
        self.assertIn("roster_paths=registered", detail)
        self.assertIn("roster_path_fields=registered", detail)
        self.assertIn("profile_files=readable", detail)
        self.assertIn("local_files=3/3", detail)
        self.assertIn("binding_state=bound", detail)
        self.assertIn("runner_id=runner-canary", detail)
        self.assertIn("model_id=model-canary", detail)
        self.assertIn("model_alias=alias-canary", detail)
        self.assertIn("choice_source=creation_operation", detail)
        self.assertIn("binding_fingerprint=verified", detail)
        self.assertIn("cli_entry=not_checked", detail)
        self.assertIn("registration=not_needed", detail)
        # preflight 只发 GET（加 ACK）；名册路径已登记时不发任何注册写；绝不调用 /sync。
        self.assertFalse(any("/sync" in url for url in transport.urls()))
        self.assertEqual(transport.calls_of("PUT"), [])
        self.assertFalse(any(_url_path(url) == ROSTER_PATHS_PATH for url in transport.urls()))

    def test_preflight_binding_missing_fails(self):
        transport = happy_transport(binding={"project_id": PROJECT_ID, "member_id": MEMBER_ID, "binding": None, "binding_state": "member_missing"})
        doc, code = self.run_script(transport, env=self.env_happy, steps="preflight")
        self.assertEqual(code, 1)
        self.assertEqual(doc["error_code"], "identity_mismatch")
        self.assertEqual(doc["steps"]["preflight"]["state"], "failed")

    def test_preflight_binding_projection_mismatch_fails(self):
        transport = happy_transport(binding=_binding_out(model_id="model-other"))
        doc, code = self.run_script(transport, env=self.env_happy, steps="preflight")
        self.assertEqual(code, 1)
        self.assertEqual(doc["error_code"], "identity_mismatch")

    def test_preflight_roster_row_missing_fails(self):
        transport = happy_transport(roster_responses=[rp.HttpResponse(200, [])])
        doc, code = self.run_script(transport, env=self.env_happy, steps="preflight")
        self.assertEqual(code, 1)
        self.assertEqual(doc["error_code"], "identity_mismatch")

    def test_single_role_registration_calls_roster_paths_and_fails_if_not_reflected(self):
        # 名册路径未登记：用 operator 凭据对本角色调用 provision/roster-paths；
        # 登记后名册仍未回填 → preflight 必须失败，绝不假装成功。
        transport = happy_transport(roster_responses=[rp.HttpResponse(200, [_roster_row(paths=False)])])
        doc, code = self.run_script(transport, env=self.env_happy, steps="profile,preflight")

        self.assertEqual(code, 1)
        self.assertEqual(doc["conclusion"], "partial")
        preflight = doc["steps"]["preflight"]
        self.assertEqual(preflight["state"], "failed")
        detail = preflight["detail"]
        self.assertIn("roster_paths=registration_attempted", detail)
        self.assertIn("roster_path_fields=not_reflected", detail)
        self.assertIn("registration=roster_paths_endpoint", detail)

        posts = [
            call
            for call in transport.calls_of("POST")
            if _url_path(call["url"]) == ROSTER_PATHS_PATH
        ]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["api_key"], CANARY_OPERATOR)
        self.assertEqual(
            set(posts[0]["body"].keys()),
            {"operation_key", "identity_path", "soul_path", "user_path"},
        )
        self.assertEqual(posts[0]["body"]["operation_key"], OPERATION_KEY)
        self.assertEqual(
            posts[0]["body"],
            {"operation_key": OPERATION_KEY, **ROSTER_RELATIVE_PATHS},
        )
        self.assertEqual(
            posts[0]["body"]["identity_path"],
            f".talk/agents/{member_dir_name(MEMBER_ID)}/IDENTITY.md",
        )
        # 不再用 PUT .../profile 做登记，也绝不调用全量 /sync。
        self.assertEqual(transport.calls_of("PUT"), [])
        self.assertFalse(any(_url_path(url) == PROFILE_PATH for url in transport.urls()))
        self.assertFalse(any("/sync" in url for url in transport.urls()))

    def test_single_role_registration_passes_when_roster_paths_refresh(self):
        transport = happy_transport(
            roster_responses=[
                rp.HttpResponse(200, [_roster_row(paths=False)]),
                rp.HttpResponse(200, [_roster_row(paths=True)]),
            ]
        )
        doc, code = self.run_script(transport, env=self.env_happy, steps="profile,preflight")
        self.assertEqual(code, 0)
        preflight = doc["steps"]["preflight"]
        self.assertEqual(preflight["state"], "succeeded")
        self.assertIn("roster_paths=registered", preflight["detail"])
        self.assertIn("roster_path_fields=registered", preflight["detail"])
        self.assertIn("registration=roster_paths_endpoint", preflight["detail"])
        posts = [
            call
            for call in transport.calls_of("POST")
            if _url_path(call["url"]) == ROSTER_PATHS_PATH
        ]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["api_key"], CANARY_OPERATOR)
        self.assertEqual(
            posts[0]["body"], {"operation_key": OPERATION_KEY, **ROSTER_RELATIVE_PATHS}
        )
        self.assertEqual(transport.calls_of("PUT"), [])
        self.assertFalse(any("/sync" in url for url in transport.urls()))

    def test_registration_without_operator_is_recoverable_not_succeeded(self):
        transport = happy_transport(roster_responses=[rp.HttpResponse(200, [_roster_row(paths=False)])])
        doc, code = self.run_script(
            transport, env={"TALK_ROLE_API_KEY": CANARY_KEY}, steps="profile,preflight"
        )

        self.assertEqual(code, 1)
        self.assertEqual(doc["conclusion"], "partial")
        self.assertEqual(doc["error_code"], "operator_key_missing")
        self.assertEqual(doc["steps"]["preflight"]["state"], "failed")
        self.assertIn("operator", doc["steps"]["preflight"]["detail"])
        self.assertIn("roster_path_fields=not_reflected", doc["steps"]["preflight"]["detail"])
        self.assertEqual(
            [
                call
                for call in transport.calls_of("POST")
                if _url_path(call["url"]) == ROSTER_PATHS_PATH
            ],
            [],
        )
        self.assertEqual(transport.calls_of("PUT"), [])
        self.assertFalse(any("/sync" in url for url in transport.urls()))

    def test_registration_without_operator_preflight_only_is_partial(self):
        # 即使只有 preflight 一步且未成功，缺 operator 也是可恢复的 partial，而不是 failed。
        transport = happy_transport(roster_responses=[rp.HttpResponse(200, [_roster_row(paths=False)])])
        doc, code = self.run_script(
            transport, env={"TALK_ROLE_API_KEY": CANARY_KEY}, steps="preflight"
        )
        self.assertEqual(code, 1)
        self.assertEqual(doc["conclusion"], "partial")
        self.assertEqual(doc["error_code"], "operator_key_missing")
        self.assertEqual(doc["steps"]["preflight"]["state"], "failed")

    def test_registration_rejection_is_reported_without_retry(self):
        # 例如 422 provision_roster_path_invalid：只报稳定脚本码 + HTTP 状态，不重试、不 /sync。
        transport = happy_transport(
            roster_responses=[rp.HttpResponse(200, [_roster_row(paths=False)])],
            register_status=422,
        )
        doc, code = self.run_script(transport, env=self.env_happy, steps="profile,preflight")

        self.assertEqual(code, 1)
        self.assertEqual(doc["steps"]["preflight"]["state"], "failed")
        self.assertEqual(doc["error_code"], "http_error")
        self.assertIn("HTTP 422", doc["steps"]["preflight"]["detail"])
        posts = [
            call
            for call in transport.calls_of("POST")
            if _url_path(call["url"]) == ROSTER_PATHS_PATH
        ]
        self.assertEqual(len(posts), 1)
        self.assertFalse(any("/sync" in url for url in transport.urls()))

    def test_registration_then_roster_reread_failure_is_http_error(self):
        transport = happy_transport(
            roster_responses=[
                rp.HttpResponse(200, [_roster_row(paths=False)]),
                rp.HttpResponse(500, None),
            ]
        )
        doc, code = self.run_script(transport, env=self.env_happy, steps="profile,preflight")

        self.assertEqual(code, 1)
        self.assertEqual(doc["steps"]["preflight"]["state"], "failed")
        self.assertEqual(doc["error_code"], "http_error")

    def test_cli_executable_present_recorded_but_not_executed(self):
        cli = self._tmp / "fake-cli.exe"
        cli.write_text("not-a-real-binary", encoding="utf-8")
        transport = happy_transport()
        doc, code = self.run_script(
            transport, env=self.env_happy, steps="preflight", cli_executable=cli
        )
        self.assertEqual(code, 0)
        self.assertIn("cli_entry=present", doc["steps"]["preflight"]["detail"])

    def test_cli_executable_missing_fails(self):
        transport = happy_transport()
        doc, code = self.run_script(
            transport,
            env=self.env_happy,
            steps="preflight",
            cli_executable=self._tmp / "no-such-cli.exe",
        )
        self.assertEqual(code, 1)
        self.assertEqual(doc["error_code"], "cli_executable_missing")
        self.assertEqual(doc["steps"]["preflight"]["state"], "failed")


# ---------------------------------------------------------------------------
# CLI / Key 不泄露
# ---------------------------------------------------------------------------


class CliAndSecretTests(RoleProvisionTestCase):
    def _main_argv(self, *, apply: bool = True, steps: str = "key_file"):
        argv = [
            "--project",
            PROJECT_ID,
            "--member",
            MEMBER_ID,
            "--operation-key",
            OPERATION_KEY,
            "--project-root",
            str(self.project_root),
            "--key-root",
            str(self.key_root),
            "--base-url",
            BASE_URL,
            "--steps",
            steps,
            "--json",
        ]
        if apply:
            argv.append("--apply")
        return argv

    def _run_main(self, argv, transport=None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.dict(
            os.environ,
            {"TALK_ROLE_API_KEY": CANARY_KEY, "TALK_OPERATOR_API_KEY": CANARY_OPERATOR},
            clear=False,
        ):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = rp.main(argv, transport=transport if transport is not None else happy_transport())
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_resume_flag_sends_explicit_steps_and_creates_absent_job(self):
        argv = self._main_argv(steps="key_file") + ["--resume"]
        create_transport = happy_transport(
            job_get_responses=[
                rp.HttpResponse(404, None),
                rp.HttpResponse(200, _provision_job()),
            ]
        )
        code, out, _ = self._run_main(argv, transport=create_transport)
        self.assertEqual(code, 0)
        document = json.loads(out.strip())
        self.assertEqual(document["job"]["action"], "created")
        posts = _job_posts(create_transport)
        self.assertEqual(
            posts[0]["body"],
            {"operation_key": OPERATION_KEY, "resume": False, "steps": None},
        )

        resume_transport = happy_transport()
        code, out, _ = self._run_main(
            self._main_argv(steps="key_file") + ["--resume"], transport=resume_transport
        )
        self.assertEqual(code, 0)
        document = json.loads(out.strip())
        self.assertEqual(document["job"]["action"], "resumed")
        posts = _job_posts(resume_transport)
        self.assertEqual(
            posts[0]["body"],
            {"operation_key": OPERATION_KEY, "resume": True, "steps": ["key_file"]},
        )

    def test_json_stdout_is_one_object_and_no_key_material(self):
        code, out, err = self._run_main(self._main_argv())

        self.assertEqual(code, 0)
        document = json.loads(out.strip())
        self.assertEqual(document["schema"], "talk-role-provision-1")
        self.assertEqual(document["mode"], "apply")
        self.assertEqual(document["project_id"], PROJECT_ID)
        self.assertEqual(document["member_id"], MEMBER_ID)
        self.assertEqual(document["operation_key"], OPERATION_KEY)
        self.assertIn("steps", document)
        self.assertIn("ack", document)
        self.assertIn("conclusion", document)
        self.assertNotIn(CANARY_KEY, out)
        self.assertNotIn(CANARY_KEY, err)
        self.assertNotIn(CANARY_OPERATOR, out)
        self.assertNotIn(CANARY_OPERATOR, err)

    def test_dry_run_cli_performs_no_writes_or_http(self):
        argv = self._main_argv(apply=False, steps="profile")
        transport = FakeTransport()
        stdout = io.StringIO()
        with mock.patch.dict(os.environ, {"TALK_ROLE_API_KEY": CANARY_KEY}, clear=False):
            with contextlib.redirect_stdout(stdout):
                code = rp.main(argv, transport=transport)
        self.assertEqual(code, 0)
        self.assertEqual(transport.calls, [])
        self.assertFalse(self.key_root.exists())
        self.assertEqual(list(self.project_root.rglob("*")), [])

    def test_usage_errors_exit_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                rp.main(
                    [
                        "--project",
                        PROJECT_ID,
                        "--member",
                        MEMBER_ID,
                        "--operation-key",
                        OPERATION_KEY,
                        "--steps",
                        "profile,unknown",
                    ]
                )
        self.assertEqual(ctx.exception.code, 2)

    def test_operation_key_must_be_safe_token(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                rp.main(
                    [
                        "--project",
                        PROJECT_ID,
                        "--member",
                        MEMBER_ID,
                        "--operation-key",
                        "short",
                    ]
                )
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
