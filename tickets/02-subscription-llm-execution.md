# 02 — Run automated LLM calls on the Claude subscription (not metered API)

Type: research
Status: open
Blocked by: —

## Question

The user wants **everything on the Claude subscription basis**, not pay-per-token API.
How do we drive automated, batched pipeline LLM calls (extraction, routing,
reconciliation) under a subscription?

Investigate and recommend: headless Claude Code CLI invocations, the Claude Agent SDK,
MCP, or another path — including how model tiers (Opus manager / Sonnet structure /
Haiku bulk) are selected per call, rate/quota realities for hundreds→thousands of
videos, and idempotent re-run behavior. This blocks every LLM-touching layer.
Output: a recommendation doc linked from this ticket.
