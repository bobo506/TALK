"""Human-only, same-machine runtime log read endpoints (contract 273).

Both endpoints are GET-only, authenticate before touching a source, verify the
project/role pair from ``ProjectRole`` or ``ProjectAgent`` history, and then
delegate to the replaceable ``RuntimeDiagnosticsProvider``.  No existing
project/service/task endpoint changes behavior or permission.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlmodel import Session

from bridges.runtime_diagnostics import LOG_ID_RE
from server.auth import get_current_member
from server.db import get_session
from server.models import Member, Project, ProjectAgent, ProjectRole
from server.runtime_diagnostics_export import (
    build_export,
    export_filename,
    parse_export_time,
    validate_export_window,
)
from server.runtime_diagnostics_models import RuntimeLogDetail, RuntimeLogPage
from server.runtime_diagnostics_query import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    MAX_RANGE,
    MAX_TASK_ID,
    QuerySpec,
    RuntimeDiagnosticsError,
    ScanLimits,
)
from server.runtime_diagnostics_sources import (
    RuntimeDiagnosticsProvider,
    get_default_provider,
)

router = APIRouter(prefix="/api/projects", tags=["runtime-diagnostics"])

_SAFE_FILTER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DIGITS_RE = re.compile(r"^[0-9]+$")
_SEVERITIES = frozenset({"error", "warning", "info"})
_LIST_PARAMS = frozenset(
    {
        "ref",
        "since",
        "until",
        "instance_id",
        "launch_id",
        "task_id",
        "event",
        "stage",
        "severity",
        "limit",
        "cursor",
    }
)
_REF_CONFLICT_PARAMS = frozenset(
    {
        "cursor",
        "since",
        "until",
        "instance_id",
        "launch_id",
        "task_id",
        "event",
        "stage",
        "severity",
    }
)
_EXPORT_PARAMS = frozenset({"since", "until"})


def require_log_reader(
    request: Request,
    x_api_key: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> Member:
    """Authenticate with the existing auth helper, but turn a missing key into 401.

    ``get_current_member`` uses ``Header(...)``, which FastAPI would otherwise
    report as a generic 422.  The log contract requires 401 for no key, so this
    thin wrapper only supplies the missing-key mapping and then delegates to
    the existing authentication/disabled-account checks.
    """
    if x_api_key is None or not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return get_current_member(
        request=request, x_api_key=x_api_key, session=session
    )


def get_runtime_diagnostics_provider() -> RuntimeDiagnosticsProvider:
    """Replaceable FastAPI dependency; production uses one process-lifetime provider."""
    return get_default_provider()


def _invalid_filter() -> HTTPException:
    return HTTPException(status_code=422, detail="invalid_filter")


def _invalid_ref() -> HTTPException:
    return HTTPException(status_code=422, detail="invalid_log_ref")


def _invalid_cursor() -> HTTPException:
    return HTTPException(status_code=422, detail="invalid_cursor")


def _conflicting_filters() -> HTTPException:
    return HTTPException(status_code=422, detail="conflicting_filters")


def _require_human(current: Member) -> None:
    if current.kind != "human":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="log_read_forbidden",
        )


def _require_target(project_id: str, member_id: str, session: Session) -> None:
    if session.get(Project, project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project_not_found",
        )
    role_exists = session.get(ProjectRole, (project_id, member_id)) is not None
    roster_exists = session.get(ProjectAgent, (project_id, member_id)) is not None
    if not role_exists and not roster_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="role_not_found",
        )


def _single_pairs(request: Request, allowed: frozenset[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in request.query_params.multi_items():
        if key not in allowed:
            raise _invalid_filter()
        if key in result:
            raise _invalid_filter()
        result[key] = value
    return result


def _reject_any_query(request: Request) -> None:
    if request.query_params:
        raise _invalid_filter()


def _parse_time(value: str) -> datetime:
    if not value or len(value) > 128:
        raise _invalid_filter()
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise _invalid_filter()
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise _invalid_filter()


def _parse_limit(value: str | None) -> int:
    if value is None:
        return DEFAULT_PAGE_LIMIT
    if len(value) > 32 or not _DIGITS_RE.fullmatch(value):
        raise _invalid_filter()
    number = int(value)
    if number < 1 or number > MAX_PAGE_LIMIT:
        raise _invalid_filter()
    return number


def _parse_task_id(value: str) -> int:
    if len(value) > 32 or not _DIGITS_RE.fullmatch(value):
        raise _invalid_filter()
    number = int(value)
    if number < 1 or number > MAX_TASK_ID:
        raise _invalid_filter()
    return number


def _parse_optional_filter(
    pairs: dict[str, str],
    key: str,
    *,
    pattern: re.Pattern[str],
) -> str | None:
    if key not in pairs:
        return None
    value = pairs[key]
    if not value or not pattern.fullmatch(value):
        raise _invalid_filter()
    return value


def _parse_severity(value: str | None) -> list[str]:
    if value is None:
        return ["error", "warning"]
    if not value:
        raise _invalid_filter()
    pieces = [piece.strip() for piece in value.split(",")]
    if not pieces or any(not piece for piece in pieces):
        raise _invalid_filter()
    if any(piece not in _SEVERITIES for piece in pieces):
        raise _invalid_filter()
    return sorted(set(pieces))


def _parse_ref(value: str) -> str:
    if not value or not LOG_ID_RE.fullmatch(value):
        raise _invalid_ref()
    return value


def _parse_list_query(request: Request, provider: RuntimeDiagnosticsProvider) -> QuerySpec:
    pairs = _single_pairs(request, _LIST_PARAMS)
    provided = frozenset(pairs)
    raw_ref = pairs.get("ref")
    if raw_ref is not None and any(key in pairs for key in _REF_CONFLICT_PARAMS):
        raise _conflicting_filters()
    if raw_ref is not None:
        return QuerySpec(
            ref=_parse_ref(raw_ref),
            since=None,
            until=None,
            instance_id=None,
            launch_id=None,
            task_id=None,
            event=None,
            stage=None,
            severity=None,
            limit=_parse_limit(pairs.get("limit")),
            cursor=None,
            provided=provided,
        )

    cursor = pairs.get("cursor")
    if cursor is not None:
        if not cursor:
            raise _invalid_cursor()
        # A cursor must replay the first response's absolute window and severity,
        # not silently regenerate either one.
        if not {"since", "until", "severity"}.issubset(pairs):
            raise _invalid_cursor()

    now = provider.now()
    if "since" in pairs:
        since = _parse_time(pairs["since"])
    else:
        since = now - timedelta(hours=24)
    if "until" in pairs:
        until = _parse_time(pairs["until"])
    else:
        until = now
    if since >= until or until - since > MAX_RANGE:
        raise _invalid_filter()
    severity = _parse_severity(pairs.get("severity"))
    return QuerySpec(
        ref=None,
        since=since,
        until=until,
        instance_id=_parse_optional_filter(
            pairs, "instance_id", pattern=_SAFE_IDENTIFIER_RE
        ),
        launch_id=_parse_optional_filter(
            pairs, "launch_id", pattern=_SAFE_IDENTIFIER_RE
        ),
        task_id=_parse_task_id(pairs["task_id"]) if "task_id" in pairs else None,
        event=_parse_optional_filter(pairs, "event", pattern=_SAFE_FILTER_RE),
        stage=_parse_optional_filter(pairs, "stage", pattern=_SAFE_FILTER_RE),
        severity=tuple(severity),
        limit=_parse_limit(pairs.get("limit")),
        cursor=cursor,
        provided=provided,
    )


def _parse_export_window(request: Request) -> tuple[datetime, datetime]:
    pairs = _single_pairs(request, _EXPORT_PARAMS)
    if set(pairs) != {"since", "until"}:
        raise _invalid_filter()
    try:
        since = parse_export_time(pairs["since"])
        until = parse_export_time(pairs["until"])
        validate_export_window(since, until)
    except (TypeError, ValueError, OverflowError):
        raise _invalid_filter()
    return since, until


def _map_error(exc: RuntimeDiagnosticsError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc


@router.get(
    "/{project_id}/roles/{member_id}/runtime-logs",
    response_model=RuntimeLogPage,
)
def list_runtime_logs(
    project_id: str,
    member_id: str,
    request: Request,
    current: Member = Depends(require_log_reader),
    session: Session = Depends(get_session),
    provider: RuntimeDiagnosticsProvider = Depends(get_runtime_diagnostics_provider),
):
    _require_human(current)
    _require_target(project_id, member_id, session)
    query = _parse_list_query(request, provider)
    try:
        return provider.list_logs(project_id, member_id, query)
    except RuntimeDiagnosticsError as exc:
        _map_error(exc)
    except HTTPException:
        raise
    except Exception:
        # Never let a raw path, parser message or record body escape in a 500.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="diagnostics_projection_failed",
        )


@router.get(
    "/{project_id}/roles/{member_id}/runtime-logs/export",
    responses={
        200: {"content": {"application/x-ndjson": {"schema": {"type": "string"}}}},
    },
)
def export_runtime_logs(
    project_id: str,
    member_id: str,
    request: Request,
    current: Member = Depends(require_log_reader),
    session: Session = Depends(get_session),
    provider: RuntimeDiagnosticsProvider = Depends(get_runtime_diagnostics_provider),
):
    _require_human(current)
    _require_target(project_id, member_id, session)
    since, until = _parse_export_window(request)
    try:
        source = provider.require_source(project_id, member_id)
        limits = getattr(provider, "_scan_limits", None)
        if not isinstance(limits, ScanLimits):
            limits = ScanLimits()
        body = build_export(
            source,
            project_id=project_id,
            member_id=member_id,
            since=since,
            until=until,
            generated_at=provider.now(),
            limits=limits,
        )
        filename = export_filename(since, until)
        return Response(
            content=body,
            media_type="application/x-ndjson",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )
    except RuntimeDiagnosticsError as exc:
        _map_error(exc)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="diagnostics_projection_failed",
        )


@router.get(
    "/{project_id}/roles/{member_id}/runtime-logs/{log_ref:path}/detail",
    response_model=RuntimeLogDetail,
)
def get_runtime_log_detail(
    project_id: str,
    member_id: str,
    log_ref: str,
    request: Request,
    current: Member = Depends(require_log_reader),
    session: Session = Depends(get_session),
    provider: RuntimeDiagnosticsProvider = Depends(get_runtime_diagnostics_provider),
):
    _require_human(current)
    _require_target(project_id, member_id, session)
    _reject_any_query(request)
    if not log_ref or not LOG_ID_RE.fullmatch(log_ref):
        raise _invalid_ref()
    try:
        return provider.get_detail(project_id, member_id, log_ref)
    except RuntimeDiagnosticsError as exc:
        _map_error(exc)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="diagnostics_projection_failed",
        )
