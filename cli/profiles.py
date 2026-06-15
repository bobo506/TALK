"""Read agent identity-layer profiles from a project's ``.talk/agents/``.

Shared by the bridge (Phase 2 prompt injection) and the ``talk`` CLI. Pure
filesystem reads — no network, no heavy deps — so it is safe to import from the
bridge hot path.

Profile layout (PROJECT_INTEGRATION §5.3)::

    .talk/agents/<member_dir_name(member_id)>/
        IDENTITY.md   # 我是谁、Agent 类型、擅长领域
        SOUL.md       # 语气、决策风格、不可逾越的边界
        USER.md       # 这个项目里的搭档信息（可选）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, Path]


def member_dir_name(member_id: str) -> str:
    """Filesystem-safe directory name for a ``member_id``.

    member_ids contain ``:`` (e.g. ``agent:codex``) which Windows forbids in
    paths, so map ``:`` -> ``_``. The bridge and CLI MUST use this same mapping
    so a profile written by ``talk add-agent`` is found by the bridge.
    """
    return member_id.replace(":", "_")


@dataclass
class AgentProfile:
    """An agent's identity-layer profile loaded from disk."""

    member_id: str
    identity: Optional[str] = None
    soul: Optional[str] = None
    user: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not (self.identity or self.soul or self.user)


def _read_if_exists(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def agent_profile_dir(root: PathLike, member_id: str) -> Path:
    """Return the profile directory for ``member_id`` under ``root``."""
    return Path(root) / ".talk" / "agents" / member_dir_name(member_id)


def load_profile(root: PathLike, member_id: str) -> AgentProfile:
    """Load IDENTITY/SOUL/USER for ``member_id`` from ``<root>/.talk/agents/<dir>/``.

    A missing directory or missing files yield ``None`` fields (``is_empty`` is
    True), so callers can fall back to no injection rather than erroring.
    """
    agent_dir = agent_profile_dir(root, member_id)
    return AgentProfile(
        member_id=member_id,
        identity=_read_if_exists(agent_dir / "IDENTITY.md"),
        soul=_read_if_exists(agent_dir / "SOUL.md"),
        user=_read_if_exists(agent_dir / "USER.md"),
    )


def compose_identity_block(profile: AgentProfile) -> str:
    """Compose a compact system-layer block from a profile.

    Returns ``""`` when the profile is empty. Concatenates the curated
    IDENTITY / SOUL / USER markdown (in that order). These files are authored to
    be concise; the SOUL section itself carries the anti-"已经XX啦" / no-meta
    rules, so injecting it is the intended Phase 2 fix — distinct from the
    compact per-call identity line the bridge already emits.
    """
    if profile.is_empty:
        return ""
    parts = [text.strip() for text in (profile.identity, profile.soul, profile.user) if text]
    return "\n\n".join(parts)
