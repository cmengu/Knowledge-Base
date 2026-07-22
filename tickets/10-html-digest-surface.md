# 10 — HTML "Reader's Digest" output surface (the user's priority)

Type: prototype
Status: open
Blocked by: 08

## Question

The primary output. On each run, produce a rich **HTML briefing** — Reader's Digest style,
morning-readable, with visuals, never an empty file — of what changed in the KB since the
last run. The daily digest is literally a **diff of the knowledge base**, so adapt the
`/explain-diff-html` skill's style to KB deltas.

Must show per topic (evals for the slice): newly confirmed, net-new positions, newly
contested items (both stances quoted with source + date), maturity transitions since last
run, and citations for anything trend-like. Prototype the HTML on a real run's output.
Depends on the reconciliation engine producing deltas (#08).
