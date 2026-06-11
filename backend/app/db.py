import os
import psycopg2
import psycopg2.extras
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

_raw_url = os.getenv("DATABASE_URL", "")
# Hide credentials from /db/health display
DB_PATH = _raw_url.split("@")[-1] if "@" in _raw_url else (_raw_url or "not configured")


class _Conn:
    """Makes psycopg2 connection behave like sqlite3 for minimal code changes."""

    def __init__(self, raw: "psycopg2.extensions.connection") -> None:
        self._raw = raw
        self._cur = raw.cursor()

    def execute(self, sql: str, params=None):
        self._cur.execute(sql, params)
        return self._cur

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._cur.close()
        self._raw.close()

    def __enter__(self) -> "_Conn":
        return self

    def __exit__(self, exc_type, *_) -> None:
        if exc_type is None:
            self._raw.commit()
        else:
            self._raw.rollback()
        self._cur.close()
        self._raw.close()


def get_conn() -> _Conn:
    raw = psycopg2.connect(_raw_url, cursor_factory=psycopg2.extras.DictCursor)
    return _Conn(raw)


def is_slug_blocked(conn: _Conn, slug: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM bad_slugs WHERE slug = %s LIMIT 1",
        (slug,),
    ).fetchone()
    return row is not None


def block_slug(conn: _Conn, slug: str, reason: str) -> None:
    conn.execute(
        """
        INSERT INTO bad_slugs (slug, reason)
        VALUES (%s, %s)
        ON CONFLICT (slug) DO UPDATE SET
          reason = EXCLUDED.reason,
          created_at = NOW()
        """,
        (slug, reason),
    )
    conn.commit()


def migrate_db(conn: _Conn) -> None:
    # Add kind column to today_queue if missing (backward compatibility)
    cols = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'today_queue'"
    ).fetchall()
    col_names = {c["column_name"] for c in cols}
    if "kind" not in col_names:
        conn.execute(
            "ALTER TABLE today_queue ADD COLUMN kind TEXT NOT NULL DEFAULT 'new'"
        )
        conn.execute(
            "UPDATE today_queue SET kind = 'new' WHERE kind IS NULL OR kind = ''"
        )
        conn.commit()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bad_slugs (
          slug TEXT PRIMARY KEY,
          reason TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bad_slugs_created_at ON bad_slugs(created_at)"
    )
    conn.commit()

    # Add transcript_json column to clips if missing (backward compatibility)
    cols = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'clips'"
    ).fetchall()
    col_names = {c["column_name"] for c in cols}
    if "transcript_json" not in col_names:
        conn.execute("ALTER TABLE clips ADD COLUMN transcript_json TEXT")
        conn.commit()


def init_db() -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_conn() as conn:
        for stmt in schema_sql.split(";"):
            lines = [
                line for line in stmt.splitlines()
                if not line.strip().startswith("--")
            ]
            stmt = "\n".join(lines).strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
        migrate_db(conn)


def count_unreviewed_clips(conn: _Conn) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM clips c
        LEFT JOIN reviews r ON r.clip_id = c.id
        WHERE r.id IS NULL
        """
    ).fetchone()
    return int(row[0]) if row else 0


def fetch_unreviewed_clip_ids(conn: _Conn, limit: int) -> list[int]:
    rows = conn.execute(
        """
        SELECT c.id
        FROM clips c
        LEFT JOIN reviews r ON r.clip_id = c.id
        WHERE r.id IS NULL
        ORDER BY c.id DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [int(r[0]) for r in rows]


def gemini_calls_today(conn: _Conn) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM gemini_calls
        WHERE (created_at AT TIME ZONE 'America/Los_Angeles')::date
              = (NOW() AT TIME ZONE 'America/Los_Angeles')::date
        """
    ).fetchone()
    return int(row[0]) if row else 0


def log_gemini_call(conn: _Conn, reason: str) -> None:
    conn.execute(
        "INSERT INTO gemini_calls (reason) VALUES (%s)",
        (reason,),
    )
    conn.commit()


def reset_db() -> dict:
    """
    Completely reset the database. Deletes all data from all tables and recreates the schema.
    Returns: Dictionary with deleted record counts
    """
    conn = get_conn()

    counts = {}
    tables = ['reviews', 'today_queue', 'clips', 'gemini_calls', 'bad_slugs']
    for table in tables:
        row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()
        counts[table] = row['cnt'] if row else 0

    conn.execute(
        "TRUNCATE TABLE reviews, today_queue, clips, gemini_calls, bad_slugs RESTART IDENTITY"
    )
    conn.commit()
    conn.close()

    init_db()

    return {
        "deleted": counts,
        "status": "reset_complete"
    }
