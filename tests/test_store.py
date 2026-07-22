"""VideoStore: dedup no-op, round-trip, and the NOT NULL timestamp guard."""

from __future__ import annotations

import sqlite3

import pytest

from kb.models import VideoRecord
from kb.store import VideoStore


def _record(vid: str, date: str = "2023-11-23T02:27:48Z", **over) -> VideoRecord:
    base = dict(
        id=vid,
        channel="Chan",
        date=date,
        views=1,
        transcript=[{"text": "hi", "start": 0.0, "duration": 1.0}],
        chapters=[],
        ingested_at="2026-07-22T00:00:00Z",
    )
    base.update(over)
    return VideoRecord(**base)


def test_add_then_dedup_noop(store):
    rec = _record("vid00000001")
    assert store.add(rec) is True  # first write
    assert store.add(rec) is False  # dedup no-op — not written again
    assert store.count() == 1


def test_dedup_does_not_overwrite(store):
    store.add(_record("vid00000001", channel="Original"))
    # Same id, different content — must be ignored, original preserved.
    store.add(_record("vid00000001", channel="Changed"))
    assert store.get("vid00000001").channel == "Original"


def test_exists_and_get(store):
    assert store.exists("vid00000001") is False
    assert store.get("vid00000001") is None
    rec = _record("vid00000001")
    store.add(rec)
    assert store.exists("vid00000001") is True
    assert store.get("vid00000001") == rec


def test_iteration_ordered_by_date(store):
    store.add(_record("newer000001", date="2024-01-01T00:00:00Z"))
    store.add(_record("older000001", date="2020-01-01T00:00:00Z"))
    ids = [r.id for r in store.all()]
    assert ids == ["older000001", "newer000001"]


def test_null_timestamp_rejected_by_schema(store):
    # Bypass the model invariant to prove the DB itself enforces NOT NULL date.
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute(
            "INSERT INTO videos "
            "(id, channel, date, views, transcript, chapters, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("x" * 11, "Chan", None, 1, "[]", "[]", "2026-07-22T00:00:00Z"),
        )


def test_reopen_database_persists_rows(tmp_path):
    db = tmp_path / "kb.sqlite3"
    with VideoStore(db) as s:
        s.add(_record("persist0001"))
    # Reopen: the row survives and is still deduped.
    with VideoStore(db) as s2:
        assert s2.exists("persist0001")
        assert s2.add(_record("persist0001")) is False
        assert s2.count() == 1


def test_creates_parent_directory(tmp_path):
    nested = tmp_path / "a" / "b" / "kb.sqlite3"
    with VideoStore(nested) as s:
        s.add(_record("nested00001"))
    assert nested.exists()
