from youtube_transcript_api import YouTubeTranscriptApi


def get_clip_transcript(video_id: str, start_sec: float, end_sec: float) -> list[dict]:
    """
    Fetch the YouTube transcript for video_id and return only the segments
    that overlap [start_sec, end_sec], sorted by start time.
    """
    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id)

    segments = []
    for snippet in transcript:
        seg_start = snippet.start
        seg_end = snippet.start + snippet.duration
        if seg_end >= start_sec and seg_start <= end_sec:
            segments.append({
                "start": seg_start,
                "end": seg_end,
                "text": snippet.text,
            })

    return segments
