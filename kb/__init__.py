"""YouTube AI-topic knowledge-base pipeline.

Five one-directional transforms, each its own module (see spec.md):
``ingest`` (Layer 1) → ``extract`` → ``route`` → ``reconcile`` → ``digest``.
This package currently ships Layer 1 only.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
