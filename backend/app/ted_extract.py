from __future__ import annotations

import json
from typing import Any


class TedExtractError(RuntimeError):
    pass


def _get_nested(d: Any, keys: list[str]) -> Any:
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def extract_youtube_id(next_data: dict[str, Any]) -> str | None:
    """
    Extract YouTube video id from __NEXT_DATA__.

    In many TED pages:
      next_data["props"]["pageProps"]["videoData"]["playerData"] is a JSON string.
      After json.loads(playerData):
        ["external"]["service"] == "YouTube"
        ["external"]["code"] is the YouTube id.
    """
    player_data_str = _get_nested(next_data, ["props", "pageProps", "videoData", "playerData"])
    if not isinstance(player_data_str, str) or not player_data_str:
        return None

    try:
        player_data = json.loads(player_data_str)
    except json.JSONDecodeError:
        return None

    if not isinstance(player_data, dict):
        return None

    external = player_data.get("external")
    if not isinstance(external, dict):
        return None

    if external.get("service") != "YouTube":
        return None

    code = external.get("code")
    if isinstance(code, str) and code:
        return code

    return None


def _extract_paragraphs_any(next_data: dict[str, Any]) -> list[Any] | None:
    """
    TED transcript paragraphs can appear in (at least) two shapes:

    A) props.pageProps.videoData.transcriptData.translation.paragraphs
    B) props.pageProps.transcriptData.translation.paragraphs   (videoData 밖)

    We'll try A then B.
    """
    paths = [
        ["props", "pageProps", "videoData", "transcriptData", "translation", "paragraphs"],
        ["props", "pageProps", "transcriptData", "translation", "paragraphs"],
    ]

    for keys in paths:
        paragraphs = _get_nested(next_data, keys)
        if isinstance(paragraphs, list):
            return paragraphs

    return None


def extract_transcript_cues(next_data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract transcript cues from __NEXT_DATA__.

    Expected cue format:
      paragraphs[].cues[].{time,text}

    time is in milliseconds (int). We'll convert to seconds float.

    Returns:
      list of {"tSec": float, "text": str} sorted by tSec
    """
    paragraphs = _extract_paragraphs_any(next_data)
    if not isinstance(paragraphs, list):
        return []

    cues_out: list[dict[str, Any]] = []
    for p in paragraphs:
        if not isinstance(p, dict):
            continue
        cues = p.get("cues")
        if not isinstance(cues, list):
            continue

        for c in cues:
            if not isinstance(c, dict):
                continue

            text = c.get("text")
            t_ms = c.get("time")

            if not isinstance(text, str) or not text.strip():
                continue
            if not isinstance(t_ms, (int, float)):
                continue

            # TED cue time is milliseconds
            t_sec = float(t_ms) / 1000.0
            cues_out.append({"tSec": t_sec, "text": text.strip()})

    cues_out.sort(key=lambda x: x["tSec"])
    return cues_out
