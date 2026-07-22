"""YouTube AI-topic knowledge-base pipeline.

Five one-directional transforms, each its own subpackage (spec → Implementation
Decisions → "Layer boundaries as modules"):

    ingest   (Layer 1)   URL      -> video record {id, channel, date, ...}
    extract  (Layer 2)   record   -> ExtractedVideo {topic_tags, units, date}
    route    (Layer 3)   units    -> topic assignments (multi-topic)
    reconcile(Layers 4-5)units    -> per-topic knowledge base of positions
    digest   (output)    KB diff  -> HTML Reader's Digest
"""

__version__ = "0.1.0"
