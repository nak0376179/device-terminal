from __future__ import annotations

from fastapi import HTTPException

from db import devices_table


def make_device_pk(group_id: str, dev_id: str) -> str:
    return f"{group_id}#{dev_id}"


def assert_device_access(thing_name: str, group_id: str) -> str:
    """Verify device belongs to group. Returns device_pk (group_id#dev_id)."""
    parts = thing_name.split(":", 1)
    if len(parts) != 2 or parts[0] != group_id:
        raise HTTPException(status_code=403, detail="Device not in your group")
    dev_id = parts[1]
    if not devices_table().get_item(Key={"group_id": group_id, "dev_id": dev_id}).get("Item"):
        raise HTTPException(status_code=403, detail="Device not in your group")
    return make_device_pk(group_id, dev_id)
