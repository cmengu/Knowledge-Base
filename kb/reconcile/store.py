"""The per-topic position store — Layer 4 persistence + CRUD (ticket #06).

One :class:`KBStore` owns one topic's positions. On disk that is a directory per topic
under the KB data root::

    kb-data/
      evals/
        positions.json   # canonical — the source of truth
        positions.md     # derived — a human-readable, git-diffable rendering

``positions.json`` is authoritative; ``positions.md`` is rewritten from it on every save
and is never read back (mirroring the wider decision that JSON is canonical and other
representations are rebuildable caches). Keeping positions in a single small file per
topic is deliberate: the spec notes positions stay few even when videos reach the
thousands, so one file diffs cleanly and there is no per-position file sprawl.

Persistence is explicit: mutate the store in memory (``add`` / ``upsert`` / ``remove`` /
``create_position``) and call :meth:`save` to write. Reads (``get``, ``positions``,
iteration, ``in``) never touch disk. Writes are atomic (temp file + ``os.replace``) so an
interrupted run cannot leave a half-written KB. The store is single-process by design,
matching the storage research (LanceDB/JSON, one personal pipeline, no concurrent
writers).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

from kb.config import KB_DATA_DIR
from kb.reconcile.markdown import render_markdown
from kb.reconcile.schema import Maturity, Position, PositionSource

__all__ = ["KBStore", "POSITIONS_JSON", "POSITIONS_MD"]

POSITIONS_JSON = "positions.json"
POSITIONS_MD = "positions.md"

_ID_SEQ = re.compile(r"-(\d+)\Z")  # trailing "-NNNN" of a "{topic}-NNNN" position id


class KBStore:
    """The positions of a single topic, backed by ``<root>/<topic>/``.

    Construct directly with an in-memory set of positions, or (the usual path) call
    :meth:`load` to read the topic's ``positions.json`` from disk.
    """

    def __init__(
        self,
        topic: str,
        *,
        root: str | Path = KB_DATA_DIR,
        positions: list[Position] | None = None,
    ) -> None:
        if not topic:
            raise ValueError("topic must be a non-empty string")
        self.topic = topic
        self.root = Path(root)
        self._positions: dict[str, Position] = {}
        for position in positions or []:
            self._insert(position)

    # -- paths --------------------------------------------------------------

    @property
    def dir(self) -> Path:
        """The topic's directory, ``<root>/<topic>/`` (not created until :meth:`save`)."""
        return self.root / self.topic

    @property
    def json_path(self) -> Path:
        return self.dir / POSITIONS_JSON

    @property
    def md_path(self) -> Path:
        return self.dir / POSITIONS_MD

    # -- load / save --------------------------------------------------------

    @classmethod
    def load(cls, topic: str, *, root: str | Path = KB_DATA_DIR) -> "KBStore":
        """Load a topic's positions from disk (an empty store when the file is absent)."""

        store = cls(topic, root=root)
        if not store.json_path.exists():
            return store
        data = json.loads(store.json_path.read_text(encoding="utf-8"))
        stored_topic = data.get("topic")
        if stored_topic is not None and stored_topic != topic:
            raise ValueError(
                f"{store.json_path} holds topic {stored_topic!r}, not {topic!r}"
            )
        for raw in data.get("positions", []):
            store._insert(Position.model_validate(raw))
        return store

    def save(self) -> None:
        """Write ``positions.json`` (canonical) and re-render ``positions.md``.

        Both files are written atomically and deterministically — positions sorted by
        id, JSON indented with non-ASCII preserved — so unchanged data round-trips to
        byte-identical files and git diffs stay minimal.
        """

        self.dir.mkdir(parents=True, exist_ok=True)
        ordered = self.positions()
        document = {
            "topic": self.topic,
            "positions": [p.model_dump(mode="json") for p in ordered],
        }
        payload = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        _atomic_write(self.json_path, payload)
        _atomic_write(self.md_path, render_markdown(ordered, topic=self.topic))

    # -- read (CRUD: R) -----------------------------------------------------

    def get(self, position_id: str) -> Position | None:
        """Return the position with this id, or ``None`` if the topic has no such id."""
        return self._positions.get(position_id)

    def positions(self) -> list[Position]:
        """All positions in the topic, sorted by ``position_id`` (stable, diff-friendly)."""
        return [self._positions[key] for key in sorted(self._positions)]

    def __len__(self) -> int:
        return len(self._positions)

    def __iter__(self):
        return iter(self.positions())

    def __contains__(self, position_id: object) -> bool:
        return position_id in self._positions

    # -- create / update / delete (CRUD: C, U, D) ---------------------------

    def next_id(self) -> str:
        """The next free ``{topic}-NNNN`` id, one past the highest existing sequence."""

        highest = 0
        for position_id in self._positions:
            match = _ID_SEQ.search(position_id)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"{self.topic}-{highest + 1:04d}"

    def add(self, position: Position) -> Position:
        """Insert a new position; raise if its id already exists (create semantics)."""

        self._check_topic(position)
        if position.position_id in self._positions:
            raise KeyError(f"position {position.position_id!r} already exists; use upsert() to replace")
        self._positions[position.position_id] = position
        return position

    def upsert(self, position: Position) -> Position:
        """Insert or replace a position by id (update semantics)."""

        self._check_topic(position)
        self._positions[position.position_id] = position
        return position

    def remove(self, position_id: str) -> bool:
        """Delete a position by id; return whether it was present."""
        return self._positions.pop(position_id, None) is not None

    def create_position(
        self,
        *,
        statement: str,
        at: dt.datetime,
        maturity: Maturity = Maturity.open_question,
        first_source: PositionSource | None = None,
        reason: str = "opened as a new position",
    ) -> Position:
        """Mint an id, open a :class:`Position`, add it to the store, and return it.

        The ergonomic create path the reconciliation engine uses for a novel unit: the
        store assigns the next ``{topic}-NNNN`` id so callers never invent ids. The store
        is not saved — call :meth:`save` when the batch is done.
        """

        position = Position.create(
            position_id=self.next_id(),
            topic=self.topic,
            statement=statement,
            at=at,
            maturity=maturity,
            first_source=first_source,
            reason=reason,
        )
        return self.add(position)

    # -- internals ----------------------------------------------------------

    def _check_topic(self, position: Position) -> None:
        if position.topic != self.topic:
            raise ValueError(
                f"position {position.position_id!r} is topic {position.topic!r}, "
                f"not this store's {self.topic!r}"
            )

    def _insert(self, position: Position) -> None:
        """Load-time insert: trust the id, reject a duplicate or wrong-topic position."""
        self._check_topic(position)
        if position.position_id in self._positions:
            raise ValueError(f"duplicate position id {position.position_id!r}")
        self._positions[position.position_id] = position


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (temp file in the same dir, then replace)."""

    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
