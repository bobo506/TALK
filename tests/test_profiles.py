import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cli.profiles import (
    SYSTEM_PROMPT_PROFILE_HEADER,
    AgentProfile,
    agent_profile_dir,
    atomic_write_text,
    compose_identity_block,
    compose_system_prompt,
    load_profile,
    member_dir_name,
    write_profile_file_atomic,
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


class AtomicProfileWriteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="talk-profiles-atomic-"))
        self.addCleanup(lambda: shutil.rmtree(self._tmp, ignore_errors=True))

    def test_write_profile_file_atomic_writes_and_replaces(self):
        path = write_profile_file_atomic(self._tmp, "agent:codex", "identity", "first")
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_text(encoding="utf-8"), "first")
        self.assertEqual(
            path,
            (agent_profile_dir(self._tmp, "agent:codex") / "IDENTITY.md").resolve(),
        )

        write_profile_file_atomic(self._tmp, "agent:codex", "identity", "second")
        self.assertEqual(path.read_text(encoding="utf-8"), "second")

    def test_write_profile_file_atomic_no_temp_leftovers(self):
        write_profile_file_atomic(self._tmp, "agent:codex", "soul", "soul text")
        agent_dir = agent_profile_dir(self._tmp, "agent:codex")
        self.assertEqual(sorted(item.name for item in agent_dir.iterdir()), ["SOUL.md"])

    def test_write_profile_file_atomic_rejects_escape(self):
        with self.assertRaises(ValueError):
            write_profile_file_atomic(self._tmp, "agent:../escape", "identity", "x")

    def test_atomic_write_text_creates_parents(self):
        target = self._tmp / "nested" / "file.txt"
        result = atomic_write_text(target, "内容", encoding="utf-8")
        self.assertEqual(result, target)
        self.assertEqual(target.read_text(encoding="utf-8"), "内容")

    def test_atomic_write_text_failure_leaves_no_half_file(self):
        target = self._tmp / "out.txt"
        with mock.patch("cli.profiles.os.replace", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                atomic_write_text(target, "partial")
        self.assertFalse(target.exists())
        self.assertEqual(list(self._tmp.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
