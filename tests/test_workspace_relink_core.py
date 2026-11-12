"""Relink integration tests using disposable databases and directories."""
import hashlib
import os
import tempfile
from datetime import datetime, timezone
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect, text, update
from sqlmodel import Session, create_engine

import server.db as db
from server.models import Member, Project, WorkspaceOperation
from server import workspace_operations as ops, workspace_registry as registry
from server import workspace_relink as relink, workspace_relink_files as files


class RelinkTests(unittest.TestCase):
    def setUp(self):
        identity = {"platform": os.name, "machine": "test", "volume_id": 1, "file_id": 1, "collected_at": datetime.now(timezone.utc).isoformat()}
        identity_patch = patch("server.workspace_diagnostics._identity", return_value=identity)
        identity_patch.start()
        self.addCleanup(identity_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.old = self.base / "old"
        self.new = self.base / "new"
        self.old.mkdir()
        self.new.mkdir()
        self.engine = create_engine("sqlite:///" + (self.base / "db.sqlite").as_posix())
        self.addCleanup(self.engine.dispose)
        with patch.object(db, "engine", self.engine):
            db.init_db()
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        self.session.add(Member(id="h", kind="human", display_name="H", api_key="synthetic"))
        self.session.add(Project(project_id="p", display_name="P", maintainer_member_id="h", project_root_path=str(self.old)))
        self.session.commit()
        registry.ensure_registration(self.session, "p")
        self.session.commit()
        self.a = self.new / "a"
        self.b = self.new / "b"
        self.a.write_bytes(b"old-a")
        self.b.write_bytes(b"old-b")
        self.writes = [{"target": str(p), "payload": data, "expected_digest": hashlib.sha256(old).hexdigest()}
                       for p, data, old in ((self.a, b"new-a", b"old-a"), (self.b, b"new-b", b"old-b"))]
        self.args = dict(project_id="p", candidate_root=str(self.new), expected_revision=1,
                         operation_id="op", writes=self.writes, allowed_roots=[str(self.new)])

    def call(self, **kwargs):
        return relink.execute_relink(lambda: Session(self.engine), **(self.args | kwargs))

    def error(self, code, **kwargs):
        with self.assertRaises(relink.WorkspaceRelinkError) as caught:
            self.call(**kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def state(self):
        return (self.session.get(Project, "p", populate_existing=True).project_root_path,
                registry.get_registration(self.session, "p").revision, self.a.read_bytes(), self.b.read_bytes())

    def unchanged(self):
        self.assertEqual(self.state(), (str(self.old), 1, b"old-a", b"old-b"))
        self.assertEqual(list(self.new.glob("*.talk-tmp-*")), [])
        self.assertEqual(list(self.new.glob(".*.talk-tmp-*")), [])

    def test_success_retry_and_conflict(self):
        stages = []
        advance = ops.advance_stage
        def track(session, op, source, target, *args):
            stages.append((source, target))
            return advance(session, op, source, target, *args)
        with patch.object(ops, "advance_stage", side_effect=track):
            result = self.call()
        self.assertEqual(result, dict(operation_id="op", project_id="p", stage="completed", project_root=str(self.new), revision=2))
        self.assertEqual(stages, [("started", "prepared"), ("prepared", "files_staged"), ("files_staged", "committed"), ("committed", "completed")])
        self.assertEqual(self.state(), (str(self.new), 2, b"new-a", b"new-b"))
        stamps = (self.a.stat().st_mtime_ns, self.b.stat().st_mtime_ns)
        self.assertEqual(self.call(), result)
        self.assertEqual(stamps, (self.a.stat().st_mtime_ns, self.b.stat().st_mtime_ns))
        self.error("workspace_operation_conflict", expected_revision=2)
        print("SUCCESS stages=started>prepared>files_staged>committed>completed; retry unchanged; mismatch=workspace_operation_conflict")

    def test_prepared_committed_before_files_and_crash(self):
        def crash(*args):
            with Session(self.engine) as observer:
                self.assertEqual(ops.get_operation(observer, "op").stage, "prepared")
                self.assertEqual(observer.get(Project, "p").project_root_path, str(self.old))
            raise KeyboardInterrupt("simulated crash")
        with patch.object(files, "prepare_write", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                self.call()
        with Session(self.engine) as observer:
            self.assertEqual(ops.get_operation(observer, "op").stage, "prepared")
            self.assertEqual(observer.get(Project, "p").project_root_path, str(self.old))
        with patch.object(files, "prepare_write", side_effect=AssertionError("retry wrote files")):
            self.assertEqual(self.call()["stage"], "prepared")
        self.unchanged()
        print("CRASH T1 committed: observer sees prepared; old root; retry no writes")

    def test_t2_commit_failure(self):
        count = [0]
        class FailSecondCommit(Session):
            def commit(inner):
                count[0] += 1
                if count[0] == 2:
                    raise RuntimeError("injected T2 commit failure")
                return super().commit()
        with self.assertRaises(relink.WorkspaceRelinkError) as caught:
            relink.execute_relink(lambda: FailSecondCommit(self.engine), **self.args)
        self.assertEqual(caught.exception.code, "workspace_write_failed")
        self.assertEqual(set(caught.exception.rolled_back), {str(self.a), str(self.b)})
        self.unchanged()
        with Session(self.engine) as observer:
            self.assertEqual(ops.get_operation(observer, "op").stage, "failed")
        print("T2 commit injected failure -> rollback both files, old DB, T3 failed committed")

    def test_each_t2_stage_failure_restores_prior_state(self):
        advance = ops.advance_stage
        for stage in ("files_staged", "committed", "completed"):
            with self.subTest(stage=stage):
                def injected(session, op, source, target, *args):
                    result = advance(session, op, source, target, *args)
                    if target == stage:
                        raise RuntimeError("injected T2 stage error")
                    return result
                with patch.object(ops, "advance_stage", side_effect=injected):
                    error = self.error("workspace_write_failed", operation_id="fail-" + stage)
                self.assertEqual(set(error.rolled_back), {str(self.a), str(self.b)})
                self.unchanged()
                with Session(self.engine) as observer:
                    self.assertEqual(ops.get_operation(observer, "fail-" + stage).stage, "failed")
                print("T2 stage", stage, "injected after SQL -> file rollback, DB old, T3 failed")

    def test_completed_operation_does_not_block_new(self):
        self.call()
        target = self.new / "third"
        result = self.call(operation_id="next", expected_revision=2,
                           writes=[{"target": str(target), "payload": b"third", "expected_digest": None}])
        self.assertEqual((result["stage"], result["revision"], target.read_bytes()), ("completed", 3, b"third"))
        print("INDEX completed operation permits another operation")

    def test_nonterminal_and_busy(self):
        ops.begin_operation(self.session, "other", "p", str(self.old), str(self.new), 1)
        self.session.commit()
        self.assertEqual(self.call(operation_id="other")["stage"], "started")
        self.error("workspace_busy")
        self.unchanged()
        print("SERIAL existing=started no effects; other ID=workspace_busy")

    def test_different_projects_and_terminal_index(self):
        self.session.add(Project(project_id="p2", display_name="P2", maintainer_member_id="h", project_root_path=str(self.old)))
        self.session.flush()
        registry.ensure_registration(self.session, "p2")
        ops.begin_operation(self.session, "other", "p", str(self.old), str(self.new), 1)
        ops.begin_operation(self.session, "second", "p2", str(self.old), str(self.new), 1)
        ops.advance_stage(self.session, "other", "started", "failed", "workspace_write_failed")
        ops.begin_operation(self.session, "third", "p", str(self.old), str(self.new), 1)
        self.session.commit()
        names = {i["name"] for i in inspect(self.engine).get_indexes("workspace_operations")}
        self.assertIn("ux_workspace_operations_active", names)
        with patch.object(db, "engine", self.engine):
            db.init_db()
        print("INDEX active unique present; repeated init; failed permits new; distinct projects permitted")

    def test_preflight(self):
        cases = [("workspace_project_not_found", {"project_id": "missing"}),
                 ("workspace_revision_conflict", {"expected_revision": 2}),
                 ("workspace_root_missing", {"candidate_root": str(self.base / "missing")}),
                 ("workspace_root_invalid", {"candidate_root": "relative"}),
                 ("workspace_path_refused", {"writes": [{"target": str(self.base / "out"), "payload": b"a", "expected_digest": None}]}),
                 ("workspace_file_too_large", {"writes": [{"target": str(self.a), "payload": b"x" * (1024 * 1024 + 1), "expected_digest": None}]})]
        for code, args in cases:
            with self.subTest(code=code):
                self.error(code, **args)
                self.unchanged()
                self.assertIsNone(ops.get_operation(self.session, "op"))
        for info, code in [({"status": "inaccessible"}, "workspace_root_inaccessible"),
                           ({"status": "ok", "identity": None}, "workspace_identity_unknown")]:
            with patch.object(relink, "inspect_root", return_value=info):
                self.error(code)
        self.session.add(Project(project_id="unregistered", display_name="U", maintainer_member_id="h"))
        self.session.commit()
        self.error("workspace_registration_not_found", project_id="unregistered")
        self.unchanged()
        self.assertIsNone(ops.get_operation(self.session, "op"))
        print("PREFLIGHT missing project/registration, revision, root missing/invalid/inaccessible, identity unknown, outside, size: expected codes; no writes")

    def test_prepare_conflict(self):
        self.writes[1]["expected_digest"] = "wrong"
        self.error("workspace_file_conflict")
        self.unchanged()
        self.assertEqual(ops.get_operation(self.session, "op").stage, "failed")
        print("PREPARE second conflict; first temporary removed; stage=failed")

    def test_commit_failure(self):
        replace = os.replace
        count = [0]
        def broken(src, dst):
            count[0] += 1
            if count[0] == 2:
                raise OSError("injected")
            return replace(src, dst)
        with patch.object(files.os, "replace", side_effect=broken):
            self.error("workspace_write_failed")
        self.unchanged()
        self.assertEqual(ops.get_operation(self.session, "op").stage, "failed")
        print("COMMIT second replace failure; first restored; stage=failed")

    def test_cas_failure(self):
        batch = files.commit_batch
        def interfere(receipts, roots):
            result = batch(receipts, roots)
            with Session(self.engine) as other:
                other.execute(update(Project).where(Project.project_id == "p").values(project_root_path="changed"))
                other.commit()
            return result
        with patch.object(files, "commit_batch", side_effect=interfere):
            self.error("workspace_revision_conflict")
        self.assertEqual(self.state(), ("changed", 1, b"old-a", b"old-b"))
        self.assertEqual(ops.get_operation(self.session, "op").stage, "failed")
        print("CAS conflict preserves competing root; files restored; stage=failed")

    def test_caller_rollback_does_not_change_committed_result(self):
        self.call()
        self.session.rollback()
        self.assertEqual(self.state(), (str(self.new), 2, b"new-a", b"new-b"))
        print("CALLER rollback after return leaves committed DB and files unchanged")

    def test_registration_write_then_exception(self):
        save = registry.save_identity
        def save_then_fail(*args):
            save(*args)
            raise RuntimeError("injected after revision update")
        with patch.object(registry, "save_identity", side_effect=save_then_fail):
            self.error("workspace_write_failed")
        self.unchanged()
        self.assertEqual(ops.get_operation(self.session, "op").stage, "failed")
        print("REGISTRY injected post-update error; project, revision, files restored")

    def test_different_project_executes_while_busy(self):
        other_root = self.base / "other"
        other_root.mkdir()
        self.session.add(Project(project_id="p2", display_name="P2", maintainer_member_id="h", project_root_path=str(self.old)))
        self.session.flush()
        registry.ensure_registration(self.session, "p2")
        ops.begin_operation(self.session, "pending", "p", str(self.old), str(self.new), 1)
        self.session.commit()
        result = self.call(project_id="p2", operation_id="second", candidate_root=str(other_root),
                           allowed_roots=[str(other_root)], writes=[{"target": str(other_root / "file"),
                           "payload": b"ok", "expected_digest": None}])
        self.assertEqual(result["stage"], "completed")
        self.assertEqual((other_root / "file").read_bytes(), b"ok")
        print("SERIAL another project executed while p has active operation")

    def test_recovery_failure(self):
        with patch.object(registry, "save_identity", side_effect=registry.WorkspaceRegistryError("workspace_revision_conflict")), \
             patch.object(files, "rollback_write", side_effect=files.WorkspaceFileError("workspace_recovery_required")):
            error = self.error("workspace_recovery_required")
        self.assertEqual(set(error.not_rolled_back), {str(self.a), str(self.b)})
        self.assertEqual(ops.get_operation(self.session, "op").stage, "recovery_required")
        self.assertEqual(self.state(), (str(self.old), 1, b"new-a", b"new-b"))
        print("RECOVERY rollback injected failure; two paths reported; stage=recovery_required")


if __name__ == "__main__":
    unittest.main()
