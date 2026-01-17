import sqlite3
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent  # backend/app
#DB_PATH = BASE_DIR.parent / "echoslice.db"  # backend/echoslice.db
DB_PATH = Path(
    os.getenv("ECHOSLICE_DB_PATH", BASE_DIR.parent / "echoslice.db")
)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
SCHEMA_PATH = BASE_DIR / "schema.sql"       # backend/app/schema.sql

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_db(conn: sqlite3.Connection) -> None:
    # today_queue에 kind 컬럼이 없으면 추가 (기존 DB 호환)
    cols = conn.execute("PRAGMA table_info(today_queue);").fetchall()
    col_names = {c["name"] for c in cols}
    if "kind" not in col_names:
        conn.execute("ALTER TABLE today_queue ADD COLUMN kind TEXT NOT NULL DEFAULT 'new';")
        # 기존 데이터는 의미를 알 수 없으니 안전하게 new로 둠
        conn.execute("UPDATE today_queue SET kind = 'new' WHERE kind IS NULL OR kind = '';")
        conn.commit()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gemini_calls (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          reason TEXT
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_gemini_calls_created_at ON gemini_calls(created_at);"
    )
    conn.commit()


def init_db() -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.executescript(schema_sql)
        conn.commit()
        migrate_db(conn)

def count_unreviewed_clips(conn) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM clips c
        LEFT JOIN reviews r ON r.clip_id = c.id
        WHERE r.id IS NULL
        """
    ).fetchone()
    return int(row[0]) if row else 0


def fetch_unreviewed_clip_ids(conn, limit: int) -> list[int]:
    rows = conn.execute(
        """
        SELECT c.id
        FROM clips c
        LEFT JOIN reviews r ON r.clip_id = c.id
        WHERE r.id IS NULL
        ORDER BY c.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [int(r[0]) for r in rows]

# -----------------------------
# Gemini API usage guard helpers
# -----------------------------

def gemini_calls_today(conn: sqlite3.Connection) -> int:
    """Local-time 기준 오늘 gemini 호출 횟수."""
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM gemini_calls
        WHERE DATE(created_at, 'localtime') = DATE('now', 'localtime')
        """
    ).fetchone()
    return int(row[0]) if row else 0


def log_gemini_call(conn: sqlite3.Connection, reason: str) -> None:
    conn.execute(
        "INSERT INTO gemini_calls (reason) VALUES (?);",
        (reason,),
    )
    conn.commit()
