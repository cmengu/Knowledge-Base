# Knowledge base — evals

4 position(s), 1 contested. Canonical data lives in `positions.json`; this file is a rendered view.

## evals-0001 — ◑ converging

**Evaluating an LLM system is different from evaluating an LLM model — you must evaluate your own system on the task it is meant to solve, not just the base model.**

_3 source(s) · 132-day span_

**Sources**

- "evaluating LLM systems is not the same as evaluating LLM models, which is usually done through benchmarks"
  — K8LLVi5Xrh8 · 2025-05-11 · affirms · `K8LLVi5Xrh8#0`
- "if you're building a specific application like a chatbot or even a simpler prompt chain you need to test it on the tasks that it is meant to solve"
  — K8LLVi5Xrh8 · 2025-05-11 · affirms · `K8LLVi5Xrh8#2`
- "[illustrative] benchmarks tell you about the model, evals tell you about your product"
  — demo-eval-talk-02 · 2025-07-08 · affirms · `demo-eval-talk-02#4`
- "[illustrative] stop shipping on vibes; measure the system you actually built"
  — demo-eval-talk-03 · 2025-09-20 · affirms · `demo-eval-talk-03#7`

**Status history**

- 2025-05-11 — opened as open-question: first stated in the ingested evals talk (`K8LLVi5Xrh8#0`)
- 2025-07-08 — open-question → emerging-trend: a second, independent voice agreed (`demo-eval-talk-02#4`)
- 2025-09-20 — emerging-trend → converging: three independent sources agreeing over >3 months, no contest (`demo-eval-talk-03#7`)

## evals-0002 — ◔ emerging trend

**For a specialized system (e.g. RAG), build your own evaluation rather than reaching for an off-the-shelf public benchmark.**

_2 source(s) · 58-day span_

**Sources**

- "So if you are building a RAG system don't search for a RAG benchmark - build your own."
  — K8LLVi5Xrh8 · 2025-05-11 · affirms · `K8LLVi5Xrh8#3`
- "[illustrative] a generic RAG leaderboard won't tell you if YOUR retrieval works"
  — demo-eval-talk-02 · 2025-07-08 · affirms · `demo-eval-talk-02#9`

**Status history**

- 2025-05-11 — opened as open-question: stated in the ingested evals talk (`K8LLVi5Xrh8#3`)
- 2025-07-08 — open-question → emerging-trend: a second source agreed within three months (`demo-eval-talk-02#9`)

## evals-0003 — ○ open question

**Manual evaluation is the right place to start; automation scales human judgment but does not replace it.**

_1 source(s) · single source_

**Sources**

- "The first obvious solution to this complexity is manual evaluations, and honestly that's where you should start."
  — K8LLVi5Xrh8 · 2025-05-11 · affirms · `K8LLVi5Xrh8#16`
- "Automated evaluations are there to scale your judgment, not to replace it. If you don't know yet what you're evaluating manually, there is nothing to automate."
  — K8LLVi5Xrh8 · 2025-05-11 · affirms · `K8LLVi5Xrh8#19`

**Status history**

- 2025-05-11 — opened as open-question: single source so far — genuinely open (`K8LLVi5Xrh8#16`)

## evals-0004 — ⚔ contested

**LLM-as-a-judge is reliable enough to depend on for evaluating LLM outputs.**

_2 source(s) · 84-day span_

**Supporting**

- "And it works surprisingly well. Just remember that your LLM judge is like a small machine learning project in itself and it also requires some tuning and evaluation."
  — K8LLVi5Xrh8 · 2025-05-11 · affirms · `K8LLVi5Xrh8#28`

**Opposing** (contested — both stances kept)

- "[illustrative] an uncalibrated LLM judge is confidently wrong; don't trust it raw"
  — demo-critic-05 · 2025-08-03 · denies · `demo-critic-05#2`

**Status history**

- 2025-05-11 — opened as open-question: stated (with a caveat) in the ingested evals talk (`K8LLVi5Xrh8#28`)
- 2025-08-03 — open-question → contested: a credible dissent — both stances now kept side by side (`demo-critic-05#2`)
