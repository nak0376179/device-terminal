from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key
from fastapi import APIRouter, Depends

from auth import jwt_bearer
from connection_manager import manager
from db import devices_table

router = APIRouter(prefix="/api", tags=["devices"])


@router.get("/devices")
def list_devices(group_id: str = Depends(jwt_bearer)) -> dict[str, Any]:
    resp = devices_table().query(
        KeyConditionExpression=Key("group_id").eq(group_id),
    )
    devices = []
    for item in resp.get("Items", []):
        devices.append({
            "thingName": item["thing_name"],
            "connected": manager.is_online(item["thing_name"]),
        })
    return {"devices": devices}
