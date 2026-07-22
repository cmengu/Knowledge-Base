# 04 — Unit extraction schema (Layer 2)

Type: prototype
Status: open
Blocked by: —

## Question

Define the fixed per-video extraction schema, now that a "unit" = any content unit,
not only a thesis. Prototype the schema + a sample extraction on one real transcript
to react to.

Starting shape: per video `{topic_tags[], units[], date}`, where each unit =
`{type: claim|content, text (normalized), raw_quote, timestamp, stance, evidence_offered[]}`.
Fixed schema is what makes cross-video comparison possible. Fork the UncleTony78
LangChain analyzer's *structure*, replace its generic schema. Link the prototype +
sample output. (Schema choice is independent of storage, so unblocked; the KB data
model in #06 consumes this.)
