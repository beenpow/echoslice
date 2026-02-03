"""
Fetch transcript (captions) from YouTube by video_id.

- fetch_youtube_transcript: unofficial youtube-transcript-api (fast, but may be out of sync if video has intro).
- fetch_youtube_transcript_whisper: download audio + Whisper ASR (local compute, timestamps match actual audio).
Returns same cue format: [{"tSec": float, "text": str}, ...].

Whisper path requires: ffmpeg on PATH (for loading audio).
"""
from __future__ import annotations

import os
import tempfile
import time
from typing import Any

# Whisper model cached for reuse (avoids reload per video)
_whisper_model = None


def _get_whisper_model(model_name: str = "base"):
    global _whisper_model
    if _whisper_model is None:
        try:
            import whisper
        except ImportError as e:
            raise RuntimeError("openai-whisper not installed") from e
        _whisper_model = whisper.load_model(model_name)
    return _whisper_model


def fetch_youtube_transcript_whisper(
    video_id: str,
    model_name: str = "base",
) -> list[dict[str, Any]]:
    """
    Download audio from YouTube and run Whisper ASR. Returns cues with timestamps
    that match the actual audio file (same as the video). No API cost; uses local CPU/GPU.

    Requires: yt-dlp, openai-whisper, ffmpeg on PATH.

    model_name: "tiny" (fastest) | "base" | "small" | "medium" | "large"
    """
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"
    cues: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        outtmpl = os.path.join(tmpdir, "audio.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
        }
        t0 = time.time()
        print(f"[echoslice] whisper video_id={video_id} download start")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            print(f"[echoslice] whisper video_id={video_id} download error {type(e).__name__}: {e}")
            raise RuntimeError(f"yt-dlp download failed: {e}") from e
        print(f"[echoslice] whisper video_id={video_id} download ok ({time.time() - t0:.1f}s)")

        # Find the downloaded file (audio.webm, audio.m4a, etc.)
        audio_path = None
        for name in os.listdir(tmpdir):
            if name.startswith("audio."):
                audio_path = os.path.join(tmpdir, name)
                break
        if not audio_path or not os.path.isfile(audio_path):
            raise RuntimeError("yt-dlp did not produce an audio file")

        model = _get_whisper_model(model_name)
        t1 = time.time()
        print(f"[echoslice] whisper video_id={video_id} transcribe start model={model_name}")
        result = model.transcribe(audio_path, fp16=False)
        print(f"[echoslice] whisper video_id={video_id} transcribe ok ({time.time() - t1:.1f}s)")

        for seg in result.get("segments") or []:
            start = seg.get("start")
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            if not isinstance(start, (int, float)):
                continue
            cues.append({"tSec": float(start), "text": text})

    cues.sort(key=lambda x: x["tSec"])
    print(f"[echoslice] whisper video_id={video_id} ok total={time.time() - t0:.1f}s segments={len(cues)}")
    return cues


def fetch_youtube_transcript(video_id: str) -> list[dict[str, Any]]:
    """
    Fetch transcript for a YouTube video. Returns cues in our standard format:
    [{"tSec": float, "text": str}, ...] sorted by tSec.

    Raises:
        Exception: on fetch failure (no captions, disabled, etc.)
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as e:
        raise RuntimeError("youtube-transcript-api not installed") from e

    raw = YouTubeTranscriptApi.get_transcript(video_id)
    if not raw:
        return []

    cues: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        start = item.get("start")
        if not isinstance(text, str) or not text.strip():
            continue
        if not isinstance(start, (int, float)):
            continue
        cues.append({"tSec": float(start), "text": text.strip()})

    cues.sort(key=lambda x: x["tSec"])
    return cues
