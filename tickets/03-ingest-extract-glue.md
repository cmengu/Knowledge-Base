# 03 — Ingest + extract glue (Layer 1)

Type: task
Status: open
Blocked by: —

## Question

Build the glue that turns a YouTube URL into one JSON record:
`{id, channel, date, views, transcript, chapters}`. yt-dlp for metadata,
jdepoix/youtube-transcript-api for transcripts (no API key).

Done when: given a list of URLs, it emits one timestamped record per video, dedup by
video-id, safe to re-run. **Every record must carry the upload timestamp** — all
downstream trend logic is time-series. No LLM involved here, so this is unblocked and
buildable now.
