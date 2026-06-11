"""
One-off local script: fetch YouTube transcripts for all clips that don't
have a cached transcript_json yet, and store them in the clips table.

Run locally (not from Render) since YouTube blocks cloud-provider IPs.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_conn
from app.transcript import get_clip_transcript


def main():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, video_id, start_sec, end_sec, title FROM clips "
            "WHERE transcript_json IS NULL ORDER BY id"
        ).fetchall()

        print(f"{len(rows)} clip(s) without cached transcript")

        for row in rows:
            clip_id = row["id"]
            try:
                segments = get_clip_transcript(row["video_id"], row["start_sec"], row["end_sec"])
            except Exception as e:
                print(f"  clip {clip_id}: FAILED ({e})")
                continue

            conn.execute(
                "UPDATE clips SET transcript_json = %s WHERE id = %s",
                (json.dumps(segments), clip_id),
            )
            conn.commit()
            print(f"  clip {clip_id}: {len(segments)} segments cached")
            time.sleep(2)


if __name__ == "__main__":
    main()
