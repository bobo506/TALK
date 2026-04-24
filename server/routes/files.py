"""File upload/download routes."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, Depends, File as FastAPIFile, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from server.auth import get_current_member
from server.db import STORAGE_DIR, UPLOAD_MAX_MB, get_session
from server.models import File, FileOut, Member, Message

router = APIRouter(prefix="/api/files", tags=["files"])
logger = logging.getLogger("talk.files")

_CHUNK_SIZE = 1024 * 1024
_MAX_BYTES = UPLOAD_MAX_MB * 1024 * 1024
_TEMP_UPLOAD_DIR = ".upload-tmp"


def _safe_content_disposition(filename: str) -> str:
    quoted = quote(filename)
    ascii_fallback = filename.encode("ascii", errors="ignore").decode("ascii") or "download"
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quoted}'


def _resolve_disk_path(relative_path: str) -> Path:
    return (STORAGE_DIR / Path(relative_path)).resolve()


def _make_temp_upload_path() -> Path:
    temp_dir = (STORAGE_DIR / _TEMP_UPLOAD_DIR).resolve()
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir / f"upload-{uuid4()}"


def _find_existing_blob(session: Session, sha256_hex: str) -> File | None:
    candidates = session.exec(
        select(File).where(File.sha256 == sha256_hex).order_by(File.created_at)
    ).all()

    for candidate in candidates:
        disk_path = _resolve_disk_path(candidate.path)
        if disk_path.exists() and disk_path.is_file():
            return candidate

    return None


def purge_expired_files(session: Session, retention_days: int) -> dict[str, int]:
    """Delete expired file blobs and metadata records.

    Messages are intentionally left untouched so file cards can still render from snapshots.
    """
    if retention_days <= 0:
        return {"deleted": 0, "missing_on_disk": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    expired_records = session.exec(
        select(File).where(File.created_at < cutoff).order_by(File.created_at)
    ).all()

    deleted = 0
    missing_on_disk = 0
    expired_ids = {record.id for record in expired_records}
    protected_paths: set[str] = set()

    for record in expired_records:
        still_referenced = session.exec(
            select(File.id).where(File.path == record.path, File.id.notin_(expired_ids)).limit(1)
        ).first()
        if still_referenced is not None:
            protected_paths.add(record.path)

    processed_paths: set[str] = set()
    for record in expired_records:
        disk_path = _resolve_disk_path(record.path)
        if record.path not in processed_paths and record.path not in protected_paths:
            if disk_path.exists():
                disk_path.unlink()
                deleted += 1
            else:
                missing_on_disk += 1
            processed_paths.add(record.path)

        session.delete(record)

    if expired_records:
        session.commit()

    return {"deleted": deleted, "missing_on_disk": missing_on_disk}


async def _iter_file(path: Path):
    async with aiofiles.open(path, "rb") as f:
        while chunk := await f.read(_CHUNK_SIZE):
            yield chunk


@router.post("", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Upload a file and store its metadata."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="filename is required",
        )

    temp_path = _make_temp_upload_path()
    sha256 = hashlib.sha256()
    size_bytes = 0

    try:
        async with aiofiles.open(temp_path, "wb") as out:
            while chunk := await file.read(_CHUNK_SIZE):
                size_bytes += len(chunk)
                if size_bytes > _MAX_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"file exceeds upload_max_mb={UPLOAD_MAX_MB}",
                    )
                sha256.update(chunk)
                await out.write(chunk)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
    finally:
        await file.close()

    mime = file.content_type or mimetypes.guess_type(file.filename)[0]
    sha256_hex = sha256.hexdigest()
    existing = _find_existing_blob(session, sha256_hex)
    file_id = str(uuid4())

    if existing is not None:
        if temp_path.exists():
            temp_path.unlink()
        relative_path = existing.path
        logger.info(
            "File upload dedup hit: sha256=%s existing_file_id=%s new_file_id=%s",
            sha256_hex,
            existing.id,
            file_id,
        )
    else:
        relative_path = (Path("files") / file_id).as_posix()
        disk_path = _resolve_disk_path(relative_path)
        disk_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.replace(disk_path)
        logger.info("File upload dedup miss: sha256=%s file_id=%s", sha256_hex, file_id)

    record = File(
        id=file_id,
        filename=file.filename,
        mime=mime,
        size_bytes=size_bytes,
        sha256=sha256_hex,
        uploader_id=current.id,
        path=relative_path,
    )
    session.add(record)
    session.commit()

    return FileOut(file_id=file_id, filename=record.filename, size_bytes=record.size_bytes)


@router.get("/{file_id}")
async def download_file(
    file_id: str,
    _current: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Download a previously uploaded file."""
    record = session.get(File, file_id)
    if record is None:
        expired_reference = session.exec(
            select(Message.id).where(Message.file_id == file_id).limit(1)
        ).first()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="file expired" if expired_reference is not None else "file not found",
        )

    disk_path = _resolve_disk_path(record.path)
    if not disk_path.exists() or not disk_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="file content missing on disk",
        )

    headers = {"Content-Disposition": _safe_content_disposition(record.filename)}
    return StreamingResponse(
        _iter_file(disk_path),
        media_type=record.mime or "application/octet-stream",
        headers=headers,
    )
