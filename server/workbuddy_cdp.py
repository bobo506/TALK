"""Bounded, loopback-only check for the WorkBuddy debugging endpoint."""

import ipaddress
import os
import socket
import time
from urllib.parse import urlsplit


def cdp_endpoint_available(timeout=0.6):
    try:
        endpoint = os.environ.get("TALK_WORKBUDDY_CDP_ENDPOINT") or "http://127.0.0.1:9222"
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "http" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path not in ("", "/")):
            return False
        hostname = "127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname
        if not ipaddress.ip_address(hostname).is_loopback or not parsed.port:
            return False
        port = parsed.port
        host = f"[{hostname}]" if ":" in hostname else hostname
        budget = min(max(float(timeout), 0.001), 1.0)
        deadline = time.monotonic() + budget
        request = (f"GET /json/version HTTP/1.1\r\nHost: {host}:{port}\r\n"
                   "Connection: close\r\n\r\n").encode("ascii")

        with socket.create_connection((hostname, port), timeout=budget) as connection:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            connection.settimeout(remaining)
            connection.sendall(request)
            status_line = b""
            while b"\r\n" not in status_line and len(status_line) < 8192:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                connection.settimeout(remaining)
                chunk = connection.recv(min(1024, 8192 - len(status_line)))
                if not chunk:
                    return False
                status_line += chunk
            if b"\r\n" not in status_line:
                return False
            parts = status_line.split(b"\r\n", 1)[0].split(b" ", 2)
            return len(parts) >= 2 and parts[0] in (b"HTTP/1.0", b"HTTP/1.1") and parts[1] == b"200"
    except Exception:
        return False
