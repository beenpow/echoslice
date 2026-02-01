from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
import os
import sqlite3
from datetime import datetime
import json

router = APIRouter(prefix="/timeslicer", tags=["timeslicer"])

# ===== Config =====
DB_PATH = os.getenv("ECHOSLICE_DB_PATH", "echoslice.db")
TOKEN = os.getenv("TIMESLICER_TOKEN", "")

def require_token(req: Request):
    if not TOKEN:
        # 토큰을 안 걸고 개발하고 싶으면 로컬에서는 env 없이도 통과
        return
    auth = req.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    if auth.removeprefix("Bearer ").strip() != TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
    client_id = request.headers.get("x-timeslicer-client", "unknown")
    logger.info(f"[timeslicer] client={client_id} {request.method} {request.url.path}")

    require_token(req)
    ensure_table()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT state_json, updated_at FROM timeslicer_state WHERE key = ?",
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
    client_id = request.headers.get("x-timeslicer-client", "unknown")
    logger.info(f"[timeslicer] client={client_id} {request.method} {request.url.path}")
    
    require_token(req)
    ensure_table()

    now = datetime.utcnow().isoformat() + "Z"
    state_json = payload.model_dump_json(include={"state"})  # {"state": {...}} JSON

    # 저장은 state만 저장하고 싶으니까 껍데기 제거
    # payload.state를 JSON 문자열로 저장
    import json
    state_str = json.dumps(payload.state, separators=(",", ":"))

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO timeslicer_state(key, state_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              state_json=excluded.state_json,
              updated_at=excluded.updated_at
            """,
            ("default", state_str, now),
        )
        conn.commit()

    return {"ok": True, "updatedAt": now}
