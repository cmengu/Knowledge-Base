"""YouTube AI-topic knowledge-base pipeline.

Five one-directional transforms, each its own subpackage (spec → Implementation
Decisions → "Layer boundaries as modules"):

    ingest   (Layer 1)   URL      -> video record {id, channel, date, ...}
    extract  (Layer 2)   record   -> ExtractedVideo {topic_tags, units, date}   <- ticket #04
    route    (Layer 3)   units    -> topic assignments (multi-topic)             <- ticket #07
    reconcile(Layers 4-5)units    -> per-topic knowledge base of positions
    digest   (output)    KB diff  -> HTML Reader's Digest

Implemented so far: `extract` (ticket #04) — the fixed per-video unit schema plus the
transcript -> validated-units step; and `route` (ticket #07) — the LLM topic router that
assigns each video and each unit to one or more topics from the fixed, config-driven set.
"""

__version__ = "0.1.0"
