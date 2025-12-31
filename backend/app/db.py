import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent  # backend/app
DB_PATH = BASE_DIR.parent / "echoslice.db"  # backend/echoslice.db
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

def init_db() -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.executescript(schema_sql)
        conn.commit()
        migrate_db(conn)
