"""SQLite persistence for ingested video records.

The ``videos`` table is Layer 1's output and the dedup boundary: ``id`` is the
primary key, ``date`` is ``NOT NULL`` (the mandatory-timestamp invariant lives
in the schema as well as the model), and :meth:`VideoStore.add` is
insert-or-ignore so writing a known id is a genuine no-op.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

from .models import VideoRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id           TEXT PRIMARY KEY,
    channel      TEXT NOT NULL,
    date         TEXT NOT NULL,          -- ISO 8601 upload timestamp, MANDATORY
    views        INTEGER,                -- may be NULL (e.g. hidden view count)
    transcript   TEXT NOT NULL,          -- JSON list of {text,start,duration}
    chapters     TEXT NOT NULL,          -- JSON list of {start,end,title}
    title        TEXT,
    url          TEXT,
    ingested_at  TEXT NOT NULL           -- ISO 8601 moment the row was written
);
"""

_COLUMNS = (
    "id",
    "channel",
    "date",
    "views",
    "transcript",
    "chapters",
    "title",
    "url",
    "ingested_at",
)


class VideoStore:
    """A thin, idempotent SQLite gateway for :class:`VideoRecord` rows.

    Usable as a context manager. Pass ``":memory:"`` for tests.
    """

    def __init__(self, database: str | Path = ":memory:") -> None:
        self.database = str(database)
        if self.database != ":memory:":
            parent = Path(self.database).parent
            if parent and not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.database)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- context manager -------------------------------------------------
    def __enter__(self) -> "VideoStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    # -- reads -----------------------------------------------------------
    def exists(self, video_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM videos WHERE id = ? LIMIT 1", (video_id,)
        )
        return cur.fetchone() is not None

    def get(self, video_id: str) -> VideoRecord | None:
        cur = self._conn.execute(
            "SELECT * FROM videos WHERE id = ? LIMIT 1", (video_id,)
        )
        row = cur.fetchone()
        return VideoRecord.from_row(dict(row)) if row is not None else None

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0])

    def iter_videos(self) -> Iterator[VideoRecord]:
        cur = self._conn.execute("SELECT * FROM videos ORDER BY date ASC, id ASC")
        for row in cur:
            yield VideoRecord.from_row(dict(row))

    def all(self) -> list[VideoRecord]:
        return list(self.iter_videos())

    # -- writes ----------------------------------------------------------
    def add(self, record: VideoRecord) -> bool:
        """Insert a record; a known id is a no-op.

        Returns ``True`` if a row was written, ``False`` if the id was already
        present (the dedup no-op). Existing rows are never overwritten. Dedup is
        an explicit ``exists`` check rather than ``INSERT OR IGNORE`` so that a
        genuine constraint violation (e.g. a NULL in a NOT NULL column) raises
        loudly instead of being silently swallowed.
        """
        if self.exists(record.id):
            return False
        row = record.to_row()
        placeholders = ", ".join("?" for _ in _COLUMNS)
        self._conn.execute(
            f"INSERT INTO videos ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
            tuple(row[c] for c in _COLUMNS),
        )
        self._conn.commit()
        return True
