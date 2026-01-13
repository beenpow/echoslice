from __future__ import annotations

import json
import re
from typing import Any

import requests

TED_TALK_URL = "https://www.ted.com/talks/{slug}"

class TedTalkPageError(RuntimeError):
    pass

# __NEXT_DATA__ 스크립트 태그에서 JSON 본문만 뽑기
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(?P<json>.*?)</script>',
    re.DOTALL,
)

def fetch_talk_html(slug: str, timeout_sec: int = 10) -> str:
    if not slug or not isinstance(slug, str):
        raise ValueError("slug must be a non-empty string")

    url = TED_TALK_URL.format(slug=slug)
    headers = {
        "Accept": "text/html",
        "User-Agent": "EchoSlice/0.1 (+local dev)",
        "Referer": "https://www.ted.com/talks?sort=popular",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=timeout_sec)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        raise TedTalkPageError(f"Failed to fetch talk page: {url} ({e})")

def extract_next_data_from_html(html: str) -> dict[str, Any]:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise TedTalkPageError("__NEXT_DATA__ script not found in HTML")

    raw = m.group("json").strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise TedTalkPageError(f"__NEXT_DATA__ JSON decode failed: {e}") from e

    if not isinstance(data, dict):
        raise TedTalkPageError("__NEXT_DATA__ parsed JSON is not a dict")

    return data

def fetch_talk_next_data(slug: str, timeout_sec: int = 10) -> dict[str, Any]:
    html = fetch_talk_html(slug, timeout_sec=timeout_sec)
    return extract_next_data_from_html(html)