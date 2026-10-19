"""Network DTOs for the human-only runtime log view (contract 273).

These models are deliberately independent from ``talk-runtime-diagnostics-1``:
the persisted records are never serialized directly.  Every object forbids
unknown fields and contains only the fields listed in the frozen API contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RuntimeLogScope(_ContractModel):
    project_id: str
    member_id: str


class RuntimeLogQuery(_ContractModel):
    since: str | None = None
    until: str | None = None
    instance_id: str | None = None
    launch_id: str | None = None
    task_id: int | None = None
    event: str | None = None
    stage: str | None = None
    severity: list[str] | None = None
    ref: str | None = None


class RuntimeLogBudgets(_ContractModel):
    cli_timeout_seconds: int | float | None = None
    http_timeout_seconds: int | float | None = None
    task_lease_seconds: int | float | None = None
    task_heartbeat_interval_seconds: int | float | None = None
    managed_heartbeat_interval_seconds: int | float | None = None
    task_poll_interval_seconds: int | float | None = None
    mcp_wait_seconds: int | float | None = None


class RuntimeLogIntegritySummary(_ContractModel):
    redacted: bool | None = None
    truncated: bool | None = None
    write_complete: bool | None = None


class RuntimeLogExceptionSummary(_ContractModel):
    type: str | None = None
    message_preview: str = ""
    frames_total: int | None = None
    cause_depth: int | None = None


class RuntimeLogRecordSummary(_ContractModel):
    log_id: str
    recorded_at: str
    event: str
    severity: str
    stage: str | None = None
    project_id: str
    member_id: str
    instance_id: str | None = None
    launch_id: str | None = None
    task_id: int | None = None
    related_log_id: str | None = None
    exception: RuntimeLogExceptionSummary | None = None
    returncode: int | None = None
    timeout: bool | None = None
    cancel_category: str | None = None
    budgets: RuntimeLogBudgets
    integrity: RuntimeLogIntegritySummary


class RuntimeLogPageInfo(_ContractModel):
    limit: int = Field(ge=1, le=50)
    sort: Literal["recorded_at DESC, log_id DESC"] = "recorded_at DESC, log_id DESC"
    snapshot_until: str | None = None
    has_more: bool
    next_cursor: str | None = None


class RuntimeLogScan(_ContractModel):
    complete: bool
    truncated: bool
    scanned_files: int = Field(ge=0)
    scanned_bytes: int = Field(ge=0)
    malformed_lines: int = Field(ge=0)
    unavailable_sources: int = Field(ge=0)


class RuntimeLogPage(_ContractModel):
    schema_name: Literal["talk-runtime-log-page-1"] = Field(
        default="talk-runtime-log-page-1", alias="schema"
    )
    scope: RuntimeLogScope
    query: RuntimeLogQuery
    records: list[RuntimeLogRecordSummary]
    page: RuntimeLogPageInfo
    scan: RuntimeLogScan
    warnings: list[str]


class RuntimeLogFrame(_ContractModel):
    file_name: str
    line: int | None = None
    function: str | None = None


class RuntimeLogCause(_ContractModel):
    relation: str | None = None
    type: str | None = None
    message: str = ""
    frames_total: int | None = None
    frames_omitted: int | None = None
    frames: list[RuntimeLogFrame]


class RuntimeLogExceptionDetail(_ContractModel):
    type: str | None = None
    message: str = ""
    str_empty: bool | None = None
    message_error: bool | None = None
    frames_total: int | None = None
    frames_omitted: int | None = None
    frames: list[RuntimeLogFrame]
    cause_chain: list[RuntimeLogCause]
    chain_depth: int | None = None
    chain_truncated: bool | None = None
    chain_cycle: bool | None = None
    has_explicit_cause: bool | None = None
    context_present: bool | None = None
    context_suppressed: bool | None = None


class RuntimeLogIntegrityDetail(_ContractModel):
    redacted: bool | None = None
    redaction_kinds: list[str]
    truncated: bool | None = None
    truncated_fields: list[str]
    write_complete: bool | None = None
    capacity_soft_exceeded: bool | None = None
    event_size_soft_exceeded: bool | None = None


class RuntimeLogRecordDetail(_ContractModel):
    log_id: str
    recorded_at: str
    event: str
    severity: str
    stage: str | None = None
    project_id: str
    member_id: str
    instance_id: str | None = None
    launch_id: str | None = None
    task_id: int | None = None
    related_log_id: str | None = None
    exception: RuntimeLogExceptionDetail | None = None
    returncode: int | None = None
    timeout: bool | None = None
    cancel_category: str | None = None
    budgets: RuntimeLogBudgets
    integrity: RuntimeLogIntegrityDetail


class RuntimeLogDetail(_ContractModel):
    schema_name: Literal["talk-runtime-log-detail-1"] = Field(
        default="talk-runtime-log-detail-1", alias="schema"
    )
    scope: RuntimeLogScope
    record: RuntimeLogRecordDetail
    scan: RuntimeLogScan
