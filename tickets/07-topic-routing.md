# 07 — Topic routing (Layer 3)

Type: prototype
Status: open
Blocked by: 02, 04

## Question

Build the LLM classifier that routes each video AND each individual unit to one or more
topics from the fixed set (evals, small-models, open-source, harness, enterprise,
swe-practices). Prototype the routing prompt + test on extracted units.

Runs on the cheap tier (Sonnet/Haiku per #02's mechanism). Must allow multi-topic
assignment for a single unit. For the slice, only `evals`-routed units flow downstream,
but routing over all six is built now so widening is free. Depends on the LLM execution
mechanism (#02) and the unit schema (#04).
