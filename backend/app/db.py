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


def is_slug_blocked(conn: sqlite3.Connection, slug: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM bad_slugs WHERE slug = ? LIMIT 1;",
        (slug,),
    ).fetchone()
    return row is not None

def block_slug(conn: sqlite3.Connection, slug: str, reason: str) -> None:
    conn.execute(
        """
        INSERT INTO bad_slugs (slug, reason)
        VALUES (?, ?)
        ON CONFLICT(slug) DO UPDATE SET
          reason = excluded.reason,
          created_at = datetime('now');
        """,
        (slug, reason),
    )
    conn.commit()

def migrate_db(conn: sqlite3.Connection) -> None:
    # Add kind column to today_queue if missing (backward compatibility)
    cols = conn.execute("PRAGMA table_info(today_queue);").fetchall()
    col_names = {c["name"] for c in cols}
    if "kind" not in col_names:
        conn.execute("ALTER TABLE today_queue ADD COLUMN kind TEXT NOT NULL DEFAULT 'new';")
        # Set existing data to 'new' as default (safe fallback)
        conn.execute("UPDATE today_queue SET kind = 'new' WHERE kind IS NULL OR kind = '';")
        conn.commit()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bad_slugs (
          slug TEXT PRIMARY KEY,
          reason TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bad_slugs_created_at ON bad_slugs(created_at);"
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
    """Count of Gemini API calls made today (local time)."""
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


def reset_db() -> dict:
    """
    Completely reset the database. Deletes all data from all tables and recreates the schema.
    Returns: Dictionary with deleted record counts
    """
    conn = get_conn()
    
    # Count records in each table before deletion
    counts = {}
    tables = ['reviews', 'today_queue', 'clips', 'gemini_calls', 'bad_slugs']
    for table in tables:
        row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
        counts[table] = row['cnt'] if row else 0
    
    # Temporarily disable foreign key constraints
    conn.execute("PRAGMA foreign_keys = OFF")
    
    # Delete all data from tables (order matters: reverse of foreign key references)
    conn.execute("DELETE FROM reviews")
    conn.execute("DELETE FROM today_queue")
    conn.execute("DELETE FROM clips")
    conn.execute("DELETE FROM gemini_calls")
    conn.execute("DELETE FROM bad_slugs")
    
    # Reset AUTOINCREMENT sequences
    conn.execute("DELETE FROM sqlite_sequence")
    
    # Re-enable foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON")
    
    conn.commit()
    conn.close()
    
    # Recreate schema (including indexes)
    init_db()
    
    return {
        "deleted": counts,
        "status": "reset_complete"
    }
