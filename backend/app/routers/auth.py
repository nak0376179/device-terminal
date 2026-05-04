from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth import create_token, pwd_context
from db import groups_table

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    group_id: str
    group_pw: str


@router.post("/login")
def login(body: LoginRequest) -> dict[str, str]:
    item = groups_table().get_item(Key={"group_id": body.group_id}).get("Item")
    if not item or not pwd_context.verify(body.group_pw, item["group_pw_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": create_token(body.group_id)}
