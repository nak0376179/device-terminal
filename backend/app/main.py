"""Device Terminal API.

Local dev:  uvicorn --app-dir app main:app --reload --port 9001

Routes:
  /healthz                         — health check (no auth)
  /api/auth/*                      — login
  /api/admin/*                     — group/device provisioning
  /api/devices                     — tenant-scoped device list (JWT required)
  /ws/device                       — device WebSocket (API key)
  /ws/terminal/{thing_name}        — browser terminal WebSocket (JWT)
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import admin, auth, devices, ws_device, ws_terminal

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Device Terminal API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(devices.router)
app.include_router(ws_device.router)
app.include_router(ws_terminal.router)
