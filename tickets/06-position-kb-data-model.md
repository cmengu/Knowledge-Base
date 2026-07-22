# 06 — Position + per-topic KB data model (Layer 4)

Type: prototype
Status: open
Blocked by: 01, 04

## Question

Design the shape of a **position** — the living unit the KB accumulates and new units
get compared against. Prototype the data model to react to.

Must capture: canonical statement, maturity flag (open-question / emerging-trend /
converging / solved), supporting sources + dates, contested stances (both sides quoted
with source + date), status history (so we can see *when* it converged), and links to
the underlying units. Depends on the storage decision (#01) and the unit schema (#04).
Feeds the reconciliation engine (#08), maturity config (#09), and digest (#10).
