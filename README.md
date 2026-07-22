# Knowledge-Base — YouTube AI-topic pipeline

A personal knowledge-accumulation system over a hand-picked set of YouTube AI videos.
The system ingests each chosen video, extracts structured **units** of content, routes
them to a fixed topic set, and compares every new unit against a growing per-topic
knowledge base of **positions**. Each position carries a maturity flag
(open → emerging → converging → solved) that ratchets as evidence accumulates, and
contested positions preserve *both* stances quoted with source and date. On every run
the system emits a rich HTML **Reader's Digest** — literally a *diff of the knowledge
base* since the last run.

The first delivery is a **vertical slice**: all five layers, the single topic `evals`,
10–15 hand-picked videos — enough to prove the reconciliation concept before widening to
all six topics.

## Contents

- **[map.md](map.md)** — the wayfinder map: destination, scope, standing decisions.
- **[spec.md](spec.md)** — the synthesized PRD (problem, solution, user stories,
  implementation + testing decisions).
- **[research/integration-findings.md](research/integration-findings.md)** — web-verified
  findings that resolve tickets 01 & 02 and reshape the integration architecture
  (Agent-SDK-on-subscription, local BGE-M3 embeddings, residential-IP ingest).

## Tickets

| # | Title | Type | Blocked by |
|---|-------|------|------------|
| [01](tickets/01-storage-architecture.md) | Storage architecture for thousands of videos | research | — |
| [02](tickets/02-subscription-llm-execution.md) | Run automated LLM calls on the Claude subscription | research | — |
| [03](tickets/03-ingest-extract-glue.md) | Ingest + extract glue (Layer 1) | task | — |
| [04](tickets/04-unit-extraction-schema.md) | Unit extraction schema (Layer 2) | prototype | — |
| [05](tickets/05-seed-video-set.md) | Seed video set for the evals slice | task | — |
| [06](tickets/06-position-kb-data-model.md) | Position + per-topic KB data model (Layer 4) | prototype | 01, 04 |
| [07](tickets/07-topic-routing.md) | Topic routing (Layer 3) | prototype | 02, 04 |
| [08](tickets/08-reconciliation-engine.md) | Two-stage matcher + reconciliation engine (Layer 5) | prototype | 02, 06 |
| [09](tickets/09-maturity-state-machine.md) | Maturity state machine config | task | 06 |
| [10](tickets/10-html-digest-surface.md) | HTML "Reader's Digest" output surface | prototype | 08 |

## Pipeline shape

```
seed/evals.txt (URLs, manual)
      │  [local, residential IP]
   ingest ──► SQLite: videos
      │  Agent SDK · Sonnet
   extract units ──► SQLite: units
      │  Agent SDK · Haiku/Sonnet
   route to topics (multi-topic)
      │  sentence-transformers (BGE-M3, local)
   embed ──► LanceDB (vectors, versioned)
      │  stage 1: LanceDB top-k   stage 2: Agent SDK · Opus adjudicate
   reconcile ──► positions (flat JSON/MD per topic) + status history
      │  computeMaturity(position, config, now)
   render HTML digest ──► digests/YYYY-MM-DD-evals.html
```
