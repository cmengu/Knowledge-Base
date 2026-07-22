# Map: YouTube AI-Topic Knowledge Base — evals vertical slice

Label: wayfinder:map

## Destination

A working **vertical-slice pipeline** — all 5 layers — over the **evals** topic on
10–15 hand-picked videos, that on each run emits a rich HTML **"Reader's Digest"**
of what's newly confirmed / novel / contested in the knowledge base since the last run,
proving the reconciliation concept is useful before widening to all six topics.

This map's destination is a **built, working slice**, not just a spec.

## Notes

**Domain.** Personal knowledge-accumulation system over a manually-curated set of
YouTube AI videos. Full spec: `~/knowledgebase/SPEC.md`. Value is cross-video
**critique over time**, not prediction.

**Execution is in scope** (overrides wayfinder's plan-don't-do default): the destination
is a running slice, so `task` tickets that *build* are expected alongside decision tickets.

**Skills each session should consult:** `/explain-diff-html` (the output-surface style —
the daily digest is literally a *diff of the KB* since last run), `/prototype`,
`/grilling`, `/domain-modeling`.

**Settled by the user's briefing (standing context, not tickets):**
- *Unit definition* — a "unit" = any content unit from a video, not only a thesis.
  Capture as a **claim** (assertion) when there is one; otherwise as **content** (value-add).
  Most units are claims.
- *Matching* — two-stage: (1) vector cosine top-k, (2) LLM judge for same / novel /
  adversarial. **Never merge on embedding distance alone.**
- *Model routing (subscription basis, no metered API)* — Opus 4.8 = "manager"
  (reconciliation / adjudication); Sonnet = extraction / structure + topic routing;
  Haiku = cheapest bulk steps where quality allows. Fable escalation deferred (cost).
- *Maturity state machine* — adopt recommended default thresholds, config-driven, tunable.
- *Batch / idempotency* — batch = a list of URLs; video-id = dedup key; runs timestamped;
  per-position status history.
- *MVP* — vertical slice on **evals**, 10–15 videos; widen after it proves useful.
- *Guardrails* — force quoting competing claims with source + date; "unreconciled — open"
  is a valid, common output; keep prediction minimal and citation-bound.

## Decisions so far

<!-- one line per resolved ticket -->

## Not yet specified

- Widening from the evals slice to all six topics (routing tuning, per-topic KB bootstrap).
- Cross-topic units (one unit routed to several topics) — dedup/linking at scale.
- Automation / scheduling — the "morning, a run kicks off, I read it" trigger (cron, watcher).
  Manual run is fine for the slice.
- Escalation to Fable for the hardest adjudications (cost-gated, later).

## Out of scope

- **Prediction / forecasting as a headline feature** — spec + user both call it the weakest
  axis; minority views stay separate, not smoothed into a narrative. Not a destination goal.
- **Non-YouTube / multi-platform ingest.**
- **Full population of the other five topics** (post-slice effort).
