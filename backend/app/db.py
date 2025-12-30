import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent  # backend/app
DB_PATH = BASE_DIR.parent / "echoslice.db"  # backend/echoslice.db
SCHEMA_PATH = BASE_DIR / "schema.sql"       # backend/app/schema.sql


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.executescript(schema_sql)
        conn.commit()
