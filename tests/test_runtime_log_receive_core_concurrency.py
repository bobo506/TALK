"""Cross-store/concurrency tests for the B2a runtime log receive core.

These tests use independent SQLAlchemy engines/connections to the same real
temporary SQLite/WAL database.  They deliberately do not rely on a Python lock
inside one core object: the database write transaction and unique constraints
must be the authority.
"""

from __future__ import annotations

import threading
import unittest
from typing import Any, Callable

from server.runtime_log_receive_core import (
    RuntimeLogBatchReceipt,
    RuntimeLogLimits,
    RuntimeLogReceiveError,
)

try:  # package/discovery import (project root on sys.path)
    from tests.test_runtime_log_receive_core import (
        CoreFixture,
        _MAINTAINER_KEY,
        _ROLE_KEY,
    )
except ImportError:  # direct script execution from tests/
    from test_runtime_log_receive_core import (  # type: ignore[no-redef]
        CoreFixture,
        _MAINTAINER_KEY,
        _ROLE_KEY,
    )


class ConcurrencyTests(CoreFixture):
    def setUp(self) -> None:
        super().setUp()
        self.seed_base()
        self.scope = self.role_scope()
        self.source = self.register(self.scope)

    def _worker_engine(self):
        return self._make_engine(timeout=30)

    def _run_parallel(
        self, functions: list[Callable[[], Any]]
    ) -> tuple[list[Any], list[BaseException | None]]:
        barrier = threading.Barrier(len(functions), timeout=20)
        results: list[Any] = [None] * len(functions)
        errors: list[BaseException | None] = [None] * len(functions)

        def _runner(index: int, function: Callable[[], Any]) -> None:
            engine = self._worker_engine()
            try:
                barrier.wait()
                results[index] = function()
            except BaseException as exc:  # noqa: BLE001 - captured for assertions
                errors[index] = exc
            finally:
                engine.dispose()

        threads = [
            threading.Thread(target=_runner, args=(index, function), daemon=True)
            for index, function in enumerate(functions)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=40)
            self.assertFalse(thread.is_alive(), "concurrent worker did not finish")
        return results, errors

    def _ingest_with_engine(self, engine, prepared):
        core = self._core(engine=engine)
        return core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared)

    def test_same_batch_two_stores_commits_once(self) -> None:
        prepared = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="race-same")],
            batch_id="race-same-batch",
            batch_seq=1,
        )
        engines = [self._worker_engine(), self._worker_engine()]
        results, errors = self._run_parallel(
            [
                lambda engine=engines[0]: self._ingest_with_engine(engine, prepared),
                lambda engine=engines[1]: self._ingest_with_engine(engine, prepared),
            ]
        )
        for engine in engines:
            engine.dispose()
        unexpected = [
            error
            for error in errors
            if error is not None
            and not (
                isinstance(error, RuntimeLogReceiveError)
                and error.code == "database_busy"
            )
        ]
        self.assertEqual(unexpected, [])
        receipts = [item for item in results if isinstance(item, RuntimeLogBatchReceipt)]
        self.assertGreaterEqual(len(receipts), 1)
        self.assertLessEqual(sum(1 for item in receipts if not item.replayed), 1)
        self.assertEqual(self.count_rows("runtime_log_batches"), 1)
        self.assertEqual(self.count_rows("runtime_log_events"), 1)
        row = self.source_row(self.scope)
        self.assertEqual(row.batch_count, 1)
        self.assertEqual(row.event_count, 1)
        self.assertEqual(row.next_event_seq, 2)

    def test_same_event_across_batches_reuses_one_row(self) -> None:
        first = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="race-event", payload={"n": 1})],
            batch_id="race-event-1",
            batch_seq=1,
        )
        second = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="race-event", payload={"n": 1})],
            batch_id="race-event-2",
            batch_seq=2,
        )
        engines = [self._worker_engine(), self._worker_engine()]
        results, errors = self._run_parallel(
            [
                lambda engine=engines[0]: self._ingest_with_engine(engine, first),
                lambda engine=engines[1]: self._ingest_with_engine(engine, second),
            ]
        )
        for engine in engines:
            engine.dispose()
        self.assertEqual(errors, [None, None])
        receipts = [item for item in results if isinstance(item, RuntimeLogBatchReceipt)]
        self.assertEqual(len(receipts), 2)
        self.assertEqual(receipts[0].events[0].event_uid, receipts[1].events[0].event_uid)
        self.assertEqual(receipts[0].events[0].received_seq, 1)
        self.assertEqual(receipts[1].events[0].received_seq, 1)
        self.assertEqual(self.count_rows("runtime_log_batches"), 2)
        self.assertEqual(self.count_rows("runtime_log_events"), 1)
        row = self.source_row(self.scope)
        self.assertEqual(row.batch_count, 2)
        self.assertEqual(row.event_count, 1)
        self.assertEqual(row.next_event_seq, 2)

    def test_global_batch_quota_allows_exactly_one_of_two(self) -> None:
        tight = RuntimeLogLimits(
            max_batches_total=1,
            source_row_overhead_bytes=0,
            batch_row_overhead_bytes=0,
            event_row_overhead_bytes=0,
        )
        first = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="race-quota-1")],
            batch_id="race-quota-1",
            batch_seq=1,
        )
        second = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="race-quota-2")],
            batch_id="race-quota-2",
            batch_seq=2,
        )
        engines = [self._worker_engine(), self._worker_engine()]

        def _ingest(engine, prepared):
            core = self._core(engine=engine, limits=tight)
            return core.ingest_batch(raw_api_key=_ROLE_KEY, batch=prepared)

        results, errors = self._run_parallel(
            [
                lambda engine=engines[0]: _ingest(engine, first),
                lambda engine=engines[1]: _ingest(engine, second),
            ]
        )
        for engine in engines:
            engine.dispose()
        successes = [item for item in results if isinstance(item, RuntimeLogBatchReceipt)]
        failures = [error for error in errors if isinstance(error, RuntimeLogReceiveError)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIn(failures[0].code, ("quota_global_batches", "database_busy"))
        self.assertEqual(self.count_rows("runtime_log_batches"), 1)
        self.assertEqual(self.count_rows("runtime_log_events"), 1)
        self.assertEqual(self.source_row(self.scope).event_count, 1)

    def test_concurrent_unique_sequences_and_batches(self) -> None:
        count = 6
        prepared = [
            self.batch(
                scope=self.scope,
                records=[
                    self.role_record(
                        log_id=f"race-seq-{index}",
                        payload={"index": index},
                    )
                ],
                batch_id=f"race-seq-batch-{index}",
                batch_seq=index + 1,
            )
            for index in range(count)
        ]
        engines = [self._worker_engine() for _ in range(count)]
        results, errors = self._run_parallel(
            [
                lambda index=index: self._ingest_with_engine(engines[index], prepared[index])
                for index in range(count)
            ]
        )
        for engine in engines:
            engine.dispose()
        self.assertEqual(errors, [None] * count)
        receipts = [item for item in results if isinstance(item, RuntimeLogBatchReceipt)]
        self.assertEqual(len(receipts), count)
        seqs = sorted(
            event.received_seq for receipt in receipts for event in receipt.events
        )
        self.assertEqual(seqs, list(range(1, count + 1)))
        self.assertEqual(self.count_rows("runtime_log_batches"), count)
        self.assertEqual(self.count_rows("runtime_log_events"), count)
        row = self.source_row(self.scope)
        self.assertEqual(row.batch_count, count)
        self.assertEqual(row.event_count, count)
        self.assertEqual(row.next_event_seq, count + 1)

    def test_concurrent_source_cap_keeps_one_new_source(self) -> None:
        # setUp already used one of the two allowed source slots.
        cap_two = RuntimeLogLimits(
            max_sources_total=2,
            source_row_overhead_bytes=0,
            batch_row_overhead_bytes=0,
            event_row_overhead_bytes=0,
        )
        first_scope = self.manager_scope(host="host-one")
        second_scope = self.manager_scope(host="host-two")
        engines = [self._worker_engine(), self._worker_engine()]

        def _register(engine, scope):
            core = self._core(engine=engine, limits=cap_two)
            return core.register_source(raw_api_key=_MAINTAINER_KEY, scope=scope)

        results, errors = self._run_parallel(
            [
                lambda engine=engines[0]: _register(engine, first_scope),
                lambda engine=engines[1]: _register(engine, second_scope),
            ]
        )
        for engine in engines:
            engine.dispose()
        successes = [item for item in results if item is not None]
        failures = [error for error in errors if isinstance(error, RuntimeLogReceiveError)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIn(failures[0].code, ("quota_source_count", "database_busy"))
        self.assertEqual(self.count_rows("runtime_log_sources"), 2)

    def test_concurrent_revoke_and_ingest_are_serialized(self) -> None:
        prepared = self.batch(
            scope=self.scope,
            records=[self.role_record(log_id="race-revoke")],
            batch_id="race-revoke-batch",
            batch_seq=1,
        )
        engines = [self._worker_engine(), self._worker_engine()]

        def _revoke(engine):
            core = self._core(engine=engine)
            return core.revoke_source(
                raw_api_key=_MAINTAINER_KEY,
                scope=self.scope,
                expected_revision=1,
            )

        results, errors = self._run_parallel(
            [
                lambda: _revoke(engines[0]),
                lambda: self._ingest_with_engine(engines[1], prepared),
            ]
        )
        for engine in engines:
            engine.dispose()
        ingest = results[1]
        ingest_rejected = (
            isinstance(errors[1], RuntimeLogReceiveError)
            and errors[1].code in ("source_revoked", "source_revision_conflict")
        )
        if ingest_rejected:
            self.assertEqual(self.count_rows("runtime_log_batches"), 0)
        else:
            self.assertIsInstance(ingest, RuntimeLogBatchReceipt)
            self.assertEqual(self.count_rows("runtime_log_batches"), 1)
        # In both serial orders the source is revoked and the historical rows
        # (if the ingest won the lock) are retained, never erased.
        row = self.source_row(self.scope)
        self.assertFalse(bool(row.active))
        self.assertEqual(row.revision, 2)
        expected_events = 0 if ingest_rejected else 1
        self.assertEqual(self.count_rows("runtime_log_events"), expected_events)


if __name__ == "__main__":
    unittest.main()
