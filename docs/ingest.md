# Layer 1 — Ingest

Turns a file of hand-picked YouTube URLs into one structured record per video,
stored in SQLite. No LLM is involved. This is the first stage of the pipeline
(`ingest → extract → route → reconcile → digest`).

## What it produces

One row per video with the canonical shape
`{id, channel, date, views, transcript, chapters}` plus additive operational
fields (`title`, `url`, `ingested_at`):

- **`id`** — the 11-char YouTube video id; the **dedup key** for the whole pipeline.
- **`date`** — the upload timestamp, ISO 8601 UTC. **Mandatory on every record**
  (all downstream trend logic is time-series). A video whose metadata carries no
  upload time is *failed*, never stored.
- **`channel`**, **`views`** — from yt-dlp (`views` may be null if hidden).
- **`transcript`** — timestamped segments `[{text, start, duration}, …]` from
  `youtube-transcript-api` (no API key). Segment timestamps are preserved so
  Layer 2 can cite the exact moment of a quote.
- **`chapters`** — `[{start, end, title}, …]`, empty when the video has none.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e .          # runtime deps: yt-dlp, youtube-transcript-api, PyYAML
```

## Run

```bash
python -m kb.ingest seed/evals.example.txt
# or with an explicit DB / config:
python -m kb.ingest seed/evals.txt --config config/ingest.yaml --db data/kb.sqlite3
```

The seed file is one URL or bare id per line; blank lines, `#` full-line
comments, and whitespace-preceded inline `# comments` are ignored. Accepted URL
forms: `watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`, `/live/`, `/v/`, and a
bare 11-char id.

Flags: `--db PATH` (overrides config), `--quiet` (summary only), `--strict`
(exit non-zero if any entry failed).

## Idempotency (safe to re-run)

The video id is the dedup key. On a re-run, a **known id is skipped before any
network call** — a true no-op. A *failed* video (unparseable input, missing
upload timestamp, or no transcript) is **not** persisted, so a later re-run
retries it rather than skipping it forever.

## Running location and the proxy escape hatch

Ingest is meant to run on your **local residential IP** — YouTube blocks
cloud/datacenter IPs. If you must run from a blocked network, enable
`youtube-transcript-api`'s native **Webshare rotating-residential-proxy** support
in `config/ingest.yaml`:

```yaml
proxy:
  enabled: true                     # OFF by default
  webshare_proxy_username: "..."
  webshare_proxy_password: "..."
```

An enabled proxy with missing credentials fails fast at startup.

## Storage

SQLite (`config.database`, default `data/knowledge_base.sqlite3`), one `videos`
table. `id` is the primary key and `date` is `NOT NULL`, so the mandatory-
timestamp invariant is enforced by the schema as well as the model. Nested
fields (`transcript`, `chapters`) are stored as JSON text.

## Tests

Deterministic and fully offline — no live network, no LLM. The two network
dependencies are injected; tests feed the core `ingest()` seam recorded yt-dlp /
transcript fixtures (`tests/fixtures/`) captured from a one-off live run.

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```
