import asyncio
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlmodel import select

import server.routes.files as files_route
from server.models import File
from server.routes.files import download_file, purge_expired_files
from tests.test_support import RouteTestCase


class FilesRouteTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.human = self.add_member("human:bobo", api_key="bobo-key", display_name="Bobo")

    def test_first_upload_logs_dedup_miss_and_creates_one_blob(self):
        content = b"same-bytes"

        with self.assertLogs("talk.files", level="INFO") as logs:
            with self.make_client() as client:
                response = client.post(
                    "/api/files",
                    headers={"X-API-Key": "bobo-key"},
                    files={"file": ("first.txt", content, "text/plain")},
                )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(any("dedup miss" in message for message in logs.output))

        with self.session() as session:
            records = session.exec(select(File)).all()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].sha256, hashlib.sha256(content).hexdigest())
        self.assertEqual(len(list((self.storage_dir / "files").iterdir())), 1)

    def test_upload_persists_blob_metadata_and_supports_download(self):
        content = b"hello TALK"

        with self.make_client() as client:
            response = client.post(
                "/api/files",
                headers={"X-API-Key": "bobo-key"},
                files={"file": ("hello.txt", content, "text/plain")},
            )
            self.assertEqual(response.status_code, 201)
            payload = response.json()

            download_response = client.get(
                f"/api/files/{payload['file_id']}",
                headers={"X-API-Key": "bobo-key"},
            )

        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response.content, content)

        with self.session() as session:
            record = session.get(File, payload["file_id"])

        self.assertIsNotNone(record)
        self.assertEqual(record.filename, "hello.txt")
        self.assertEqual(record.mime, "text/plain")
        self.assertEqual(record.size_bytes, len(content))
        self.assertEqual(record.uploader_id, self.human.id)
        self.assertEqual(record.sha256, hashlib.sha256(content).hexdigest())
        self.assertTrue((self.storage_dir / record.path).exists())
        self.assertEqual((self.storage_dir / record.path).read_bytes(), content)

    def test_upload_requires_authentication(self):
        with self.make_client() as client:
            missing_header = client.post(
                "/api/files",
                files={"file": ("hello.txt", b"hello", "text/plain")},
            )
            invalid_key = client.post(
                "/api/files",
                headers={"X-API-Key": "bad-key"},
                files={"file": ("hello.txt", b"hello", "text/plain")},
            )

        self.assertEqual(missing_header.status_code, 422)
        self.assertEqual(invalid_key.status_code, 401)
        self.assertEqual(invalid_key.json()["detail"], "Invalid API key")

    def test_upload_rejects_files_larger_than_max_bytes_without_leaking_state(self):
        original_max_bytes = files_route._MAX_BYTES
        files_route._MAX_BYTES = 3
        try:
            with self.make_client() as client:
                response = client.post(
                    "/api/files",
                    headers={"X-API-Key": "bobo-key"},
                    files={"file": ("huge.bin", b"1234", "application/octet-stream")},
                )

            self.assertEqual(response.status_code, 413)
            self.assertIn("upload_max_mb", response.json()["detail"])

            with self.session() as session:
                self.assertEqual(session.exec(select(File)).all(), [])

            files_dir = self.storage_dir / "files"
            self.assertFalse(files_dir.exists() and any(files_dir.iterdir()))
        finally:
            files_route._MAX_BYTES = original_max_bytes

    def test_uploaded_file_metadata_is_frozen_into_file_message_snapshot(self):
        content = b"build artifact"

        with self.make_client() as client:
            upload_response = client.post(
                "/api/files",
                headers={"X-API-Key": "bobo-key"},
                files={"file": ("build.zip", content, "application/zip")},
            )
            self.assertEqual(upload_response.status_code, 201)
            file_payload = upload_response.json()

            message_response = client.post(
                "/api/messages",
                headers={"X-API-Key": "bobo-key"},
                json={
                    "type": "file",
                    "file_id": file_payload["file_id"],
                    "caption": "build attached",
                },
            )

        self.assertEqual(message_response.status_code, 201)
        message_payload = message_response.json()
        self.assertEqual(message_payload["file_id"], file_payload["file_id"])
        self.assertEqual(message_payload["filename"], "build.zip")
        self.assertEqual(message_payload["size_bytes"], len(content))
        self.assertEqual(message_payload["mime"], "application/zip")
        self.assertEqual(message_payload["content"], "build.zip")

    def test_same_content_second_upload_reuses_existing_blob_and_logs_hit(self):
        content = b"duplicate payload"

        with self.make_client() as client:
            first_response = client.post(
                "/api/files",
                headers={"X-API-Key": "bobo-key"},
                files={"file": ("first.bin", content, "application/octet-stream")},
            )
            self.assertEqual(first_response.status_code, 201)
            first_payload = first_response.json()

            with self.assertLogs("talk.files", level="INFO") as logs:
                second_response = client.post(
                    "/api/files",
                    headers={"X-API-Key": "bobo-key"},
                    files={"file": ("second.bin", content, "application/octet-stream")},
                )

        self.assertEqual(second_response.status_code, 201)
        self.assertTrue(any("dedup hit" in message for message in logs.output))
        second_payload = second_response.json()
        self.assertNotEqual(first_payload["file_id"], second_payload["file_id"])

        with self.session() as session:
            records = session.exec(select(File).order_by(File.created_at)).all()

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].sha256, records[1].sha256)
        self.assertEqual(records[0].path, records[1].path)
        self.assertEqual(len(list((self.storage_dir / "files").iterdir())), 1)

    def test_purge_expired_files_deletes_only_old_records(self):
        now = datetime.now(timezone.utc)
        old_file = self.add_file(
            file_id="expired-file",
            uploader_id=self.human.id,
            filename="old.zip",
            created_at=now - timedelta(days=31),
            content=b"old",
        )
        fresh_file = self.add_file(
            file_id="fresh-file",
            uploader_id=self.human.id,
            filename="fresh.zip",
            created_at=now - timedelta(days=1),
            content=b"new",
        )

        with self.session() as session:
            stats = purge_expired_files(session, 30)

        self.assertEqual(stats["deleted"], 1)
        self.assertFalse((self.storage_dir / old_file.path).exists())
        self.assertTrue((self.storage_dir / fresh_file.path).exists())

    def test_purge_expired_files_keeps_shared_blob_when_fresh_reference_exists(self):
        now = datetime.now(timezone.utc)
        shared_path = "files/shared-blob"
        self.add_file(
            file_id="expired-shared",
            uploader_id=self.human.id,
            filename="old.bin",
            relative_path=shared_path,
            created_at=now - timedelta(days=31),
            content=b"shared",
        )
        fresh_file = self.add_file(
            file_id="fresh-shared",
            uploader_id=self.human.id,
            filename="new.bin",
            relative_path=shared_path,
            created_at=now - timedelta(days=1),
            content=None,
        )

        with self.session() as session:
            stats = purge_expired_files(session, 30)
            remaining = session.exec(select(File).order_by(File.id)).all()

        self.assertEqual(stats["deleted"], 0)
        self.assertEqual(stats["missing_on_disk"], 0)
        self.assertEqual([record.id for record in remaining], [fresh_file.id])
        self.assertTrue((self.storage_dir / shared_path).exists())

    def test_download_distinguishes_expired_from_missing(self):
        self.add_message(
            from_id=self.human.id,
            to_ids=None,
            message_type="file",
            content="old.zip",
            file_id="expired-file",
            caption=None,
            filename="old.zip",
            size_bytes=3,
            mime="application/zip",
        )

        with self.session() as session:
            with self.assertRaises(HTTPException) as expired_ctx:
                asyncio.run(
                    download_file(
                        "expired-file",
                        _current=self.human,
                        session=session,
                    )
                )

        self.assertEqual(expired_ctx.exception.status_code, 404)
        self.assertEqual(expired_ctx.exception.detail, "file expired")

        with self.session() as session:
            with self.assertRaises(HTTPException) as missing_ctx:
                asyncio.run(
                    download_file(
                        "missing-file",
                        _current=self.human,
                        session=session,
                    )
                )

        self.assertEqual(missing_ctx.exception.status_code, 404)
        self.assertEqual(missing_ctx.exception.detail, "file not found")
