from app.db import init_db, DB_PATH
from app.db import get_conn, count_unreviewed_clips, is_slug_blocked, block_slug
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import random
import time
import os
from typing import Any
from app.ted_popular import fetch_popular_slugs
from app.ted_talk_page import fetch_talk_next_data
from app.ted_extract import extract_youtube_id, extract_transcript_cues
from app.ted_clips import generate_clips_for_slug, insert_clip_candidates_no_overlap
from app.ted_ai import generate_ai_clips_for_slug


TODAY_LIMIT = 5
REVIEW_TARGET = 2
MIN_UNUSED_NEW = 30  # 30 minimum new clip stock count

SUPPLY_MAX_PAGE = 308         # popular page 7312/24 = 308
SUPPLY_TALKS_PER_ROUND = 6    # 한 라운드에서 시도할 talk 수
SUPPLY_MAX_ROUNDS = 30         # 무한루프 방지
SUPPLY_SLEEP_SEC = 3.2        # 과도 호출 방지(필요시 0.2 같은 값)

DEFAULT_SUPPLY_PER_TALK = 3
DEFAULT_SUPPLY_MODEL = "gemini-2.5-flash"
DEFAULT_SUPPLY_MAX_CANDIDATES = 18

SLUG_COOLDOWN_SEC = 60 * 60  # 1시간
_slug_last_tried: dict[str, float] = {}

SUPPLY_GLOBAL_TIMEOUT_SEC = 60 * 5# (AI 한번당 12 ~ 20초 + 15s sleep)* 5개 talk

k = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
print("[Gemini] key suffix:", k[-6:] if k else "NONE")

app = FastAPI(title="EchoSlice API", version="0.0.1")

# Frontend dev server(CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://echoslicefront.vercel.app",
    ],
    allow_credentials=False,
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

    # 핵심: (기본 재고 MIN_UNUSED_NEW)와 (오늘 필요한 slots_left) 중 더 큰 값만큼은 확보
    min_needed = max(MIN_UNUSED_NEW, slots_left)
    print("min_needed : " + str(min_needed))

    ensure_new_stock(conn, min_needed)

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
    print("reviews_ids size : " + str(pos))
    for cid in new_ids:
        conn.execute(
            "INSERT INTO today_queue (day, position, clip_id, kind) VALUES (?, ?, ?, 'new')",
            (day, pos, cid),
        )
        pos += 1
    print("new_ids size : " + str(pos))
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
    ensure_new_stock(conn, MIN_UNUSED_NEW)
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
class RerollOneRequest(BaseModel):
    position: int
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

def ensure_new_stock(conn: sqlite3.Connection, min_unused: int):
    unused_cnt = count_unreviewed_clips(conn)
    if unused_cnt >= min_unused:
        return

    # ensure_new_clips는 "최종 최소 개수 보장"으로 쓰는 게 가장 깔끔
    ensure_new_clips(
        conn=conn,
        min_needed=min_unused,
        per_talk=DEFAULT_SUPPLY_PER_TALK,
        model=DEFAULT_SUPPLY_MODEL,
        max_candidates=DEFAULT_SUPPLY_MAX_CANDIDATES,
    )

def _should_skip_slug(slug: str) -> bool:
    now = time.time()
    last = _slug_last_tried.get(slug)
    if last is not None and (now - last) < SLUG_COOLDOWN_SEC:
        return True
    _slug_last_tried[slug] = now
    return False

