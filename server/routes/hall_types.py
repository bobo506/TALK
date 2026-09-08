"""Hall 类型模板只读 API（D1）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from server.auth import get_current_member
from server.hall_types import HALL_TYPE_TEMPLATES
from server.models import Member

router = APIRouter(prefix="/api/hall-types", tags=["hall-types"])


@router.get("")
def list_hall_types(current: Member = Depends(get_current_member)):
    """列出内置 Hall 类型模板（已认证成员可读）。"""
    return [
        {
            "type": hall_type,
            "label": template["label"],
            "protocol_guidance": template["protocol_guidance"],
            "roles": template["roles"],
        }
        for hall_type, template in HALL_TYPE_TEMPLATES.items()
    ]
