from app.db import init_db, DB_PATH
from app.db import get_conn
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from typing import Any

TODAY_LIMIT = 5
REVIEW_TARGET = 2


app = FastAPI(title="EchoSlice API", version="0.0.1")

# Frontend dev server(CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://localhost:5173",
        "https://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def today_str_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def now_str_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def fetch_today_queue(conn: sqlite3.Connection, day: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT tq.position, tq.kind, c.id, c.video_id, c.start_sec, c.end_sec, c.title
        FROM today_queue tq
        JOIN clips c ON c.id = tq.clip_id
        WHERE tq.day = ?
        ORDER BY tq.position ASC
        """,
        (day,),
    ).fetchall()

def create_today_queue(conn: sqlite3.Connection, day: str, limit: int, review_target: int) -> list[sqlite3.Row]:
    now_s = now_str_utc()

    # 0) 오늘 완료된 clip 제외 (오늘 리뷰한 clip)
    done_ids = conn.execute(
        "SELECT DISTINCT clip_id FROM reviews WHERE reviewed_at LIKE ?",
        (f"{day}%",),
    ).fetchall()
    done_set = {r["clip_id"] for r in done_ids}

    # 1) 복습 후보: next_review_at <= now (가장 최근 next_review_at 기준)
    review_rows = conn.execute(
        """
        SELECT c.id, r_due.next_review_at
        FROM clips c
        JOIN (
          SELECT clip_id, MAX(next_review_at) AS next_review_at
          FROM reviews
          GROUP BY clip_id
        ) r_due ON r_due.clip_id = c.id
        WHERE r_due.next_review_at <= ?
        ORDER BY r_due.next_review_at ASC
        LIMIT ?
        """,
        (now_s, review_target),
    ).fetchall()
    review_ids = [r["id"] for r in review_rows if r["id"] not in done_set]

    # 2) 신규 후보: 아직 리뷰가 없는 clip
    slots_left = max(0, limit - len(review_ids))
    new_rows = conn.execute(
        """
        SELECT c.id
        FROM clips c
        LEFT JOIN reviews r ON r.clip_id = c.id
        WHERE r.clip_id IS NULL
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (slots_left,),
    ).fetchall()
    new_ids = [r["id"] for r in new_rows if r["id"] not in done_set and r["id"] not in set(review_ids)]

    # 3) 저장: 오늘 큐 전체를 새로 생성
    conn.execute("DELETE FROM today_queue WHERE day = ?", (day,))
    pos = 0
    for cid in review_ids:
        conn.execute(
            "INSERT INTO today_queue (day, position, clip_id, kind) VALUES (?, ?, ?, 'review')",
            (day, pos, cid),
        )
        pos += 1
    for cid in new_ids:
        conn.execute(
            "INSERT INTO today_queue (day, position, clip_id, kind) VALUES (?, ?, ?, 'new')",
            (day, pos, cid),
        )
        pos += 1
    conn.commit()

    return fetch_today_queue(conn, day)

