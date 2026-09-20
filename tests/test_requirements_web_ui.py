"""REQ-2 角色页项目级“开发要求”编辑区：页面契约测试。"""

from pathlib import Path

from tests.test_support import RouteTestCase


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_VERSION = "20260919-c1b-s2-owner"


class RequirementsWebUiTests(RouteTestCase):
    def test_homepage_exposes_project_requirements_editor(self):
        with self.make_client() as client:
            response = client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.text
        for element_id in (
            "requirements-panel",
            "requirements-input",
            "requirements-save-btn",
            "requirements-discard-btn",
            "requirements-retry-btn",
            "requirements-status",
            "requirements-count",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('aria-label="项目开发要求"', html)
        self.assertIn('role="status"', html)
        self.assertIn("项目开发要求", html)
        self.assertIn("不绑定单个角色", html)
        # 示例只作 placeholder，不作为默认值写入。
        self.assertIn('placeholder="例如：Kimi 负责文字/交互/前端', html)
        # R3：文案不再断言 AGENTS 持有既定职责分工，只保留宿主优先级与仓库规范两项。
        self.assertIn("不覆盖 Agent 的宿主系统指令；仓库代码规范（AGENTS.md）仍然有效", html)
        self.assertNotIn("不替代 AGENTS 既定职责", html)
        # 静态资源版本同步刷新缓存。
        self.assertEqual(html.count(STATIC_VERSION), 4)
        self.assertNotIn("20260918-role-1", html)
        self.assertNotIn("20260918-req2-rework", html)
        self.assertNotIn("20260918-req2-requirements", html)
        self.assertNotIn("20260913-task-duration", html)
        self.assertNotIn("20260910-task-chat-layout", html)

    def test_requirements_script_uses_scoped_api_and_safe_rendering(self):
        script = (PROJECT_ROOT / "web" / "workspace.js").read_text(encoding="utf-8")
        stylesheet = (PROJECT_ROOT / "web" / "workspace.css").read_text(encoding="utf-8")

        start = script.index("const REQUIREMENTS_MAX_CHARS")
        end = script.index("function renderWorkspaceList()")
        block = script[start:end]

        # 请求 URL 绑定发起时项目；PATCH 只显式提交这一个字段。
        self.assertIn("apiFetch(`/api/projects/${encodeURIComponent(projectId)}`)", block)
        self.assertIn('method: "PATCH"', block)
        self.assertIn("JSON.stringify({ development_requirements: submitted })", block)
        # 旧后端兼容：读取与保存响应都必须确认字段存在。
        self.assertIn('!("development_requirements" in data)', block)
        # 草稿只存内存，不写入跨账号共享的 localStorage。
        self.assertNotIn("localStorage.", block)
        # 文本展示走 textarea.value / textContent，不拼接 HTML。
        self.assertNotIn("innerHTML", block)
        self.assertIn("input.value =", block)
        self.assertIn("status.textContent = message", block)
        # 状态绑定项目/账号/请求序号。
        self.assertIn("projectId === activeProjectId", block)
        self.assertIn("memberId === myId", block)
        self.assertIn("request === requirementsUI.request", block)
        # R2：判空按 Python str.isspace 合同（含 U+001C–U+001F/U+0085，不含 U+FEFF），不再用 JS trim。
        self.assertIn("REQUIREMENTS_BLANK", block)
        self.assertNotIn("text.trim()", block)
        # R1：可见性统一由 renderTaskDetailsPanel 同步（与角色详情并列），
        # renderWorkspaceList 不再单独调用，群聊分支也经过该同步点。
        self.assertIn("function renderRequirementsPanel()", script)
        app_script = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")
        details_fn = app_script[app_script.index("function renderTaskDetailsPanel()"):app_script.index("async function openTaskHall(")]
        self.assertIn("renderRequirementsPanel();", details_fn)
        list_fn = script[script.index("function renderWorkspaceList()"):script.index("function renderWorkspaceRoleDetails()")]
        self.assertNotIn("renderRequirementsPanel();", list_fn)
        # 样式复用浅色工作台并含窄屏覆盖。
        self.assertIn("#requirements-panel", stylesheet)
        self.assertIn(".requirements-textarea", stylesheet)
        self.assertIn("@media(max-width:700px)", stylesheet)

    def test_whitespace_contract_matches_real_backend(self):
        """R2：真实隔离后端按 Python 空白合同归一（U+001C/U+0085→null，U+FEFF 保留）。"""
        self.add_member("human:ws-probe", api_key="ws-probe-key", display_name="空白探针")

        with self.make_client() as client:
            headers = {"X-API-Key": "ws-probe-key"}
            created = client.post(
                "/api/projects",
                json={"project_id": "prj_req_ws", "display_name": "空白合同"},
                headers=headers,
            )
            self.assertEqual(created.status_code, 201, created.text)
            for raw, expected in (
                ("\u001c", None),
                ("\u001c\u001d\u001e\u001f", None),
                ("\u0085", None),
                ("\u0085\u001c", None),
                ("\ufeff", "\ufeff"),
                ("\u200b", "\u200b"),
                ("a\u001cb", "a\u001cb"),
                ("  保留首尾空格  ", "  保留首尾空格  "),
            ):
                response = client.patch(
                    "/api/projects/prj_req_ws",
                    json={"development_requirements": raw},
                    headers=headers,
                )
                self.assertEqual(response.status_code, 200, f"{raw!r}: {response.text}")
                body = response.json()
                self.assertIn("development_requirements", body)
                self.assertEqual(
                    body["development_requirements"], expected,
                    f"输入 {raw!r} 应归一为 {expected!r}",
                )
