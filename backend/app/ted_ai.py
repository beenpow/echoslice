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
from app.ted_clips import (
    ClipCandidate,
    build_clip_candidates_from_cues,
    generate_clips_for_slug,
)

MAX_TEXT_CHARS = 280  # 튜닝 가능
GEMINI_DAILY_LIMIT = 50

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
    print("generate_ai_clips_for_slug")
    try:
        next_data = fetch_talk_next_data(slug, timeout_sec=timeout_sec)
        youtube_id = extract_youtube_id(next_data)
        if not youtube_id:
            meta["mode"] = "skip"
            meta["skipReason"] = "no_youtube_id"
            print("generate_ai_clips_for_slug: skip :: no youtube id")
            return [], meta

        title = _safe_title(next_data, fallback=slug)
        cues = extract_transcript_cues(next_data)
        if not cues:
            meta["mode"] = "skip"
            meta["skipReason"] = "no_cues"
            print("generate_ai_clips_for_slug: skip :: no cues")
            return [], meta

        cues = [c for c in cues if isinstance(c, dict)]
        cues.sort(key=lambda c: float(c.get("tSec", 0.0)))

        print("ALL CUES ###########")
        for i, c in enumerate(cues):
            t = float(c.get("tSec", 0.0))
            text = c.get("text", "").replace("\n", " ").strip()
            preview = text[:120] + ("…" if len(text) > 120 else "")
            print(f"[{i:03d}] tSec={t:8.3f} | {preview}")

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

        print("GOOD QUALITY CUES ###########")
        for i, c in enumerate(cues_for_build):
            t = float(c.get("tSec", 0.0))
            text = c.get("text", "").replace("\n", " ").strip()
            preview = text[:120] + ("…" if len(text) > 120 else "")
            print(f"[{i:03d}] tSec={t:8.3f} | {preview}")

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
            meta["mode"] = "fallback"
            meta["fallbackReason"] = "not_enough_candidates"
            meta["candidateCount"] = len(rough)
            return generate_clips_for_slug(slug, per_talk=per_talk, target_sec=target_sec), meta

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
            print("going to sleep for 5 seconds")
            time.sleep(5)
            start_ts = time.time()
            picked_indices, picked_meta = _gemini_pick_indices_safe(
                conn=conn,
                reason=f"pick_indices:{slug}",
                model=model,
                title=title,
                video_id=youtube_id,
                candidates=cand_payload,
                k=per_talk,
            )
            elapsed_ts = time.time() - start_ts
            print("time took to _gemini_pick_indices : " + str(elapsed_ts))
            print("generate_ai_clips_for_slug: 5")
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
            meta["mode"] = "fallback"
            meta["fallbackReason"] = f"gemini_daily_limit: {e}"
            return generate_clips_for_slug(slug, per_talk=per_talk, target_sec=target_sec), meta


        meta["picked"] = picked_indices
        meta["gemini"] = picked_meta
        return [rough[i] for i in picked_indices], meta

    except Exception as e:
        meta["mode"] = "error"
        meta["error"] = f"{type(e).__name__}: {e}"
        raise
