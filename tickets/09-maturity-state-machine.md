# 09 — Maturity state machine config

Type: task
Status: open
Blocked by: 06

## Question

Write the config that drives each position's maturity flag, using the recommended
defaults (tunable later):

- `open` = <2 independent sources
- `emerging` = ≥2 sources, one direction, spanning <3 months
- `converging` = ≥3 sources agreeing over >3 months, no recent contest
- `solved` = ≥3 sources, no contesting unit in the last N videos
- **any adversarial unit knocks the position back to `contested`/`open`**

Done when: thresholds live in a config file the reconciliation engine reads and applies
every batch (not one-time), and status transitions are recorded in the position's history.
Depends on the position model (#06).
