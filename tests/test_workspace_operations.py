"""Operation ledger tests against isolated, in-memory SQLite databases."""
import ast
import inspect as pyinspect
import os
import unittest
from unittest.mock import patch

from sqlalchemy import inspect
from sqlmodel import Session, create_engine

import server.db as db
import server.workspace_operations as operations
from server.models import Member, Project
from server.workspace_operations import (
    WorkspaceOperationError, advance_stage, begin_operation, digest_request,
    get_operation, list_recoverable,
)

ROOT = os.path.abspath(os.path.join(os.path.sep, "synthetic", "workspace"))
OTHER = os.path.abspath(os.path.join(os.path.sep, "synthetic", "candidate"))


class WorkspaceOperationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        with patch.object(db, "engine", self.engine):
            db.init_db()
        with Session(self.engine) as session:
            session.add(Member(id="human:test", kind="human", display_name="Test", api_key="synthetic"))
            session.add(Project(project_id="p1", display_name="Project", maintainer_member_id="human:test"))
            session.commit()

    def code(self, code, function, *args):
        with self.assertRaises(WorkspaceOperationError) as error:
            function(*args)
        self.assertEqual((error.exception.code, str(error.exception)), (code, code))

    def begin(self, session, op="op", project="p1", old=ROOT, candidate=OTHER, revision=1):
        return begin_operation(session, op, project, old, candidate, revision)

    def snapshot(self, session):
        return [row.model_dump() for row in list_recoverable(session)]

    def test_incremental_old_database(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE workspace_operations")
        def snapshot():
            with self.engine.connect() as connection:
                names = [r[0] for r in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
                return {n: (connection.exec_driver_sql(f'PRAGMA table_info("{n}")').fetchall(),
                            connection.exec_driver_sql(f'SELECT * FROM "{n}"').fetchall()) for n in names}
        before = snapshot()
        with patch.object(db, "engine", self.engine):
            db.init_db()
            db.init_db()
        after = snapshot()
        self.assertEqual(set(after) - set(before), {"workspace_operations"})
        for name in before:
            self.assertEqual(before[name], after[name], name)
        self.assertEqual(after["workspace_operations"][1], [])
        names = {i["name"] for i in inspect(self.engine).get_indexes("workspace_operations")}
        self.assertIn("ix_workspace_operations_project_id", names)
        self.assertIn("ux_workspace_operations_active", names)
        print(f"MIGRATION tables {len(before)} -> {len(after)}; old schema/rows identical; projects=1; new rows=0; repeated init=ok")

    def test_begin_idempotence_and_invalid_input(self):
        with Session(self.engine) as s:
            self.begin(s)
            advance_stage(s, "op", "started", "prepared")
            s.commit()
            before = get_operation(s, "op").model_dump()
            self.assertEqual(self.begin(s).model_dump(), before)
            self.code("workspace_operation_conflict", self.begin, s, "op", "p1", ROOT, OTHER, 2)
            self.code("workspace_project_not_found", self.begin, s, "missing", "missing")
            for path in ("relative", ROOT + "\x00bad", ROOT + "x" * 4097):
                self.code("workspace_operation_input_invalid", self.begin, s, "bad", "p1", path)
            self.assertEqual(get_operation(s, "op").model_dump(), before)
            self.assertIsNone(get_operation(s, "bad"))
            self.assertEqual(digest_request("p1", ROOT, OTHER, 1),
                             digest_request("p1", os.path.join(ROOT, "."), OTHER, 1))
            print("BEGIN duplicate=same row/stage/time; different revision=workspace_operation_conflict; missing project and invalid roots=no rows")

    def test_cas_chain_terminal_idempotence(self):
        with Session(self.engine) as s:
            self.begin(s)
            self.code("workspace_stage_conflict", advance_stage, s, "op", "started", "files_staged")
            for source, target in zip(operations.CHAIN, operations.CHAIN[1:]):
                self.assertEqual(advance_stage(s, "op", source, target).stage, target)
                current = get_operation(s, "op").model_dump()
                self.code("workspace_stage_conflict", advance_stage, s, "op", source, target)
                self.assertEqual(get_operation(s, "op").model_dump(), current)
                print(f"CAS {source} -> {target}: success; retry expected={source}: workspace_stage_conflict; unchanged")
            before = get_operation(s, "op").model_dump()
            self.assertEqual(advance_stage(s, "op", None, "completed").model_dump(), before)
            self.code("workspace_stage_conflict", advance_stage, s, "op", "completed", "prepared")
            self.code("workspace_stage_conflict", advance_stage, s, "op", "prepared", "started")
            self.assertEqual(get_operation(s, "op").model_dump(), before)
            print("ILLEGAL skip/backward/terminal=workspace_stage_conflict; complete retry with empty source=no write")

    def test_failed_recovery_and_read_only(self):
        with Session(self.engine) as s:
            for index, source in enumerate(operations.CHAIN[:-1]):
                for target in ("failed", "recovery_required"):
                    op = f"{source}-{target}"
                    project = "p-" + op
                    s.add(Project(project_id=project, display_name=project, maintainer_member_id="human:test"))
                    s.flush()
                    self.begin(s, op, project)
                    for a, b in zip(operations.CHAIN[:index], operations.CHAIN[1:index + 1]):
                        advance_stage(s, op, a, b)
                    before = get_operation(s, op).model_dump()
                    for bad in (None, "custom_error", []):
                        self.code("workspace_operation_input_invalid", advance_stage, s, op, source, target, bad)
                        self.assertEqual(get_operation(s, op).model_dump(), before)
                    advance_stage(s, op, source, target, "workspace_stage_conflict")
                    self.code("workspace_stage_conflict", advance_stage, s, op, target, "completed")
            for index, stage in enumerate(operations.CHAIN[:-1]):
                op = f"normal-{stage}"
                project = "p-" + op
                s.add(Project(project_id=project, display_name=project, maintainer_member_id="human:test"))
                s.flush()
                self.begin(s, op, project)
                for a, b in zip(operations.CHAIN[:index], operations.CHAIN[1:index + 1]):
                    advance_stage(s, op, a, b)
            before = self.snapshot(s)
            self.assertEqual(before, self.snapshot(s))
            self.assertEqual([row for row in before if row["project_id"] == "p-normal-started"],
                             [row.model_dump() for row in list_recoverable(s, "p-normal-started")])
            self.assertEqual(list_recoverable(s, "other"), [])
            self.assertEqual(len(before), 8)
            self.assertEqual({row["stage"] for row in before}, set(operations.RECOVERABLE))
            print("FAIL/RECOVERY all four nonterminal sources: stable error required; recovery cannot advance; failed excluded")
            print("RECOVERABLE snapshots before == after: 8 rows, all 5 recoverable stages; project filter works")

    def test_fault_rollback_and_retry(self):
        with Session(self.engine) as s:
            execute = s.execute
            def execute_then_fail(*args, **kwargs):
                result = execute(*args, **kwargs)
                if str(args[0]).lstrip().upper().startswith(("INSERT", "UPDATE")):
                    raise RuntimeError("injected after write")
                return result
            with patch.object(s, "execute", side_effect=execute_then_fail):
                with self.assertRaises(RuntimeError):
                    self.begin(s)
            s.rollback()
            self.assertIsNone(get_operation(s, "op"))
            self.begin(s)
            s.commit()
            before = get_operation(s, "op").model_dump()
            with patch.object(s, "execute", side_effect=execute_then_fail):
                with self.assertRaises(RuntimeError):
                    advance_stage(s, "op", "started", "prepared")
            s.rollback()
            self.assertEqual(get_operation(s, "op").model_dump(), before)
            self.assertEqual(self.begin(s).model_dump(), before)
            print("ROLLBACK inserted operation absent; UPDATE restored started; repeat begin identical")

    def test_no_external_effects(self):
        tree = ast.parse(pyinspect.getsource(operations))
        imports = {node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)}
        self.assertEqual(imports, {"hashlib", "json", "os"})
        banned = {"open", "system", "popen", "spawn", "fork", "connect", "socket", "read_text", "write_text", "read_bytes", "write_bytes"}
        calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertFalse([node for node in calls if isinstance(node, ast.Name) and node.id in banned])
        self.assertFalse([node for node in calls if isinstance(node, ast.Attribute) and node.attr in banned])
        self.assertFalse(any(word in pyinspect.getsource(operations).lower() for word in ("api_key", "config.toml", "subprocess", "socket")))
        print("EFFECTS AST: no file open/write, subprocess, network, key/config reads; only operation table inserted")


if __name__ == "__main__":
    unittest.main()
