"""Per-request TALK bridge context carried by ``contextvars``.

The streamable-HTTP ``/mcp`` endpoint must not mutate the process-global
``os.environ`` to route one member's tool call: with a shared environment,
every concurrent request would have to serialize behind one lock (and one
long ``talk_wait_tasks`` would block every other member's ``tools/call``
for up to 600 seconds, starving the shared thread pool).

Instead, each request installs a context-local override map via
:func:`call_context`.  Bridge readers resolve variables through :func:`env`,
which checks the current context first and falls back to ``os.environ``
when the variable is not overridden — so the stdio terminal entry
(``bridges/talk_terminal_mcp.py``) keeps setting the process environment
exactly as before and behaves unchanged.

An override value of ``None`` means *cleared*: the variable reads as unset
inside the context even when ``os.environ`` holds a stale value (used to
suppress inherited ``TALK_PROJECT_ID`` / ``TALK_MEMBER_ID`` hints).

An explicit empty string (``""``) is a real override value, returned verbatim
by :func:`env` — so callers can tell an explicitly-empty variable apart from
an unset one (``None``) and preserve the original stdio semantics (e.g. an
explicitly empty ``TALK_BASE_URL`` stays empty instead of falling back to the
default address).  The same holds on the stdio path itself: ``os.environ``
values are read with ``dict.get`` semantics, never truthiness coercion.
"""

from __future__ import annotations

import contextlib
import os
from typing import Iterator

from contextvars import ContextVar

#: The active override map for the current execution context (``None`` when
#: no per-request context is installed, i.e. every read falls back to
#: ``os.environ``).  Keys are variable names; a ``str`` value overrides the
#: variable, ``None`` clears it.
CURRENT_OVERRIDES: ContextVar[dict[str, str | None] | None] = ContextVar(
    "talk_call_context", default=None
)


def current() -> dict[str, str | None] | None:
    """Return the override map for the current context, or ``None``."""
    return CURRENT_OVERRIDES.get()


@contextlib.contextmanager
def call_context(overrides: dict[str, str | None]) -> Iterator[None]:
    """Install per-context bridge variable overrides for this execution context.

    Overrides are visible only to the current context (request / thread),
    never to other concurrent requests, and the process environment is never
    touched.  Nested contexts compose by replacement, as usual for
    ``contextvars``.
    """
    token = CURRENT_OVERRIDES.set(dict(overrides))
    try:
        yield
    finally:
        CURRENT_OVERRIDES.reset(token)


def env(name: str, default: str | None = None) -> str | None:
    """Resolve a bridge variable: context override first, then ``os.environ``.

    A context override wins even when it clears the variable (``None``);
    variables absent from the override map inherit ``os.environ`` unchanged.
    Both here and on the plain ``os.environ`` fallback an explicit ``""`` is
    returned as-is — only a genuinely unset variable yields ``default``, so
    "unset" and "explicitly empty" stay distinguishable for callers.
    """
    overrides = CURRENT_OVERRIDES.get()
    if overrides is not None and name in overrides:
        value = overrides[name]
        return default if value is None else value
    return os.environ.get(name, default)
