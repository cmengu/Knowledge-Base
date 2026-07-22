# 08 — Two-stage matcher + reconciliation engine (Layer 5, core value)

Type: prototype
Status: open
Blocked by: 02, 06

## Question

Build the core. For each incoming unit: (stage 1) vector cosine top-k against the topic's
positions; (stage 2) Opus "manager" adjudicates each candidate as
**confirming / novel / adversarial** — never merging on embedding distance alone.

- Confirming → redundant (low value) vs new-evidence-for-known (strengthens confidence).
- Novel → add as a new open position.
- Adversarial → capture both stances + evidence each side offers; flag contested; attempt
  reconciliation classified as empirical / definitional / contextual.

**Guardrail (must design in):** force quoting the specific competing claims with source +
date; make "unreconciled — genuinely open" a first-class, common output. Prototype the
prompt(s) + run on the seed set. Depends on LLM execution (#02) and the position model (#06).
