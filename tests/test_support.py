import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import server.db as db
import server.main as main
import server.routes.files as files_route
from server.models import File, Member, Message
from server.ws_hub import hub


class RouteTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        tmp_root = Path(__file__).resolve().parent.parent / ".tmp-tests"
        tmp_root.mkdir(parents=True, exist_ok=True)
        self._tmpdir = Path(tempfile.mkdtemp(prefix="talk-tests-", dir=tmp_root))
        self.storage_dir = self._tmpdir / "storage"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self._tmpdir / "talk.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

        self._old_engine = db.engine
        self._old_db_storage_dir = db.STORAGE_DIR
        self._old_files_storage_dir = files_route.STORAGE_DIR
        self._old_main_engine = main.engine

        db.engine = self.engine
        db.STORAGE_DIR = self.storage_dir
        files_route.STORAGE_DIR = self.storage_dir
        main.engine = self.engine
        hub._connections.clear()

        SQLModel.metadata.create_all(self.engine)

    def tearDown(self):
        db.engine = self._old_engine
        db.STORAGE_DIR = self._old_db_storage_dir
        files_route.STORAGE_DIR = self._old_files_storage_dir
        main.engine = self._old_main_engine
        hub._connections.clear()
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        super().tearDown()

    def session(self) -> Session:
        return Session(self.engine)

    def make_client(self) -> TestClient:
        return TestClient(main.app)

    def add_member(
        self,
        member_id: str,
        *,
        api_key: str,
        display_name: str | None = None,
        poll_hint: int | None = None,
    ) -> Member:
        member = Member(
            id=member_id,
            kind="agent" if member_id.startswith("agent:") else "human",
            display_name=display_name or member_id,
            api_key=api_key,
            poll_hint=poll_hint,
        )
        with self.session() as session:
            session.add(member)
            session.commit()
            session.refresh(member)
            return member

    def add_message(
        self,
        *,
        from_id: str,
        to_ids: str | None,
        message_type: str,
        reply_to: int | None = None,
        content: str | None = None,
        file_id: str | None = None,
        caption: str | None = None,
        filename: str | None = None,
        size_bytes: int | None = None,
        mime: str | None = None,
        created_at: datetime | None = None,
        revoked_at: datetime | None = None,
        revoked_by: str | None = None,
    ) -> Message:
        message = Message(
            from_id=from_id,
            to_ids=to_ids,
            type=message_type,
            reply_to=reply_to,
            content=content,
            file_id=file_id,
            caption=caption,
            filename=filename,
            size_bytes=size_bytes,
            mime=mime,
            created_at=created_at or datetime.now(timezone.utc),
            revoked_at=revoked_at,
            revoked_by=revoked_by,
        )
        with self.session() as session:
            session.add(message)
            session.commit()
            session.refresh(message)
            return message

    def add_file(
        self,
        *,
        file_id: str,
        uploader_id: str,
        filename: str,
        relative_path: str | None = None,
        created_at: datetime | None = None,
        content: bytes | None = None,
        mime: str = "application/octet-stream",
    ) -> File:
        relative = relative_path or f"files/{file_id}"
        record = File(
            id=file_id,
            filename=filename,
            mime=mime,
            size_bytes=len(content or b""),
            sha256="0" * 64,
            uploader_id=uploader_id,
            path=relative,
            created_at=created_at or datetime.now(timezone.utc),
        )
        disk_path = self.storage_dir / relative
        disk_path.parent.mkdir(parents=True, exist_ok=True)
        if content is not None:
            disk_path.write_bytes(content)

        with self.session() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return record
