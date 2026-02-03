from __future__ import annotations

import json
import os
import random
import time
import re
from typing import Any
from app.db import gemini_calls_today, log_gemini_call
from app.ted_talk_page import fetch_talk_next_data
from app.ted_extract import extract_youtube_id, extract_transcript_cues
from app.youtube_transcript import fetch_youtube_transcript, fetch_youtube_transcript_whisper
from app.ted_clips import (
    ClipCandidate,
    build_clip_candidates_from_cues,
    generate_clips_for_slug,
)

MAX_TEXT_CHARS = 280  # 튜닝 가능
GEMINI_DAILY_LIMIT = 50

# 1순위만 시도, 실패 시 fallback 없이 스킵 (대본=Whisper만, 구간=Gemini만)
PREFER_FIRST_ONLY = True

class GeminiDailyLimitExceeded(RuntimeError):
    pass

def _try_import_genai():
    try:
        from google import genai  # type: ignore
        return genai, None
    except Exception as e:
        return None, e

def _get_api_key() -> str | None:
    return (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GENAI_API_KEY")
    )

def _safe_title(next_data: dict[str, Any], fallback: str) -> str:
    try:
        title_val = (
            next_data.get("props", {})
            .get("pageProps", {})
            .get("videoData", {})
            .get("title")
        )
        if isinstance(title_val, str) and title_val.strip():
            return title_val.strip()
    except Exception:
        pass
    return fallback

def _extract_retry_delay_seconds(msg: str) -> int | None:
    """
    Gemini 429 에러 메시지에서 retryDelay(예: '52s' 또는 'Please retry in 52.3s')를 추출한다.
    """
    # case 1: "'retryDelay': '52s'"
    m = re.search(r"retryDelay'\s*:\s*'(\d+)s'", msg)
    if m:
        return int(m.group(1))

    # case 2: "Please retry in 52.363s."
    m = re.search(r"retry in\s+(\d+)(?:\.\d+)?s", msg, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))

    return None

def _window_text(cues: list[dict[str, Any]], start_sec: int, end_sec: int) -> str:
    parts: list[str] = []
    for c in cues:
        t = c.get("tSec")
        text = c.get("text")
        if not isinstance(t, (int, float)):
            continue
        if t < start_sec:
            continue
        if t > end_sec:
            break
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return " ".join(parts).strip()


def _log_supply_debug(
    slug: str,
    title: str,
    youtube_id: str,
    transcript_source: str | None,
    cues: list[dict[str, Any]],
    rough: list[ClipCandidate],
    picked_indices: list[int],
    cues_full: list[dict[str, Any]] | None = None,
) -> None:
    """Pretty-print transcript, candidate segments, and selected clips for manual verification."""
    sep = "=" * 72
    small_sep = "-" * 72
    cues_for_segments = cues_full if cues_full is not None else cues

    print(sep)
    print(f"[echoslice] supply debug slug={slug}")
    print(f" title: {title}")
    print(f" youtube_id: {youtube_id}")
    print(f" transcript_source: {transcript_source or 'unknown'}")
    print(sep)

    print("\n▼ 대본 전체 (cues)")
    print(small_sep)
    for i, c in enumerate(cues[:80]):  # first 80 lines
        t = c.get("tSec", 0)
        text = (c.get("text") or "").replace("\n", " ").strip()
        preview = text[:80] + ("…" if len(text) > 80 else "")
        print(f"  [{i:3d}] {t:7.1f}s  {preview}")
    if len(cues) > 80:
        print(f"  ... and {len(cues) - 80} more cues")
    print(small_sep)

    print("\n▼ 후보 구간 (candidates, 구간 나눈 결과)")
    print(small_sep)
    for i, c in enumerate(rough):
        print(f"  [{i}]  {c.start_sec}s ~ {c.end_sec}s  (duration {c.end_sec - c.start_sec}s)")
    print(small_sep)

    print("\n▼ 선택된 구간 (Gemini가 고른 것)")
    print(small_sep)
    for idx in picked_indices:
        if 0 <= idx < len(rough):
            c = rough[idx]
            url = f"https://www.youtube.com/watch?v={c.video_id}&t={int(c.start_sec)}"
            print(f"  index={idx}  video_id={c.video_id}  {c.start_sec}s ~ {c.end_sec}s")
            print(f"  → 확인: {url}")
    print(small_sep)

    print("\n▼ 선택된 구간별 대사 (해당 시간에 나와야 할 멘트)")
    print(small_sep)
    for idx in picked_indices:
        if 0 <= idx < len(rough):
            clip = rough[idx]
            print(f"\n  [선택 #{idx}]  {clip.start_sec}s ~ {clip.end_sec}s")
            # 이 구간에 해당하는 cue만 필터 (전체 대본 기준)
            for cue in cues_for_segments:
                t = cue.get("tSec")
                text = (cue.get("text") or "").replace("\n", " ").strip()
                if not isinstance(t, (int, float)) or not text:
                    continue
                if t < clip.start_sec:
                    continue
                if t > clip.end_sec:
                    break
                print(f"    {t:7.1f}s  {text}")
            print("")
    print(small_sep)
    print("")

