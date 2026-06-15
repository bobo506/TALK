import shutil
import tempfile
import unittest
from pathlib import Path

from cli.profiles import (
    SYSTEM_PROMPT_PROFILE_HEADER,
    AgentProfile,
    agent_profile_dir,
    compose_identity_block,
    compose_system_prompt,
    load_profile,
    member_dir_name,
)


class ProfileLoaderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-profiles-"))
        self.addCleanup(lambda: shutil.rmtree(self._tmp, ignore_errors=True))

    def _write_profile(self, member_id, *, identity=None, soul=None, user=None):
        agent_dir = agent_profile_dir(self._tmp, member_id)
        agent_dir.mkdir(parents=True, exist_ok=True)
        if identity is not None:
            (agent_dir / "IDENTITY.md").write_text(identity, encoding="utf-8")
        if soul is not None:
            (agent_dir / "SOUL.md").write_text(soul, encoding="utf-8")
        if user is not None:
            (agent_dir / "USER.md").write_text(user, encoding="utf-8")

    def test_member_dir_name_sanitizes_colon(self):
        self.assertEqual(member_dir_name("agent:codex"), "agent_codex")
        self.assertEqual(member_dir_name("agent:pi-kimi"), "agent_pi-kimi")

    def test_load_profile_reads_all_three(self):
        self._write_profile(
            "agent:codex",
            identity="# IDENTITY\n决策型代码 Agent",
            soul="# SOUL\n不写汇报体",
            user="# USER\n搭档 pi",
        )
        profile = load_profile(self._tmp, "agent:codex")
        self.assertFalse(profile.is_empty)
        self.assertIn("决策型代码 Agent", profile.identity)
        self.assertIn("不写汇报体", profile.soul)
        self.assertIn("搭档 pi", profile.user)

    def test_load_profile_missing_dir_is_empty(self):
        profile = load_profile(self._tmp, "agent:ghost")
        self.assertTrue(profile.is_empty)
        self.assertIsNone(profile.identity)
        self.assertIsNone(profile.soul)
        self.assertIsNone(profile.user)

    def test_load_profile_optional_user_absent(self):
        self._write_profile("agent:pi", identity="id", soul="soul")
        profile = load_profile(self._tmp, "agent:pi")
        self.assertIsNone(profile.user)
        self.assertFalse(profile.is_empty)

    def test_blank_files_treated_as_none(self):
        self._write_profile("agent:pi", identity="   \n  ", soul="real soul")
        profile = load_profile(self._tmp, "agent:pi")
        self.assertIsNone(profile.identity)
        self.assertEqual(profile.soul, "real soul")

    def test_compose_identity_block(self):
        empty = AgentProfile(member_id="agent:x")
        self.assertEqual(compose_identity_block(empty), "")

        profile = AgentProfile(member_id="agent:x", identity="I", soul="S", user="U")
        block = compose_identity_block(profile)
        self.assertEqual(block, "I\n\nS\n\nU")

    def test_compose_system_prompt_empty_profile_unchanged(self):
        # A member without a profile keeps today's base system prompt byte-for-byte.
        base = "你是 TALK 群里的一个 agent。"
        self.assertEqual(compose_system_prompt(base, AgentProfile(member_id="agent:x")), base)

    def test_compose_system_prompt_appends_background(self):
        base = "你是 TALK 群里的一个 agent。"
        profile = AgentProfile(member_id="agent:pi", identity="ID-pi", soul="不写汇报体", user="队友 codex")
        result = compose_system_prompt(base, profile)

        self.assertTrue(result.startswith(base))
        self.assertIn(SYSTEM_PROMPT_PROFILE_HEADER, result)
        # the profile content is present as background
        self.assertIn("不写汇报体", result)
        self.assertIn("队友 codex", result)
        # base appears before the profile block
        self.assertLess(result.index(base), result.index("不写汇报体"))

    def test_compose_system_prompt_no_base(self):
        profile = AgentProfile(member_id="agent:pi", soul="只有 soul")
        result = compose_system_prompt("", profile)
        self.assertIn(SYSTEM_PROMPT_PROFILE_HEADER, result)
        self.assertIn("只有 soul", result)

    def test_loads_committed_dogfood_profile(self):
        # Real data: the repo's own .talk/ dogfood profile for agent:codex.
        repo_root = Path(__file__).resolve().parent.parent
        profile = load_profile(repo_root, "agent:codex")
        self.assertFalse(profile.is_empty)
        self.assertIn("决策型代码 Agent", profile.identity)
        self.assertIn("汇报体", profile.soul)  # SOUL carries the anti-meta rule


if __name__ == "__main__":
    unittest.main()
