# Research findings — pipeline integration & repo survey (2026-07-22)

Resolves wayfinder tickets **01 (storage)** and **02 (subscription-basis LLM execution)**,
plus fixes the overall integration architecture. All facts web-verified.

## 1. LLM execution on subscription (resolves ticket 02)

- Anthropic split billing on **15 June 2026**: programmatic usage — the **Claude Agent SDK**,
  `claude -p` headless, GitHub Actions, third-party apps — **no longer draws from the
  interactive subscription pool**. It draws from a **separate monthly Agent SDK credit**
  bundled with the plan (**Max 20× = $200/mo, Max 5× = $100/mo**), billed at standard API
  rates beyond the credit.
- **Mechanism:** drive the pipeline with the **Claude Agent SDK (Python)** (or `claude -p`),
  selecting model per call — Opus 4.8 for reconciliation, Sonnet for extraction/routing,
  Haiku for cheap bulk. This is "on subscription" via the bundled Agent SDK credit.
- **Honest caveat:** it is *included up to the monthly credit*, not unlimited; heavy batches
  can exceed it and then bill at API rates. Keep Opus calls scarce (reconciliation only).
- Sources: Claude Help Center "Use the Agent SDK with your Claude plan"; Tygart Media
  "Claude Code Billing 2026"; anthropics/claude-agent-sdk-python#559.

## 2. Embeddings are NOT a Claude capability (new constraint)

- **Anthropic has no embedding model** — Claude generates text, not vectors. Anthropic's
  recommended partner is **Voyage AI**, but that is a separate *metered, paid* API.
- **Decision:** to keep stage-1 matching free/offline and off any metered API, use **local
  embeddings** via `sentence-transformers`:
  - **BGE-M3** — best open-source quality, 1024-dim, 8192-token context, CPU-fine at this
    scale. Long context suits transcript-derived units. **Recommended default.**
  - **nomic-embed-text** (via Ollama) — fastest, `ollama pull` and go; quality slightly
    lower. Good fallback / dev option.
- Only the stage-2 **judgment** spends Claude; embeddings never do.
- Sources: Claude Platform Docs "Embeddings"; BentoML "Best Open-Source Embedding Models
  2026"; Vucense "Local Embedding Models 2026".

## 3. Vector + structured storage (resolves ticket 01)

- **LanceDB** for vectors — embedded (no server), disk-based Lance columnar format, scales
  millions→billions where **Chroma degrades past ~1M** (RAM-bound). Built-in dataset
  **versioning** (every write = a new version) — a natural fit for the time-series /
  audit-trail requirement. Caveat: multi-process concurrent writes are limited (fine for a
  single-process personal pipeline).
- **SQLite** for video/unit/run records; **flat JSON/Markdown per topic** for positions
  (positions stay few even at thousands of videos). JSON is canonical; LanceDB vectors are a
  rebuildable cache.
- Sources: 4xxi & Encore "Vector Database Comparison 2026"; aicoolies LanceDB-vs-Chroma.

## 4. Ingest resilience

- YouTube **blocks cloud-provider IPs** (AWS/GCP/Azure/DO) — often on the first call — and
  the **PoToken** proof-of-origin challenge is tightening through 2025–26.
- **Run ingest locally on the laptop's residential IP** to sidestep the block. Built-in
  fallback: `youtube-transcript-api` has native **Webshare rotating-residential-proxy**
  support; wire it as a configurable escape hatch, off by default.
- Sources: jdepoix/youtube-transcript-api #511, #593; DEV "Avoiding YouTube Blocking on GCP".

## 5. Language & reference repos (verified)

- **Python** — every off-the-shelf piece is Python-native: `yt-dlp`,
  `youtube-transcript-api`, `sentence-transformers`, `lancedb`, `claude-agent-sdk`.
- **UncleTony78/Youtube-Transcript-Analyzer-Langchain** — exists; a LangChain transcript
  summary/key-points analyzer. Borrow the *structured-output* pattern (LangChain +
  Pydantic parser), replace its generic schema with our fixed unit schema. We do **not** need
  LangChain itself — the Agent SDK gives structured JSON directly; take the *shape*, not the deps.
- Other reference repos (guimatheus92/mcp-video-analyzer, wendy7756/AI-Video-Transcriber,
  Dicklesworthstone/bulk_transcribe_youtube_videos_from_playlist) — optional, not on the
  MVP path; revisit only if bulk playlist ingest or MCP framing is wanted later.

## Resulting integration picture

```
seed/evals.txt (URLs, manual)
      │
      ▼  [local, residential IP; Webshare fallback]
   yt-dlp + youtube-transcript-api ──► SQLite: videos
      │
      ▼  Agent SDK · Sonnet
   extract units (Pydantic-validated) ──► SQLite: units
      │
      ├─► Agent SDK · Haiku/Sonnet — topic routing (multi-topic)
      │
      ▼  sentence-transformers (BGE-M3, local)
   embed unit.text ──► LanceDB (vectors, versioned)
      │
      ▼  RECONCILE  [stage 1: LanceDB top-k]  ──►  [stage 2: Agent SDK · Opus adjudicate]
   update positions (flat JSON/MD per topic) + status history
      │
      ▼  computeMaturity(position, config, now)  [pure]
      │
      ▼  render HTML digest (explain-diff-html style) — KB diff since last run
   ~/knowledgebase/digests/YYYY-MM-DD-evals.html
```
