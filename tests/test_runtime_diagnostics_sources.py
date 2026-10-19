"""Isolated tests for source configuration and cursor/provider lifecycle."""

from __future__ import annotations

import base64
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server.runtime_diagnostics_query import (
    QuerySpec,
    RuntimeDiagnosticsError,
)
from server.runtime_diagnostics_sources import (
    CursorCodec,
    RuntimeDiagnosticsProvider,
)

_OWN_ROOT = (
    Path(__file__).resolve().parents[1]
    / ".tmp"
    / "runtime-log-view-v1"
    / "deepseek-backend"
    / "test-roots"
)


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs) -> None:
        self.value = self.value + timedelta(**kwargs)


class CursorCodecTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _Clock(datetime(2026, 10, 18, 20, 0, tzinfo=timezone.utc))

    def test_signed_payload_roundtrip_and_public_fields(self) -> None:
        codec = CursorCodec(
            secret=b"FAKE_SECRET_FOR_CURSOR_ONLY",
            epoch="epoch-a",
            ttl_seconds=60,
            clock=self.clock,
        )
        token = codec.encode({"scope_hash": "s", "filter_hash": "f", "last_log_id": "x"})
        payload = codec.decode(token)
        self.assertEqual(payload["epoch"], "epoch-a")
        self.assertEqual(payload["scope_hash"], "s")
        self.assertNotIn("root", token)
        # The token is opaque; the server revision is bound by hash, not a path.
        self.assertNotIn("FAKE_SECRET", token)

    def test_tampered_signature_is_invalid_cursor(self) -> None:
        codec = CursorCodec(secret=b"FAKE_SECRET_FOR_CURSOR_ONLY", clock=self.clock)
        token = codec.encode({"scope_hash": "s"})
        body, signature = token.split(".")
        replacement = "A" if signature[0] != "A" else "B"
        with self.assertRaises(RuntimeDiagnosticsError) as caught:
            codec.decode(body + "." + replacement + signature[1:])
        self.assertEqual(caught.exception.code, "invalid_cursor")
        self.assertEqual(caught.exception.status_code, 422)

    def test_different_generation_epoch_is_stale(self) -> None:
        clock = self.clock
        old = CursorCodec(secret=b"old-secret", epoch="old-epoch", clock=clock)
        token = old.encode({"scope_hash": "s"})
        restarted = CursorCodec(
            secret=b"new-secret", epoch="new-epoch", clock=clock
        )
        with self.assertRaises(RuntimeDiagnosticsError) as caught:
            restarted.decode(token)
        self.assertEqual(caught.exception.code, "stale_cursor")
        self.assertEqual(caught.exception.status_code, 409)

    def test_expired_cursor_is_stale(self) -> None:
        codec = CursorCodec(
            secret=b"FAKE_SECRET_FOR_CURSOR_ONLY", ttl_seconds=10, clock=self.clock
        )
        token = codec.encode({"scope_hash": "s"})
        self.clock.advance(seconds=11)
        with self.assertRaises(RuntimeDiagnosticsError) as caught:
            codec.decode(token)
        self.assertEqual(caught.exception.code, "stale_cursor")


class SourceConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        _OWN_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = Path(
            tempfile.mkdtemp(prefix="source-config-", dir=str(_OWN_ROOT))
        )
        self.root = self.temp / "logs"
        self.root.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp, ignore_errors=True)

    def _config(self, root: str | None = None) -> dict:
        return {
            "runtime_diagnostics": {
                "sources": [
                    {
                        "project_id": "prj_fake_a",
                        "member_id": "agent:fake-a",
                        "root": root or str(self.root),
                    }
                ]
            }
        }

    def test_missing_or_empty_config_is_unavailable_not_default_root(self) -> None:
        for config in ({}, {"runtime_diagnostics": {}}, {"runtime_diagnostics": {"sources": []}}):
            provider = RuntimeDiagnosticsProvider.from_config(config)
            self.assertIsNone(provider.source_for("prj_fake_a", "agent:fake-a"))
            query = QuerySpec(
                ref=None,
                since=datetime(2026, 10, 17, tzinfo=timezone.utc),
                until=datetime(2026, 10, 18, tzinfo=timezone.utc),
                instance_id=None,
                launch_id=None,
                task_id=None,
                event=None,
                stage=None,
                severity=("error", "warning"),
                limit=20,
            )
            with self.assertRaises(RuntimeDiagnosticsError) as caught:
                provider.list_logs("prj_fake_a", "agent:fake-a", query)
            self.assertEqual(caught.exception.code, "diagnostics_unavailable")
            self.assertEqual(caught.exception.status_code, 503)

    def test_valid_source_is_exact_project_and_member(self) -> None:
        provider = RuntimeDiagnosticsProvider.from_config(self._config())
        source = provider.source_for("prj_fake_a", "agent:fake-a")
        self.assertIsNotNone(source)
        self.assertEqual(source.root, self.root.resolve())
        self.assertIsNone(provider.source_for("prj_fake_a", "agent:other"))
        self.assertIsNone(provider.source_for("prj_other", "agent:fake-a"))

    def test_invalid_configs_are_unavailable(self) -> None:
        invalid_variants = [
            {"runtime_diagnostics": {"sources": "not-a-list"}},
            {"runtime_diagnostics": {"sources": [{"project_id": "p", "member_id": "m"}]}},
            {
                "runtime_diagnostics": {
                    "sources": [
                        {
                            "project_id": "p",
                            "member_id": "m",
                            "root": "relative/path",
                        }
                    ]
                }
            },
            {
                "runtime_diagnostics": {
                    "sources": [
                        {
                            "project_id": "p",
                            "member_id": "m",
                            "root": str(self.root),
                            "extra": "value",
                        }
                    ]
                }
            },
            {
                "runtime_diagnostics": {
                    "sources": [
                        {
                            "project_id": "p",
                            "member_id": "m",
                            "root": str(self.root),
                        },
                        {
                            "project_id": "p",
                            "member_id": "m",
                            "root": str(self.root),
                        },
                    ]
                }
            },
            {
                "runtime_diagnostics": {
                    "sources": [
                        {
                            "project_id": "p",
                            "member_id": "m",
                            "root": "\\\\server\\share\\logs",
                        }
                    ]
                }
            },
        ]
        for config in invalid_variants:
            provider = RuntimeDiagnosticsProvider.from_config(config)
            self.assertIsNone(
                provider.source_for("p", "m"),
                msg=json.dumps(config, ensure_ascii=False),
            )

    def test_source_revision_changes_with_configuration(self) -> None:
        first = RuntimeDiagnosticsProvider.from_config(self._config())
        second = RuntimeDiagnosticsProvider.from_config(self._config())
        other_root = self.temp / "other"
        other_root.mkdir()
        third = RuntimeDiagnosticsProvider.from_config(self._config(str(other_root)))
        self.assertEqual(first.source_revision, second.source_revision)
        self.assertNotEqual(first.source_revision, third.source_revision)
        self.assertNotIn(str(self.root), first.source_revision)

    def test_provider_source_revision_and_cursor_are_independent_of_api_material(self) -> None:
        provider = RuntimeDiagnosticsProvider.from_config(
            self._config(), cursor_codec=CursorCodec(secret=b"cursor-only")
        )
        self.assertIsInstance(provider.source_revision, str)
        self.assertEqual(len(provider.source_revision), 64)
        # A cursor payload carries hashes/revision, never a root or owner token.
        token = provider.cursor_codec.encode(
            {"source_revision": provider.source_revision}
        )
        raw = base64.urlsafe_b64decode(
            token.split(".")[0] + "=" * (-len(token.split(".")[0]) % 4)
        ).decode("utf-8")
        self.assertNotIn(str(self.root), raw)
        self.assertNotIn("owner_token", raw)
        self.assertNotIn("api_key", raw)


if __name__ == "__main__":
    unittest.main()
