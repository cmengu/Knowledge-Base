# Spec: YouTube AI-Topic Knowledge Base — evals vertical slice

Status: ready-for-agent
Related: map.md (wayfinder effort `youtube-kb`), tickets 01–10

## Problem Statement

I watch a lot of YouTube videos about AI topics — evals, small models, open source,
harnesses, enterprise adoption, SWE practices. Individually each is a data point, but
the *value* is in what accumulates: which claims get confirmed by later voices, which
are genuinely contested, which have quietly become settled consensus. Today that
synthesis lives only in my head and decays. I can't see, across dozens or hundreds of
videos over time, where a position is still open, where the field is converging, or
where two credible people flatly disagree — and I have no artifact I can read each
morning that tells me what *changed* since yesterday.

## Solution

A knowledge-accumulation pipeline. I hand-pick videos; the system ingests each,
extracts structured **units** of content, routes them to a fixed topic set, and compares
every new unit against a growing **per-topic knowledge base** of **positions**. Each
position carries a maturity flag (open-question → emerging-trend → converging → solved)
that ratchets as evidence accumulates, and contested positions preserve *both* stances
quoted with source and date rather than smoothing them into false agreement. On every
run the system emits a rich HTML **Reader's Digest** — morning-readable, with visuals —
of what's newly confirmed, net-new, or newly contested since the last run. The daily
digest is, literally, a **diff of the knowledge base**.

The first delivery is a **vertical slice**: all five layers, the single topic **evals**,
10–15 hand-picked videos — enough to prove the reconciliation concept is useful before
widening to all six topics.

## User Stories

1. As a curator, I want to drop a list of YouTube URLs into a file, so that the pipeline
   ingests exactly the videos I chose and nothing else.
2. As a curator, I want each ingested video stored as a structured record with its upload
   date, channel, view count, and chapters, so that every downstream comparison is
   anchored in time.
3. As a curator, I want transcripts pulled without needing a YouTube API key, so that
   setup is friction-free.
4. As a curator, I want re-running the pipeline on a URL I already ingested to be a no-op,
   so that batches are safe to repeat.
5. As a reader, I want each video broken into discrete units of content, so that
   comparison happens at the level of individual ideas, not whole videos.
6. As a reader, I want a unit to be captured even when it isn't a hard thesis — as
   "content" that adds value — so that useful material isn't dropped just because it
   wasn't phrased as an assertion.
7. As a reader, I want each unit that *is* an assertion captured as a claim with its
   stance and the evidence offered, so that I can later weigh who backed what.
8. As a reader, I want each unit to keep its raw quote and timestamp alongside a
   normalized statement, so that the digest can cite the exact words and moment.
9. As a reader, I want each video and each individual unit routed to one or more of the
   fixed topics, so that a single unit can inform several topics at once.
10. As a reader, I want the fixed topic set to be extensible in config, so that I can add
    topics later without reworking the pipeline.
11. As a reader, I want every new unit matched against existing positions in its topic,
    so that the system knows whether I've heard this before.
12. As a reader, I want matching to use semantic similarity *and* an LLM judge, so that a
    claim and its negation aren't merged just because they sound alike.
13. As a reader, I want a confirming unit distinguished between merely redundant and
    new-evidence-for-a-known-position, so that repeated points strengthen confidence
    without cluttering the base.
14. As a reader, I want a genuinely new unit added as a fresh open position, so that the
    base grows as I watch more.
15. As a reader, I want a contradicting unit to create or flag a contested position that
    holds *both* stances with their evidence, so that disagreement is preserved, not
    erased.
16. As a reader, I want each reconciliation attempt on a contested position classified as
    empirical, definitional, or contextual, so that I understand *why* two people disagree.
17. As a reader, I want "unreconciled — genuinely open" to be a common, first-class
    outcome, so that the system doesn't manufacture tidy conclusions that aren't real.
18. As a reader, I want every position to carry a maturity flag driven by source count,
    time span, and recent contestation, so that I can see at a glance what's settled and
    what's live.
19. As a reader, I want any adversarial unit to knock a position back to contested/open,
    so that a single credible dissent reopens a question rather than being buried.
20. As a reader, I want each position to keep a status history, so that I can see *when*
    it converged or reopened.
21. As a reader, I want the maturity thresholds to live in config, so that I can tune them
    as I learn what "converging" should mean.
22. As a reader, I want a rich HTML digest produced on every run, so that I always have
    something visual to read, never an empty file.
23. As a reader, I want the digest to show, per topic, what was newly confirmed, net-new,
    newly contested, and which maturity transitions happened since the last run, so that
    it reads like a morning briefing.
24. As a reader, I want contested items in the digest to quote both competing claims with
    source and date, so that I can judge the disagreement myself.
25. As a reader, I want any trend or "where it's going" statement in the digest to cite
    the specific videos supporting it, so that I'm never handed a confident forecast built
    on thin air.
26. As a reader, I want minority and contested views kept separate rather than smoothed
    into a narrative, so that the digest critiques rather than predicts.
27. As an operator, I want the whole pipeline to run on my Claude subscription rather than
    a metered API, so that cost is predictable.
28. As an operator, I want cheap model tiers used for bulk extraction and routing and the
    strongest tier reserved for reconciliation, so that quality lands where it matters and
    cost stays low.
29. As an operator, I want each run timestamped, so that "since last run" is well-defined.
30. As an operator, I want the slice proven on evals before widening, so that I don't
    build six topics' worth of machinery on an unproven idea.

## Implementation Decisions