def ensure_new_clips(
    conn,
    min_needed: int,
    per_talk: int,
    model: str,
    max_candidates: int,
) -> dict:
    """
    DB에 unreviewed(new) clip이 min_needed개 이상이 되도록,
    TED popular를 랜덤 page에서 돌며 supply를 반복한다.
    transcript/youtubeId 없으면 그 talk는 스킵한다.
    """
    before = count_unreviewed_clips(conn)
    target = before + max(0, min_needed)
    start_ts = time.time()

    rounds = 0
    total_inserted = 0
    attempted_talks = 0
    skipped_talks = 0
    errors = 0
    print("target count : " + str(target))
    while count_unreviewed_clips(conn) < target and rounds < SUPPLY_MAX_ROUNDS:
        if time.time() - start_ts > SUPPLY_GLOBAL_TIMEOUT_SEC:
            print("timeout from ensure_new_clips() ")
            break
        rounds += 1
        page = random.randint(0, SUPPLY_MAX_PAGE)
        print("selected page : " + str(page))
        print("rounds: " + str(rounds))

        # page에서 후보 슬러그 가져오기
        all_slugs = fetch_popular_slugs(page=page)  # 너네 함수명에 맞춰서
        random.shuffle(all_slugs)
        slugs = all_slugs[:SUPPLY_TALKS_PER_ROUND]

        for slug in slugs:
            if is_slug_blocked(conn, slug):
                skipped_talks += 1
                continue
            if _should_skip_slug(slug):
                skipped_talks += 1
                continue
            if time.time() - start_ts > SUPPLY_GLOBAL_TIMEOUT_SEC:
                print("timeout from ensure_new_clips() 2")
                break
            attempted_talks += 1
            try:
                inserted = supply_one_talk_ai(
                    conn=conn,
                    slug=slug,
                    per_talk=per_talk,
                    model=model,
                    max_candidates=max_candidates,
                )
                if inserted == 0:
                    skipped_talks += 1
                total_inserted += inserted

                if count_unreviewed_clips(conn) >= target:
                    break

                if SUPPLY_SLEEP_SEC > 0:
                    time.sleep(SUPPLY_SLEEP_SEC)

            except Exception:
                errors += 1
                # 한 talk 에러는 전체 공급을 멈추지 않고 계속
                continue

        if count_unreviewed_clips(conn) >= target:
            break

    after = count_unreviewed_clips(conn)
    return {
        "beforeNew": before,
        "afterNew": after,
        "requestedAdd": min_needed,
        "actuallyAdded": max(0, after - before),
        "rounds": rounds,
        "attemptedTalks": attempted_talks,
        "skippedTalks": skipped_talks,
        "errors": errors,
        "model": model,
        "maxCandidates": max_candidates,
        "perTalk": per_talk,
    }

def supply_one_talk_ai(
    conn,
    slug: str,
    per_talk: int,
    model: str,
    max_candidates: int,
) -> int:
    """
    slug 하나에 대해:
    - talk 페이지에서 youtubeId + transcript cues 추출
    - 후보 max_candidates 만들고
    - Gemini로 per_talk개 pick
    - insert_clip_candidates_no_overlap로 겹침 없이 insert
    """
    print("call starts")
    # 1) AI로 클립 후보 pick
    #    반환이 ClipCandidate 리스트라고 가정 (video_id/start_sec/end_sec/title 포함)
    picked, meta = generate_ai_clips_for_slug(
        slug=slug,
        conn=conn,
        per_talk=per_talk,
        model=model,
        max_candidates=max_candidates,
    )
    print(picked)
    print(meta)
    print("call ends")
    if meta.get("mode") == "skip":
        print("supply_one_talk_ai: skipped")
        reason = meta.get("skipReason", "unknown_skip")
        block_slug(conn, slug, reason)
        return 0
    # 2) DB insert (겹침 금지)
    source = meta.get("mode", "unknown")  # "ai" or "fallback"
    inserted = insert_clip_candidates_no_overlap(
        conn,
        picked,
        talk_slug=slug,
        source=source,
    )
    print(inserted)
    return inserted


@app.get("/debug/ted/popular")
def debug_ted_popular(page: int = 0):
    slugs = fetch_popular_slugs(page=page)
    return {"page" : page, "count": len(slugs), "slugs": slugs}

@app.get("/debug/ted/talk_next_data")
def debug_ted_talk_next_data(slug: str):
    data = fetch_talk_next_data(slug)
    return {"slug": slug, "topKeys": list(data.keys())}

@app.get("/debug/ted/talk_extract")
def debug_ted_talk_extract(slug: str):
    data = fetch_talk_next_data(slug)
    youtube_id = extract_youtube_id(data)
    cues = extract_transcript_cues(data)

    preview = cues[:10]

    return {
        "slug": slug,
        "youtubeId": youtube_id,
        "cueCount": len(cues),
        "cuePreview": preview,
    }

@app.get("/ted/supply")
def ted_supply(page: int = 0, talks: int = 5, perTalk: int = 3):
    """
    page: TED popular page index
    talks: 몇 개 talk를 처리할지
    perTalk: talk당 몇 개 clip 만들지
    """
    if talks <= 0 or talks > 30:
        raise HTTPException(status_code=400, detail="talks must be 1..30")
    if perTalk <= 0 or perTalk > 10:
        raise HTTPException(status_code=400, detail="perTalk must be 1..10")

    slugs = fetch_popular_slugs(page=page)
    slugs = slugs[:talks]

    created = 0
    attempted = 0
    details = []

    with get_conn() as conn:
        for slug in slugs:
            attempted += 1
            candidates = generate_clips_for_slug(slug, per_talk=perTalk)
            ins = insert_clip_candidates(conn, candidates)
            created += ins
            details.append({"slug": slug, "generated": len(candidates), "inserted": ins})

    return {
        "page": page,
        "talks": talks,
        "perTalk": perTalk,
        "attempted": attempted,
        "created": created,
        "details": details,
    }


