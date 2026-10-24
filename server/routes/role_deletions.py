"""Human deletion intent and operator-authenticated local cleanup receipts."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session
from server.auth import get_current_member
from server.db import get_session
from server.models import Member
from server import role_deletions as d

router = APIRouter(prefix="/api/projects", tags=["role-deletions"])


class DeleteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_member_id: str


class ClaimBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int


class ReportBody(ClaimBody):
    lease_token: str
    outcome: str
    steps: dict[str, str]
    error_code: str | None = None


@router.post("/{project_id}/roles/{member_id}/delete")
def delete_role(project_id: str, member_id: str, body: DeleteBody,
                current: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    return d.request_delete(project_id, member_id, body.confirm_member_id, current, session)


@router.get("/{project_id}/roles/{member_id}/deletion")
def deletion_status(project_id: str, member_id: str,
                    current: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    return d.public(d._row(session, project_id, member_id))


@router.post("/{project_id}/roles/{member_id}/deletion/claim")
def claim_cleanup(project_id: str, member_id: str, body: ClaimBody,
                  current: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    return d.claim(project_id, member_id, body.revision, current, session)


@router.post("/{project_id}/roles/{member_id}/deletion/report")
def report_cleanup(project_id: str, member_id: str, body: ReportBody,
                   current: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    return d.report(project_id, member_id, body.lease_token, body.revision, body.outcome,
                    body.steps, body.error_code, current, session)
