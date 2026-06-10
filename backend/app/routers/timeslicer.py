from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import os
from datetime import datetime
import json
import logging

from app.db import get_conn

router = APIRouter(prefix="/timeslicer", tags=["timeslicer"])

TOKEN = os.getenv("TIMESLICER_TOKEN", "")


def require_token(req: Request):
    if not TOKEN:
        return
    auth = req.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    if auth.removeprefix("Bearer ").strip() != TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")


def ensure_table():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS timeslicer_state (
              key TEXT PRIMARY KEY,
              state_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


class StatePayload(BaseModel):
    state: dict


@router.get("/state")
def get_state(req: Request):
    logger = logging.getLogger("timeslicer")
    client_id = req.headers.get("x-timeslicer-client", "unknown")
    logger.info(f"[timeslicer] client={client_id} {req.method} {req.url.path}")

    require_token(req)
    ensure_table()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT state_json, updated_at FROM timeslicer_state WHERE key = %s",
            ("default",),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No state saved yet")

    return {
        "key": "default",
        "state": json.loads(row["state_json"]),
        "updatedAt": row["updated_at"],
    }


@router.put("/state")
def put_state(payload: StatePayload, req: Request):
    logger = logging.getLogger("timeslicer")
    client_id = req.headers.get("x-timeslicer-client", "unknown")
    logger.info(f"[timeslicer] client={client_id} {req.method} {req.url.path}")

    require_token(req)
    ensure_table()

    now = datetime.utcnow().isoformat() + "Z"
    state_str = json.dumps(payload.state, separators=(",", ":"))

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO timeslicer_state(key, state_json, updated_at)
            VALUES(%s, %s, %s)
            ON CONFLICT(key) DO UPDATE SET
              state_json=EXCLUDED.state_json,
              updated_at=EXCLUDED.updated_at
            """,
            ("default", state_str, now),
        )
        conn.commit()

    return {"ok": True, "updatedAt": now}
