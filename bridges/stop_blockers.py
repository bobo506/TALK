"""Finite, public references for a refused busy-role stop; never carries text."""
BUSY_STOP_CODE = "role_service_busy"
STOP_BLOCKER_LIMIT = 20
MAX_PUBLIC_INTEGER = 2**53 - 1


def safe_stop_blockers(value):
    if not isinstance(value, dict) or value.get("code") != BUSY_STOP_CODE:
        return None
    raw = value.get("task_ids")
    if not isinstance(raw, list):
        return None
    ids = []
    for item in raw:
        if type(item) is int and 0 < item <= MAX_PUBLIC_INTEGER and item not in ids:
            ids.append(item)
            if len(ids) == STOP_BLOCKER_LIMIT:
                break
    count = value.get("task_count")
    if type(count) is not int or not len(ids) <= count <= MAX_PUBLIC_INTEGER:
        count = len(ids)
    busy = value.get("instance_busy") is True
    if not ids and not count and not busy:
        return None
    return {"code": BUSY_STOP_CODE, "task_ids": ids, "task_count": count, "instance_busy": busy}