def _gemini_pick_indices_safe(
    *,
    conn,
    reason: str,
    model: str,
    title: str,
    video_id: str,
    candidates: list[dict[str, Any]],
    k: int,
) -> tuple[list[int], dict[str, Any]]:
    """서버 레벨 비용 안전장치: 오늘 Gemini 호출 횟수 하드 리밋."""
    if conn is not None:
        used = gemini_calls_today(conn)
        if used >= GEMINI_DAILY_LIMIT:
            raise GeminiDailyLimitExceeded(
                f"Gemini daily limit reached ({used}/{GEMINI_DAILY_LIMIT})"
            )

    indices, meta = _gemini_pick_indices(
        model=model,
        title=title,
        video_id=video_id,
        candidates=candidates,
        k=k,
    )

    if conn is not None:
        log_gemini_call(conn, reason)

    return indices, meta

def _gemini_pick_indices(
    *,
    model: str,
    title: str,
    video_id: str,
    candidates: list[dict[str, Any]],
    k: int,
) -> tuple[list[int], dict[str, Any]]:
    genai, import_err = _try_import_genai()
    if genai is None:
        raise RuntimeError(f"google-genai not installed: {import_err}")

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY (or GOOGLE_API_KEY)")

    client = genai.Client(api_key=api_key)

    schema = {
        "type": "object",
        "properties": {
            "selected": {
                "type": "array",
                "minItems": k,
                "maxItems": k,
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                        "reason": {"type": "string"},
                        "qualityFlags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["index", "difficulty", "reason", "qualityFlags"],
                },
            }
        },
        "required": ["selected"],
    }

    payload = {
        "task": "Pick best speaking-practice clip windows. Do NOT create new timestamps. Only choose indices from candidates.",
        "talk": {"title": title, "videoId": video_id},
        "k": k,
        "criteria": {
            "prefer": ["coherent standalone idea", "good for shadowing", "clear phrasing"],
            "avoid": ["only laughter/applause/music", "meaningless short text", "mid-sentence cut if possible"],
        },
        "candidates": candidates,
        "output": "Return JSON matching schema.",
    }

    resp = client.models.generate_content(
        model=model,
        contents=json.dumps(payload, ensure_ascii=False),
        config={
            "response_mime_type": "application/json",
            "response_schema": schema,
            "temperature": 0.2,
        },
    )

    raw = getattr(resp, "text", None)
    if not isinstance(raw, str) or not raw.strip():
        raw = json.dumps(getattr(resp, "parsed", {}), ensure_ascii=False)

    data = json.loads(raw)
    selected = data.get("selected", [])
    if not isinstance(selected, list) or len(selected) != k:
        raise RuntimeError("Invalid Gemini response: selected length mismatch")

    indices: list[int] = []
    for item in selected:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if isinstance(idx, int):
            indices.append(idx)

    if len(indices) != k:
        raise RuntimeError("Invalid Gemini response: indices parse failed")

    if len(set(indices)) != k:
        raise RuntimeError("Invalid Gemini response: duplicate indices")

    n = len(candidates)
    if any(i < 0 or i >= n for i in indices):
        raise RuntimeError("Invalid Gemini response: index out of range")

    return indices, {"selected": selected}

