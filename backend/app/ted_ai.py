from __future__ import annotations

import json
import os
import random
from typing import Any

from app.ted_talk_page import fetch_talk_next_data
from app.ted_extract import extract_youtube_id, extract_transcript_cues
from app.ted_clips import (
    ClipCandidate,
    build_clip_candidates_from_cues,
    generate_clips_for_slug,
)

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

def generate_ai_clips_for_slug(
    slug: str,
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

    try:
        next_data = fetch_talk_next_data(slug, timeout_sec=timeout_sec)
        youtube_id = extract_youtube_id(next_data)
        if not youtube_id:
            meta["mode"] = "fallback"
            meta["fallbackReason"] = "no_youtube_id"
            return generate_clips_for_slug(slug, per_talk=per_talk, target_sec=target_sec), meta

        title = _safe_title(next_data, fallback=slug)
        cues = extract_transcript_cues(next_data)
        if not cues:
            meta["mode"] = "fallback"
            meta["fallbackReason"] = "no_cues"
            return generate_clips_for_slug(slug, per_talk=per_talk, target_sec=target_sec), meta

        cues = [c for c in cues if isinstance(c, dict)]
        cues.sort(key=lambda c: float(c.get("tSec", 0.0)))

        seed = random.randint(1, 1_000_000_000)
        rough = build_clip_candidates_from_cues(
            video_id=youtube_id,
            cues=cues,
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
            cand_payload.append(
                {
                    "index": i,
                    "startSec": c.start_sec,
                    "endSec": c.end_sec,
                    "text": _window_text(cues, c.start_sec, c.end_sec),
                }
            )

        picked_indices, picked_meta = _gemini_pick_indices(
            model=model,
            title=title,
            video_id=youtube_id,
            candidates=cand_payload,
            k=per_talk,
        )

        meta["picked"] = picked_indices
        meta["gemini"] = picked_meta
        return [rough[i] for i in picked_indices], meta

    except Exception as e:
        meta["mode"] = "fallback"
        meta["fallbackReason"] = f"{type(e).__name__}: {e}"
        return generate_clips_for_slug(slug, per_talk=per_talk, target_sec=target_sec), meta