@app.get("/ted/supply_ai")
def ted_supply_ai(
    page: int = 0,
    talks: int = 5,
    perTalk: int = 3,
    model: str = "gemini-2.5-flash",
    maxCandidates: int = 18,
):
    """
    Step14:
    - 후보 구간은 랜덤으로 많이 만들고(maxCandidates)
    - Gemini가 그 중 perTalk개만 pick
    - Gemini 실패하면 ted_clips.generate_clips_for_slug로 fallback
    """
    if talks <= 0 or talks > 30:
        raise HTTPException(status_code=400, detail="talks must be 1..30")
    if perTalk <= 0 or perTalk > 10:
        raise HTTPException(status_code=400, detail="perTalk must be 1..10")
    if maxCandidates < perTalk or maxCandidates > 60:
        raise HTTPException(status_code=400, detail="maxCandidates must be perTalk..60")

    all_slugs = fetch_popular_slugs(page=page)
    slugs = random.sample(all_slugs, k=min(talks, len(all_slugs)))

    created = 0
    attempted = 0
    details = []

    with get_conn() as conn:
        for slug in slugs:
            attempted += 1
            candidates, meta = generate_ai_clips_for_slug(
                slug=slug,
                conn=conn,
                per_talk=perTalk,
                model=model,
                max_candidates=maxCandidates,
            )

            source = meta.get("mode", "unknown")  # "ai" or "fallback"
            ins = insert_clip_candidates_no_overlap(conn, candidates, talk_slug=slug, source=source)
            created += ins

            details.append(
                {
                    "slug": slug,
                    "mode": meta.get("mode"),
                    "skipReason": meta.get("skipReason"),  # no_cues / no_youtube_id
                    "error": meta.get("error"),             # exception message (optional)
                    "generated": len(candidates),
                    "inserted": ins,
                }
            )

    return {
        "page": page,
        "talks": talks,
        "perTalk": perTalk,
        "model": model,
        "maxCandidates": maxCandidates,
        "attempted": attempted,
        "created": created,
        "details": details,
    }


@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok", "service": "echoslice-backend"}

@app.get("/db/health")
def db_health():
    return {"db": "ok", "path": str(DB_PATH)}

@app.get("/today")
def get_today_payload():
    day = today_str_utc()

    with get_conn() as conn:
        rows = fetch_today_queue(conn, day)
        if not rows:
            rows = create_today_queue(conn, day, TODAY_LIMIT, REVIEW_TARGET)

        today_clips = [
            {
                "position": r["position"],
                "id": r["id"],
                "videoId": r["video_id"],
                "startSec": r["start_sec"],
                "endSec": r["end_sec"],
                "title": r["title"],
                "kind": r["kind"],
            }
            for r in rows
        ]

        done_rows = conn.execute(
            "SELECT DISTINCT clip_id FROM reviews WHERE reviewed_at LIKE ?",
            (f"{day}%",),
        ).fetchall()
        completed_clip_ids = [d["clip_id"] for d in done_rows]

    return {
        "day": day,
        "clips": today_clips,
        "completedClipIds": completed_clip_ids,
    }

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

@app.post("/clips/today/reroll_one")
def reroll_today_one(req: RerollOneRequest):
    day = today_str_utc()

    with get_conn() as conn:
        # 1) 해당 슬롯이 있는지, 그리고 new인지 확인
        row = conn.execute(
            """
            SELECT clip_id, kind
            FROM today_queue
            WHERE day = ? AND position = ?
            """,
            (day, req.position),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Slot not found")

        if row["kind"] != "new":
            raise HTTPException(status_code=400, detail="Only 'new' slots can be rerolled")

        old_clip_id = row["clip_id"]

        # 2) 새로 뽑을 후보 clip 1개 선택
        # ensure new stock before reroll
        ensure_new_stock(conn, MIN_UNUSED_NEW)

        # 조건: 오늘 큐에 이미 들어간 clip 제외, 그리고 기존 clip도 제외
        new_row = conn.execute(
            """
            SELECT c.id
            FROM clips c
            LEFT JOIN reviews r ON r.clip_id = c.id
            WHERE r.clip_id IS NULL
            AND c.id NOT IN (
                SELECT clip_id FROM today_queue WHERE day = ?
            )
            AND c.id != ?
            ORDER BY RANDOM()
            LIMIT 1
            """,
            (day, old_clip_id),
        ).fetchone()

        if not new_row:
            raise HTTPException(status_code=400, detail="No available new clips to reroll")

        new_clip_id = new_row["id"]

        # 3) today_queue의 해당 position만 교체
        conn.execute(
            """
            UPDATE today_queue
            SET clip_id = ?
            WHERE day = ? AND position = ?
            """,
            (new_clip_id, day, req.position),
        )
        conn.commit()

    # 4) 간단히 OK 반환 (프론트가 /today를 다시 fetch해서 갱신)
    return {"ok": True, "day": day, "position": req.position, "clipId": new_clip_id}

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