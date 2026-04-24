"""SDK exception hierarchy for TALK clients."""

from __future__ import annotations

from typing import Any


class TalkError(Exception):
    """Base exception for TALK SDK errors."""

    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class TalkAuthError(TalkError):
    """Authentication or authorization failure."""


class TalkNotFoundError(TalkError):
    """Requested resource does not exist."""


class TalkValidationError(TalkError):
    """Client-side or server-side validation failure."""


class TalkServerError(TalkError):
    """Unexpected server-side failure."""