**Layer boundaries as modules.** Five transforms, each its own module: `ingest`
(Layer 1), `extract` (Layer 2), `route` (Layer 3), `reconcile` (Layers 4–5, the
per-topic KB + reconciliation engine), and `digest` (output). Data flows one direction;
each stage's output is persisted so any stage can be re-run from stored inputs.

**Ingest.** yt-dlp for metadata, jdepoix/youtube-transcript-api for transcripts (no API
key). Emits one record per video: `{id, channel, date, views, transcript, chapters}`.
Video-id is the dedup key; re-ingest of a known id is a no-op. Every record carries the
upload timestamp — non-negotiable, all trend logic is time-series.

**Unit schema (the comparison atom).** Per video: `{topic_tags[], units[], date}`. Each
unit: `{type: claim|content, text (normalized), raw_quote, timestamp, stance,
evidence_offered[]}`. A "unit" is any content unit, not only a thesis; prefer `claim`
when there's an assertion, else `content`. Fixed schema is what makes cross-video
comparison possible. Structure forked from the UncleTony78 LangChain analyzer, generic
schema replaced.

**Topic routing.** LLM classifier routes each video and each unit to ≥1 topic from the
fixed set (evals, small-models, open-source, harness, enterprise, swe-practices), set
extensible via config. Multi-topic assignment allowed per unit. Slice consumes only
`evals`-routed units downstream, but routing over all six is built now.

**Matching — two stages, never merge on distance alone.** Stage 1: vector cosine top-k
retrieval of candidate positions. Stage 2: the Opus "manager" adjudicates each candidate
as confirming / novel / adversarial. Confirming splits into redundant vs
new-evidence-for-known. Novel becomes a new open position. Adversarial creates/flags a
contested position holding both stances + evidence, with a reconciliation attempt typed
empirical / definitional / contextual, and "unreconciled — open" as a valid outcome.

**Anti-manufactured-agreement guardrail.** The adjudicator must quote the specific
competing claims with source + date, and "unreconciled — genuinely open" is a
first-class output. This is a design requirement of the prompt, not a nicety.

**Position data model.** A position holds: canonical statement, maturity flag,
supporting sources + dates, contested stances (both quoted with source + date), status
history, and links to underlying units.

**Maturity state machine (config-driven, applied every batch).** Defaults: `open` = <2
independent sources; `emerging` = ≥2 sources one direction spanning <3 months;
`converging` = ≥3 sources agreeing >3 months with no recent contest; `solved` = ≥3
sources, no contesting unit in the last N videos. Any adversarial unit resets to
contested/open. Transitions recorded in status history. Thresholds live in config.

**Model routing (subscription basis).** Opus 4.8 = reconciliation/adjudication manager;
Sonnet = extraction/structure + routing; Haiku = cheapest bulk steps where quality
allows. Fable escalation deferred on cost. *How* automated batched calls run on the
subscription rather than metered API is an open research decision (ticket 02) that gates
every LLM layer.

**Storage.** Starting recommendation (ticket 01): SQLite for video records + transcripts
+ unit rows; LanceDB (embedded, disk-based) for the vector index; flat JSON/Markdown per
topic for positions (positions stay few even when videos reach the thousands). JSON is
canonical, vectors are a derived cache rebuildable from it.

**Digest output.** On every run, a rich HTML briefing rendered in the `/explain-diff-html`
style — because the digest *is* a diff of the KB since the last run. Per topic it shows
newly confirmed, net-new, newly contested (both stances quoted + dated), and maturity
transitions since last run, with citations for any trend claim.

## Testing Decisions

Good tests here assert **external behavior at the two deterministic seams**, never
prompt wording or LLM internals.

- **`reconcile(incomingUnits, topicKB) → {updatedKB, deltas}`** — the core seam. The LLM
  adjudicator is an injected dependency; tests supply fixture units + a fixture KB + a
  fake adjudicator returning scripted verdicts, and assert the resulting classification,
  the new/updated positions, the contested-both-stances capture, and the emitted deltas.
  This is the single highest-value seam and covers Layers 4–5.
- **`computeMaturity(position, config, now) → flag`** — a pure function. Table-driven
  tests over the threshold config: source-count boundaries, time spans, the
  adversarial-resets-to-open rule, and the resulting status-history entry.
- **`ingest`** — tested at its boundary with recorded yt-dlp/transcript fixtures (no live
  network): dedup no-op on a known id, timestamp always present, record shape.

Prior art: none in this fresh repo; establish the injected-dependency pattern here as the
convention. LLM prompt quality (extraction/routing/adjudication) is evaluated against a
small fixture/eval set with known-good outputs — not asserted in unit tests, because it's
non-deterministic.

## Out of Scope

- **Prediction / forecasting as a headline feature.** The pipeline is strongest at
  cross-video critique and weakest at prediction; minority views stay separate, trend
  claims stay citation-bound. Forecasting is not a destination goal.
- **Non-YouTube / multi-platform ingest.**
- **Full population of the other five topics** — the slice is evals-only; widening is a
  later effort.
- **Automation / scheduling** the morning run (cron/watcher). Manual run for the slice.
- **Fable escalation** for hard adjudications (cost-gated, later).

## Further Notes

- The whole effort is charted as the wayfinder map `youtube-kb` (`map.md`) with tickets
  01–10; this spec is the synthesized PRD across them. Ticket 02 (subscription-basis LLM
  execution) is the highest-risk unknown and gates every LLM-touching layer.
- Curation stays manual and human — the system never auto-selects videos.