import re

def is_sentence_start_cue(text: str) -> bool:
    if not text:
        return False

    text = text.strip()

    # 1) 대문자로 시작
    if not text[0].isupper():
        return False

    # 2) 접속사/후치 접속어로 시작하는 것 제거
    bad_starts = (
        "And ", "But ", "So ", "Or ", "Because ",
        "And\n", "But\n", "So\n",
    )
    for b in bad_starts:
        if text.startswith(b):
            return False

    # 3) 너무 짧은 조각 제거
    if len(text) < 15:
        return False

    return True

def generate_ai_clips_for_slug(
    slug: str,
    conn=None,
    per_talk: int = 3,
    model: str = "gemini-2.5-flash",
    max_candidates: int = 18,
    target_sec: int = 25,
    timeout_sec: int = 10,
) -> tuple[list[ClipCandidate], dict[str, Any]]:
    meta: dict[str, Any] = {
        "slug": slug,
        "mode": "ai",
        "model": model,
        "perTalk": per_talk,
        "maxCandidates": max_candidates,
    }
    print(f"[echoslice] supply slug={slug} start")
    try:
        next_data = fetch_talk_next_data(slug, timeout_sec=timeout_sec)
        youtube_id = extract_youtube_id(next_data)
        if not youtube_id:
            meta["mode"] = "skip"
            meta["skipReason"] = "no_youtube_id"
            print(f"[echoslice] supply slug={slug} skip no_youtube_id")
            return [], meta

        title = _safe_title(next_data, fallback=slug)

        # 1) Whisper 2) youtube-transcript-api 3) TED cues. PREFER_FIRST_ONLY면 Whisper만 시도
        first_only = PREFER_FIRST_ONLY
        cues = []
        try:
            cues = fetch_youtube_transcript_whisper(youtube_id, model_name="base")
            if cues:
                meta["transcriptSource"] = "whisper"
        except Exception as e:
            meta["transcriptSourceError"] = f"whisper: {type(e).__name__}: {e}"
        if not cues and not first_only:
            try:
                cues = fetch_youtube_transcript(youtube_id)
                if cues:
                    meta["transcriptSource"] = "youtube"
            except Exception as e:
                meta["transcriptSourceError"] = (meta.get("transcriptSourceError") or "") + f" youtube_api: {type(e).__name__}: {e}"
        if not cues and not first_only:
            cues = extract_transcript_cues(next_data)
            if cues:
                meta["transcriptSource"] = "ted"
        if not cues:
            meta["mode"] = "skip"
            meta["skipReason"] = "no_cues"
            if first_only:
                print(f"[echoslice] supply slug={slug} skip no_cues (PREFER_FIRST_ONLY)")
            else:
                print(f"[echoslice] supply slug={slug} skip no_cues")
            return [], meta

        print(f"[echoslice] supply slug={slug} transcript_source={meta.get('transcriptSource', '?')}")
        cues = [c for c in cues if isinstance(c, dict)]
        cues.sort(key=lambda c: float(c.get("tSec", 0.0)))

        # print("ALL CUES ###########")
        # for i, c in enumerate(cues):
        #     t = float(c.get("tSec", 0.0))
        #     text = c.get("text", "").replace("\n", " ").strip()
        #     preview = text[:120] + ("…" if len(text) > 120 else "")
        #     print(f"[{i:03d}] tSec={t:8.3f} | {preview}")

        # Printing all selected cue elements
        sentence_cues = [
            c for c in cues
            if is_sentence_start_cue(c.get("text", ""))
        ]

        # fallback: 너무 적으면 전체 cues 사용
        if len(sentence_cues) >= per_talk * 2:
            cues_for_build = sentence_cues
        else:
            cues_for_build = cues

        # print("GOOD QUALITY CUES ###########")
        # for i, c in enumerate(cues_for_build):
        #     t = float(c.get("tSec", 0.0))
        #     text = c.get("text", "").replace("\n", " ").strip()
        #     preview = text[:120] + ("…" if len(text) > 120 else "")
        #     print(f"[{i:03d}] tSec={t:8.3f} | {preview}")

        seed = random.randint(1, 1_000_000_000)
        rough = build_clip_candidates_from_cues(
            video_id=youtube_id,
            cues=cues_for_build,
            title=title,
            per_talk=max_candidates,
            target_sec=target_sec,
            max_tries=max(80, max_candidates * 10),
            seed=seed,
        )

        if len(rough) < per_talk:
            meta["mode"] = "skip"
            meta["skipReason"] = "not_enough_candidates"
            print(f"[echoslice] supply slug={slug} skip not_enough_candidates (have {len(rough)} need {per_talk})")
            return [], meta

        cand_payload: list[dict[str, Any]] = []
        for i, c in enumerate(rough):
            text = _window_text(cues_for_build, c.start_sec, c.end_sec)
            if len(text) > MAX_TEXT_CHARS:
                text = text[:MAX_TEXT_CHARS].rstrip() + "…"

            cand_payload.append(
                {
                    "index": i,
                    "startSec": c.start_sec,
                    "endSec": c.end_sec,
                    "text": text,
                }
            )

        try:
            time.sleep(5)
            start_ts = time.time()
            print(f"[echoslice] supply slug={slug} gemini pick start")
            picked_indices, picked_meta = _gemini_pick_indices_safe(
                conn=conn,
                reason=f"pick_indices:{slug}",
                model=model,
                title=title,
                video_id=youtube_id,
                candidates=cand_payload,
                k=per_talk,
            )
            print(f"[echoslice] supply slug={slug} gemini pick ok ({time.time() - start_ts:.1f}s)")
        except Exception as e:
            msg = str(e)
            # 429 RESOURCE_EXHAUSTED면 retryDelay만큼 기다렸다가 1회 재시도
            if ("429" in msg) or ("RESOURCE_EXHAUSTED" in msg):
                delay = _extract_retry_delay_seconds(msg) or 2
                time.sleep(min(delay, 10))  # 너무 길게는 안 기다림 (최대 10초)
                picked_indices, picked_meta = _gemini_pick_indices(
                    model=model,
                    title=title,
                    video_id=youtube_id,
                    candidates=cand_payload,
                    k=per_talk,
                )
            else:
                raise
        except GeminiDailyLimitExceeded as e:
            if PREFER_FIRST_ONLY:
                meta["mode"] = "skip"
                meta["skipReason"] = "gemini_daily_limit"
                meta["segmentSelection"] = "skip_first_only"
                print(f"[echoslice] supply slug={slug} skip gemini_daily_limit (PREFER_FIRST_ONLY)")
                return [], meta
            meta["mode"] = "fallback"
            meta["fallbackReason"] = f"gemini_daily_limit: {e}"
            meta["segmentSelection"] = "naive"
            print(f"[echoslice] supply slug={slug} segment_selection=naive fallback")
            return generate_clips_for_slug(slug, per_talk=per_talk, target_sec=target_sec), meta

        meta["picked"] = picked_indices
        meta["gemini"] = picked_meta
        meta["segmentSelection"] = "gemini"
        print(f"[echoslice] supply slug={slug} segment_selection=gemini ok")

        _log_supply_debug(
            slug=slug,
            title=title,
            youtube_id=youtube_id,
            transcript_source=meta.get("transcriptSource"),
            cues=cues_for_build,
            rough=rough,
            picked_indices=picked_indices,
            cues_full=cues,
        )

        return [rough[i] for i in picked_indices], meta

    except Exception as e:
        meta["mode"] = "error"
        meta["error"] = f"{type(e).__name__}: {e}"
        print(f"[echoslice] supply slug={slug} error {type(e).__name__}: {e}")
        raise
