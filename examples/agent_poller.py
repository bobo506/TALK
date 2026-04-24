#!/usr/bin/env python3
"""
TALK — Example Agent Poller

A minimal polling agent that:
1. Registers itself as a member (if not already registered)
2. Optionally uploads and sends one file at startup
3. Polls GET /api/messages every N seconds
4. Echoes text messages and downloads incoming file messages

Revocation handling note:
- Polling agents may see `revoked=true` tombstones when they replay history.
- WebSocket agents should additionally handle `{"type":"revoke","payload":{"id":...,"revoked_by":...}}`
  and stop acting on the revoked message content immediately.

Usage:
    python agent_poller.py --name AI1 --key secret-ai1 --interval 2
    python agent_poller.py --name AI1 --key secret-ai1 --base-url http://192.168.1.100:8000
    python agent_poller.py --name AI1 --key secret-ai1 --send-file ./demo.zip --send-to human:bobo
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
from email.parser import BytesParser
from email.policy import HTTP
from pathlib import Path
from uuid import uuid4


CHUNK_SIZE = 1024 * 1024
DOWNLOAD_ROOT = Path(__file__).resolve().parent / "downloads"


def api(base: str, method: str, path: str, key: str, body: dict | None = None) -> tuple[int, dict | list | str]:
    """Minimal JSON HTTP helper using only stdlib."""
    url = base.rstrip("/") + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-API-Key": key}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def register(base: str, name: str, key: str) -> None:
    member_id = f"agent:{name}"
    status, resp = api(base, "POST", "/api/members", key, {
        "id": member_id,
        "display_name": f"Agent {name}",
        "api_key": key,
    })
    if status == 201:
        print(f"[+] Registered as {member_id}")
    elif status == 200:
        print(f"[=] Self-registration already up to date for {member_id}")
    else:
        print(f"[!] Registration failed ({status}): {resp}")
        sys.exit(1)


def build_download_dir(agent_name: str) -> Path:
    path = DOWNLOAD_ROOT / agent_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_multipart_form(field_name: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"talk-boundary-{uuid4().hex}"
    filename = file_path.name
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8")
    )
    body.extend(f"Content-Type: {mime}\r\n\r\n".encode("utf-8"))
    body.extend(file_path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return bytes(body), boundary


def upload_file(base: str, key: str, file_path: Path) -> dict:
    payload, boundary = build_multipart_form("file", file_path)
    url = base.rstrip("/") + "/api/files"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "X-API-Key": key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        raise RuntimeError(f"Upload failed ({e.code}): {raw}") from e


def send_file_message(base: str, key: str, file_path: Path, target: str) -> None:
    uploaded = upload_file(base, key, file_path)
    status, resp = api(base, "POST", "/api/messages", key, {
        "to": [target],
        "type": "file",
        "content": file_path.name,
        "file_id": uploaded["file_id"],
    })
    if status != 200 and status != 201:
        raise RuntimeError(f"File message send failed ({status}): {resp}")
    print(f"[+] Sent file {file_path.name} to {target} (file_id={uploaded['file_id']})")


def parse_download_filename(headers) -> str:
    disposition = headers.get("Content-Disposition", "")
    if not disposition:
        return ""

    parser = BytesParser(policy=HTTP)
    message = parser.parsebytes(f"Content-Disposition: {disposition}\r\n\r\n".encode("utf-8"))
    filename = message.get_filename()
    return filename or ""


def make_unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    index = 1
    while True:
        alt = directory / f"{stem}_{index}{suffix}"
        if not alt.exists():
            return alt
        index += 1


def download_file(base: str, key: str, file_id: str, fallback_name: str, download_dir: Path) -> Path:
    url = base.rstrip("/") + f"/api/files/{file_id}"
    req = urllib.request.Request(url, headers={"X-API-Key": key}, method="GET")

    try:
        with urllib.request.urlopen(req) as resp:
            filename = parse_download_filename(resp.headers) or fallback_name or f"{file_id}.bin"
            target = make_unique_path(download_dir, filename)
            with open(target, "wb") as f:
                while True:
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
            return target
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        raise RuntimeError(f"Download failed ({e.code}): {raw}") from e


def format_file_reply(saved: Path, caption: str) -> str:
    reply = f"已收到文件「{saved.name}」，已保存到 {saved}"
    if caption:
        reply += f"；附言：「{caption}」"
    return reply


def poll_loop(base: str, name: str, key: str, interval: float) -> None:
    member_id = f"agent:{name}"
    last_id = 0
    download_dir = build_download_dir(name)
    print(f"[*] Polling every {interval}s as {member_id} …")
    print(f"[*] Download directory: {download_dir}")

    while True:
        try:
            status, msgs = api(base, "GET", f"/api/messages?since={last_id}&limit=50", key)
            if status != 200:
                print(f"[!] Poll error ({status}): {msgs}")
                time.sleep(interval)
                continue

            for msg in msgs:
                msg_id = msg["id"]
                if msg_id <= last_id:
                    continue
                last_id = msg_id

                sender = msg["from"]
                to = msg.get("to")
                msg_type = msg.get("type", "text")
                content = msg.get("content", "")
                file_id = msg.get("file_id")
                caption = (msg.get("caption") or "").strip()
                filename = msg.get("filename") or content or file_id
                size_bytes = msg.get("size_bytes")
                mime = msg.get("mime")
                revoked = bool(msg.get("revoked"))
                revoked_by = msg.get("revoked_by")

                if sender == member_id:
                    continue

                if to is not None and member_id not in to:
                    continue

                if revoked:
                    print(f"  ~ [{msg_id}] revoked by {revoked_by or sender}; ignore previous content")
                    continue

                if msg_type == "file" and file_id:
                    file_summary = filename
                    details = []
                    if isinstance(size_bytes, int):
                        details.append(f"{size_bytes} bytes")
                    if mime:
                        details.append(mime)
                    if details:
                        file_summary += f" ({', '.join(details)})"
                    if caption:
                        file_summary += f" | caption: {caption}"
                    print(f"  <- [{msg_id}] {sender} sent file: {file_summary}")
                    saved = download_file(base, key, file_id, filename, download_dir)
                    reply = format_file_reply(saved, caption)
                    api(base, "POST", "/api/messages", key, {
                        "to": [sender],
                        "type": "text",
                        "content": f"@{sender} {reply}",
                    })
                    print(f"  -> [{sender}] {reply}")
                    continue

                print(f"  <- [{msg_id}] {sender}: {content}")
                reply = f"收到！你说的是：「{content}」"
                api(base, "POST", "/api/messages", key, {
                    "to": [sender],
                    "type": "text",
                    "content": f"@{sender} {reply}",
                })
                print(f"  -> [{sender}] {reply}")

        except Exception as e:
            print(f"[!] Error: {e}")

        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="TALK example agent (polling)")
    parser.add_argument("--name", required=True, help="Agent name (e.g. AI1)")
    parser.add_argument("--key", required=True, help="API key for this agent")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="TALK server URL")
    parser.add_argument("--interval", type=float, default=2.0, help="Poll interval in seconds")
    parser.add_argument("--send-file", help="Optional file path to upload and send once at startup")
    parser.add_argument("--send-to", help="Member ID to receive --send-file")
    args = parser.parse_args()

    if args.send_file and not args.send_to:
        parser.error("--send-file requires --send-to")
    if args.send_to and not args.send_file:
        parser.error("--send-to requires --send-file")

    register(args.base_url, args.name, args.key)

    if args.send_file:
        file_path = Path(args.send_file).expanduser().resolve()
        if not file_path.exists() or not file_path.is_file():
            print(f"[!] File not found: {file_path}")
            sys.exit(1)
        send_file_message(args.base_url, args.key, file_path, args.send_to)

    poll_loop(args.base_url, args.name, args.key, args.interval)


if __name__ == "__main__":
    main()
