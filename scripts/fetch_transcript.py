#!/usr/bin/env python3
"""Fetch one YouTube transcript into a fixture (run locally, on a residential IP).

This is a thin prototype helper for ticket #04 — it produces the transcript fixture the
extraction prototype consumes. The real Layer 1 ingest (ticket #03) will pull metadata
via yt-dlp and dedup by video id; here we only need the timestamped transcript plus the
provenance we already verified by hand, so metadata is passed in as flags rather than
scraped. Not imported by the package or the tests.

Usage:
    python scripts/fetch_transcript.py K8LLVi5Xrh8 \
        --title "Introduction to LLM evaluations in 10 key ideas" \
        --channel "Hugging Face" --date 2025-05-11
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi

from kb.config import FIXTURES_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id", help="YouTube video id (not the full URL)")
    parser.add_argument("--title", default="")
    parser.add_argument("--channel", default="")
    parser.add_argument("--date", default="", help="Upload date, ISO (YYYY-MM-DD)")
    parser.add_argument("--languages", default="en", help="Comma-separated language priority")
    parser.add_argument("--out", default=None, help="Output path (default fixtures/transcripts/<id>.json)")
    args = parser.parse_args()

    languages = [code.strip() for code in args.languages.split(",") if code.strip()]
    fetched = YouTubeTranscriptApi().fetch(args.video_id, languages=languages)
    segments = [
        {"text": snippet.text, "start": round(snippet.start, 3), "duration": round(snippet.duration, 3)}
        for snippet in fetched
    ]

    document = {
        "video_id": args.video_id,
        "title": args.title,
        "channel": args.channel,
        "url": f"https://www.youtube.com/watch?v={args.video_id}",
        "date": args.date,
        "language": fetched.language_code,
        "segments": segments,
    }

    out = Path(args.out) if args.out else FIXTURES_DIR / "transcripts" / f"{args.video_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(segments)} segments ({sum(len(s['text']) for s in segments)} chars) -> {out}")


if __name__ == "__main__":
    main()
