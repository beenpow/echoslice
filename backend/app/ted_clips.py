from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
import random
import re
import sqlite3

from app.ted_popular import fetch_popular_slugs
from app.ted_talk_page import fetch_talk_next_data
from app.ted_extract import extract_youtube_id, extract_transcript_cues

@dataclass(frozen=True)
class ClipCandidate:
    video_id: str
    start_sec: int
    end_sec: int
    title: str | None

class TedClipGenError(RuntimeError):
    pass

# 괄호 태그(웃음/박수 등) 제거용
_BRACKET_TAG_RE = re.compile(r"^\s*\(.*?\)\s*$")

# 흔한 비언어/무의미 태그들
_BAD_HINTS = (
    "laughter",
    "applause",
    "music",
    "audience",
    "cheers",
)

def _is_good_text(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    if len(s) < 10:
        return False
    if _BRACKET_TAG_RE.match(s):
        lowered = s.lower()
        for h in _BAD_HINTS:
            if h in lowered:
                return False
        return False
    return True

def _sum_text_len(cues: list[dict[str, Any]]) -> int:
    total = 0
    for c in cues:
        t = c.get("text")
        if isinstance(t, str):
            total += len(t)
    return total

def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return not (a_end <= b_start or b_end <= a_start)

def build_clip_candidates_from_cues(
    video_id: str,
    cues: list[dict[str, Any]],
    title: str | None,
    per_talk: int = 3,
    target_sec: int = 25,
    min_cues: int = 4,
    min_text_len: int = 120,
    max_tries: int = 80,
    seed: int | None = None,
) -> list[ClipCandidate]:
    """
    cues: [{"tSec": float, "text": str}, ...] sorted by tSec recommended
    """
    if seed is not None:
        rnd = random.Random(seed)
    else:
        rnd = random.Random()

    # 1) cue 정리
    cleaned: list[dict[str, Any]] = []
    for c in cues:
        t = c.get("tSec")
        text = c.get("text")
        if not isinstance(t, (int, float)):
            continue
        if not isinstance(text, str):
            continue
        if not _is_good_text(text):
            continue
        cleaned.append({"tSec": float(t), "text": text.strip()})

    # 시간순 정렬
    cleaned.sort(key=lambda x: x["tSec"])

    # 2) 시작 후보 인덱스들 (좋은 cue들 중에서)
    candidate_idx = list(range(len(cleaned)))
    rnd.shuffle(candidate_idx)

    picked: list[ClipCandidate] = []
    used_ranges: list[tuple[int, int]] = []

    tries = 0
    for i in candidate_idx:
        if len(picked) >= per_talk:
            break
        if tries >= max_tries:
            break
        tries += 1

        start = cleaned[i]["tSec"]
        end = start + float(target_sec)

        # 3) 범위에 포함되는 cues 모으기
        window: list[dict[str, Any]] = []
        for c in cleaned:
            if c["tSec"] < start:
                continue
            if c["tSec"] > end:
                break
            window.append(c)

        if len(window) < min_cues:
            continue
        if _sum_text_len(window) < min_text_len:
            continue

        start_i = int(start)
        end_i = int(end)

        # 4) 겹침 방지
        overlapped = False
        for (u_s, u_e) in used_ranges:
            if _overlaps(start_i, end_i, u_s, u_e):
                overlapped = True
                break
        if overlapped:
            continue

        used_ranges.append((start_i, end_i))
        picked.append(
            ClipCandidate(
                video_id=video_id,
                start_sec=start_i,
                end_sec=end_i,
                title=title,
            )
        )

    return picked

def generate_clips_for_slug(
    slug: str,
    per_talk: int = 3,
    target_sec: int = 25,
    timeout_sec: int = 10,
) -> list[ClipCandidate]:
    next_data = fetch_talk_next_data(slug, timeout_sec=timeout_sec)

    youtube_id = extract_youtube_id(next_data)
    if not youtube_id:
        return []

    # title은 있으면 넣고, 없으면 slug라도 넣자
    title = None
    try:
        title_val = (
            next_data.get("props", {})
            .get("pageProps", {})
            .get("videoData", {})
            .get("title")
        )
        if isinstance(title_val, str) and title_val.strip():
            title = title_val.strip()
    except Exception:
        pass

    cues = extract_transcript_cues(next_data)
    if not cues:
        return []

    return build_clip_candidates_from_cues(
        video_id=youtube_id,
        cues=cues,
        title=title,
        per_talk=per_talk,
        target_sec=target_sec,
    )

def insert_clip_candidates(
    conn: sqlite3.Connection,
    clips: Iterable[ClipCandidate],
) -> int:
    """
    Inserts into clips table. Returns inserted count.
    Dedup rule: same (video_id, start_sec, end_sec) exists -> skip
    """
    inserted = 0
    for c in clips:
        exists = conn.execute(
            """
            SELECT 1 FROM clips
            WHERE video_id = ? AND start_sec = ? AND end_sec = ?
            LIMIT 1
            """,
            (c.video_id, c.start_sec, c.end_sec),
        ).fetchone()
        if exists:
            continue

        conn.execute(
            """
            INSERT INTO clips (video_id, start_sec, end_sec, title)
            VALUES (?, ?, ?, ?)
            """,
            (c.video_id, c.start_sec, c.end_sec, c.title),
        )
        inserted += 1

    conn.commit()
    return inserted


def _fetch_existing_ranges(conn, video_id: str) -> list[tuple[int, int]]:
    rows = conn.execute(
        "SELECT startSec, endSec FROM clips WHERE videoId = ? ORDER BY startSec",
        (video_id,),
    ).fetchall()
    return [(int(r[0]), int(r[1])) for r in rows]

def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    # 겹침 조건: a_start < b_end AND a_end > b_start
    return a_start < b_end and a_end > b_start

def _overlaps_any(ranges: list[tuple[int, int]], start: int, end: int) -> bool:
    for s, e in ranges:
        if _overlaps(start, end, s, e):
            return True
    return False

def insert_clip_candidates_no_overlap(conn, candidates) -> int:
    """
    candidates 중에서:
    - DB에 이미 있는 구간과 겹치면 스킵
    - 같은 배치 내에서도 서로 겹치면 스킵
    그 외만 insert. (동일 start/end 중복은 기존 UNIQUE/insert 로직이 추가로 막아도 OK)
    """
    inserted = 0

    # videoId별로 기존 ranges를 한 번만 가져오고, 배치에서 채택된 ranges도 여기에 계속 추가
    cache: dict[str, list[tuple[int, int]]] = {}

    for c in candidates:
        vid = c.video_id
        start = int(c.start_sec)
        end = int(c.end_sec)

        if vid not in cache:
            cache[vid] = _fetch_existing_ranges(conn, vid)

        # DB existing + already accepted in this run 모두 포함해서 overlap 체크
        if _overlaps_any(cache[vid], start, end):
            continue

        # 여기까지 통과면 insert 시도
        # (너희 기존 insert_clip_candidate/insert_clip_candidates 로직 재사용해도 됨)
        try:
            conn.execute(
                """
                INSERT INTO clips (videoId, title, startSec, endSec)
                VALUES (?, ?, ?, ?)
                """,
                (c.video_id, c.title, start, end),
            )
            inserted += 1

            # 방금 넣은 구간을 cache에 추가해서 같은 배치 내 오버랩도 방지
            cache[vid].append((start, end))
        except Exception:
            # UNIQUE 충돌 같은 건 그냥 스킵
            continue

    conn.commit()
    return inserted