def reroll_new_only(conn: sqlite3.Connection, day: str, limit: int) -> list[sqlite3.Row]:
    # 1) 현재 큐가 없으면 먼저 생성
    existing = fetch_today_queue(conn, day)
    if not existing:
        existing = create_today_queue(conn, day, limit, REVIEW_TARGET)

    # 2) 복습 clip은 고정 (review ids)
    review_ids = [r["id"] for r in existing if r["kind"] == "review"]

    # 3) 신규 슬롯 position 목록
    new_positions = [r["position"] for r in existing if r["kind"] == "new"]
    if not new_positions:
        return existing  # 신규 슬롯이 없으면 바꿀 것도 없음

    # 4) 오늘 완료된 clip 제외
    done_ids = conn.execute(
        "SELECT DISTINCT clip_id FROM reviews WHERE reviewed_at LIKE ?",
        (f"{day}%",),
    ).fetchall()
    done_set = {r["clip_id"] for r in done_ids}

    # 5) 신규 후보 풀에서 새로 뽑기
    needed = len(new_positions)
    new_rows = conn.execute(
        """
        SELECT c.id
        FROM clips c
        LEFT JOIN reviews r ON r.clip_id = c.id
        WHERE r.clip_id IS NULL
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (needed * 5,),  # 여유 있게 뽑고 중복/제외 필터
    ).fetchall()

    picked: list[int] = []
    blocked = set(review_ids) | done_set
    for row in new_rows:
        cid = row["id"]
        if cid in blocked or cid in picked:
            continue
        picked.append(cid)
        if len(picked) == needed:
            break

    # 후보 부족하면 가능한 만큼만 교체
    # 기존 new 행 삭제
    conn.execute("DELETE FROM today_queue WHERE day = ? AND kind = 'new'", (day,))

    # 같은 position에 다시 채우기
    for pos, cid in zip(sorted(new_positions), picked):
        conn.execute(
            "INSERT INTO today_queue (day, position, clip_id, kind) VALUES (?, ?, ?, 'new')",
            (day, pos, cid),
        )
    conn.commit()

    return fetch_today_queue(conn, day)

class ReviewCreate(BaseModel):
    clipId: int
    score: int # 1 - 5
def calc_next_review_at(score: int) -> datetime:
    if score <= 2:
        days = 1
    elif score == 3:
        days = 3
    elif score == 4:
        days = 7
    else:
        days = 14
    return datetime.now(timezone.utc) + timedelta(days=days)


@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok", "service": "echoslice-backend"}

@app.get("/db/health")
def db_health():
    return {"db": "ok", "path": str(DB_PATH)}


@app.get("/clips/today")
def get_today_clips() -> list[dict[str, Any]]:
    day = today_str_utc()
    with get_conn() as conn:
        rows = fetch_today_queue(conn, day)
        if not rows:
            rows = create_today_queue(conn, day, TODAY_LIMIT, REVIEW_TARGET)

    return [
        {
            "id": row["id"],
            "videoId": row["video_id"],
            "startSec": row["start_sec"],
            "endSec": row["end_sec"],
            "title": row["title"],
            "kind": row["kind"],  # 'review' | 'new'
        }
        for row in rows
    ]

@app.post("/clips/today/reroll")
def reroll_today_new() -> list[dict[str, Any]]:
    day = today_str_utc()
    with get_conn() as conn:
        rows = reroll_new_only(conn, day, TODAY_LIMIT)

    return [
        {
            "id": row["id"],
            "videoId": row["video_id"],
            "startSec": row["start_sec"],
            "endSec": row["end_sec"],
            "title": row["title"],
            "kind": row["kind"],
        }
        for row in rows
    ]


@app.post("/reviews")
def create_review(payload: ReviewCreate):
    if payload.score < 1 or payload.score > 5:
        raise HTTPException(status_code=400, detail="score must be between 1 and 5")

    now = datetime.now(timezone.utc)
    next_dt = calc_next_review_at(payload.score)

    reviewed_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    next_review_at = next_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    with get_conn() as conn:
        clip = conn.execute(
            "SELECT id FROM clips WHERE id = ?",
            (payload.clipId,),
        ).fetchone()

        if not clip:
            raise HTTPException(status_code=404, detail="clip not found")
        
        cur = conn.execute(
            """
            INSERT INTO reviews (clip_id, score, reviewed_at, next_review_at)
            VALUES (?, ?, ?, ?)
            """,
            (payload.clipId, payload.score, reviewed_at, next_review_at),
        )
        conn.commit()

        review_id = cur.lastrowid
    
    return {
        "id": review_id,
        "clipId": payload.clipId,
        "score": payload.score,
        "reviewedAt": reviewed_at,
        "nextReviewAt": next_review_at,
    }

@app.get("/reviews/today")
def get_today_reviews():
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                r.id,
                r.clip_id,
                r.score,
                r.reviewed_at,
                r.next_review_at
            FROM reviews r
            WHERE r.reviewed_at LIKE ?
            ORDER BY r.reviewed_at DESC
            """,
            (f"{today_utc}%",),
        ).fetchall()
    
    return [
        {
            "id": row["id"],
            "clipId": row["clip_id"],
            "score": row["score"],
            "reviewedAt": row["reviewed_at"],
            "nextReviewAt": row["next_review_at"],
        }
        for row in rows
    ]