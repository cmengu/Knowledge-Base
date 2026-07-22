# 01 — Storage architecture for thousands of videos

Type: research
Status: open
Blocked by: —

## Question

Pick the concrete storage stack. Must hold: raw per-video records + transcripts
(hundreds → thousands of videos), a vector index for semantic matching, and the
per-topic positions with status history. Recommend a stack, justify it at scale,
and note migration cost if we outgrow it.

Starting hypothesis to validate/refute: **SQLite** (video records + transcripts +
unit rows) + **LanceDB** (embedded, disk-based vectors — scales past Chroma) +
**flat JSON/Markdown per topic** for positions (positions are few even when videos
are many). Output: a short recommendation doc linked from this ticket.
