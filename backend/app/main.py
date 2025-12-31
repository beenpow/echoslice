from app.db import init_db, DB_PATH
from app.db import get_conn
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any

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
def get_today_clips():
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    today_str = now_utc.strftime("%Y-%m-%d")

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              c.id,
              c.video_id,
              c.start_sec,
              c.end_sec,
              c.title,
              COALESCE(r_due.next_review_at, '1970-01-01T00:00:00Z') AS next_review_at
            FROM clips c
            -- 각 clip에 대해 "가장 최근 review의 next_review_at"을 구한다
            LEFT JOIN (
              SELECT
                clip_id,
                MAX(next_review_at) AS next_review_at
              FROM reviews
              GROUP BY clip_id
            ) r_due
            ON r_due.clip_id = c.id
            WHERE
              -- 1) due 조건: 리뷰가 한 번도 없으면(신규) due로 취급해서 포함
              (
                r_due.next_review_at IS NULL
                OR r_due.next_review_at <= ?
              )
              -- 2) 오늘 이미 한 clip은 제외
              AND c.id NOT IN (
                SELECT clip_id
                FROM reviews
                WHERE reviewed_at LIKE ?
              )
            ORDER BY
              -- 신규(리뷰 없음) 먼저, 그 다음 due가 오래된 순
              CASE WHEN r_due.next_review_at IS NULL THEN 0 ELSE 1 END,
              r_due.next_review_at ASC
            LIMIT 5
            """,
            (now_str, f"{today_str}%"),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "videoId": row["video_id"],
            "startSec": row["start_sec"],
            "endSec": row["end_sec"],
            "title": row["title"],
            "nextReviewAt": row["next_review_at"],
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