"""Per-topic ``KBStore`` tests: load/save persistence and position CRUD (ticket #06).

Every test points the store at pytest's ``tmp_path`` so nothing is written into the repo.
No LLM, no network — the store is pure file I/O over the position model.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from kb.reconcile import KBStore, Maturity, Position, PositionSource

T0 = dt.datetime(2025, 5, 11, 9, 0)
T1 = dt.datetime(2025, 6, 1, 9, 0)


def make_source(**overrides) -> PositionSource:
    base = dict(
        unit_id="vidA#1",
        video_id="vidA",
        date="2025-05-11",
        alignment="supporting",
        stance="affirms",
        quote="build your own evals",
        statement="Build your own evals.",
    )
    base.update(overrides)
    return PositionSource(**base)


def make_position(position_id="evals-0001", topic="evals", **overrides) -> Position:
    base = dict(
        position_id=position_id,
        topic=topic,
        statement="You should build your own task-specific evals.",
        at=T0,
        first_source=make_source(),
    )
    base.update(overrides)
    return Position.create(**base)


# --- load / save -----------------------------------------------------------


def test_load_absent_topic_is_empty(tmp_path):
    store = KBStore.load("evals", root=tmp_path)
    assert len(store) == 0
    assert store.positions() == []


def test_save_writes_json_and_md_under_topic_dir(tmp_path):
    store = KBStore("evals", root=tmp_path)
    store.add(make_position())
    store.save()
    assert store.json_path == tmp_path / "evals" / "positions.json"
    assert store.md_path == tmp_path / "evals" / "positions.md"
    assert store.json_path.exists() and store.md_path.exists()


def test_saved_json_has_topic_and_positions_shape(tmp_path):
    store = KBStore("evals", root=tmp_path)
    store.add(make_position())
    store.save()
    data = json.loads(store.json_path.read_text(encoding="utf-8"))
    assert data["topic"] == "evals"
    assert isinstance(data["positions"], list) and len(data["positions"]) == 1
    assert data["positions"][0]["position_id"] == "evals-0001"


def test_roundtrip_through_disk_preserves_positions(tmp_path):
    store = KBStore("evals", root=tmp_path)
    pos = make_position()
    pos.record_transition(Maturity.emerging_trend, at=T1, reason="second source")
    pos.add_source(make_source(unit_id="vidB#2", video_id="vidB", date="2025-06-01"), at=T1)
    store.add(pos)
    store.save()

    reloaded = KBStore.load("evals", root=tmp_path)
    assert len(reloaded) == 1
    assert reloaded.get("evals-0001") == pos          # full-fidelity round-trip


def test_save_is_byte_deterministic(tmp_path):
    store = KBStore("evals", root=tmp_path)
    store.add(make_position("evals-0002"))
    store.add(make_position("evals-0001"))
    store.save()
    first = store.json_path.read_bytes()
    store.save()
    assert store.json_path.read_bytes() == first      # re-saving unchanged data is stable


def test_positions_serialized_sorted_by_id(tmp_path):
    store = KBStore("evals", root=tmp_path)
    store.add(make_position("evals-0003"))
    store.add(make_position("evals-0001"))
    store.add(make_position("evals-0002"))
    store.save()
    data = json.loads(store.json_path.read_text(encoding="utf-8"))
    assert [p["position_id"] for p in data["positions"]] == ["evals-0001", "evals-0002", "evals-0003"]


def test_save_leaves_no_temp_files(tmp_path):
    store = KBStore("evals", root=tmp_path)
    store.add(make_position())
    store.save()
    leftovers = list((tmp_path / "evals").glob("*.tmp*"))
    assert leftovers == []                             # atomic write cleans up after itself


def test_empty_store_saves_valid_files(tmp_path):
    store = KBStore("evals", root=tmp_path)
    store.save()
    data = json.loads(store.json_path.read_text(encoding="utf-8"))
    assert data == {"topic": "evals", "positions": []}
    assert "No positions yet" in store.md_path.read_text(encoding="utf-8")


def test_load_rejects_wrong_topic_file(tmp_path):
    store = KBStore("evals", root=tmp_path)
    store.add(make_position())
    store.save()
    # Ask for a different topic but point at the evals file -> mismatch is caught.
    other_dir = tmp_path / "small-models"
    other_dir.mkdir()
    (other_dir / "positions.json").write_text(store.json_path.read_text(encoding="utf-8"))
    with pytest.raises(ValueError):
        KBStore.load("small-models", root=tmp_path)


# --- CRUD ------------------------------------------------------------------


def test_add_then_get_and_contains(tmp_path):
    store = KBStore("evals", root=tmp_path)
    pos = store.add(make_position())
    assert store.get("evals-0001") is pos
    assert "evals-0001" in store
    assert store.get("nope") is None


def test_add_duplicate_id_raises(tmp_path):
    store = KBStore("evals", root=tmp_path)
    store.add(make_position())
    with pytest.raises(KeyError):
        store.add(make_position())                     # same id


def test_upsert_inserts_then_replaces(tmp_path):
    store = KBStore("evals", root=tmp_path)
    store.upsert(make_position())
    replacement = make_position(statement="A revised canonical statement.")
    store.upsert(replacement)
    assert len(store) == 1
    assert store.get("evals-0001").statement == "A revised canonical statement."


def test_remove_returns_presence(tmp_path):
    store = KBStore("evals", root=tmp_path)
    store.add(make_position())
    assert store.remove("evals-0001") is True
    assert store.remove("evals-0001") is False         # already gone
    assert len(store) == 0


def test_positions_and_iter_are_sorted(tmp_path):
    store = KBStore("evals", root=tmp_path)
    store.add(make_position("evals-0002"))
    store.add(make_position("evals-0001"))
    assert [p.position_id for p in store.positions()] == ["evals-0001", "evals-0002"]
    assert [p.position_id for p in store] == ["evals-0001", "evals-0002"]


def test_next_id_counts_from_one_and_past_the_highest(tmp_path):
    store = KBStore("evals", root=tmp_path)
    assert store.next_id() == "evals-0001"
    store.add(make_position("evals-0001"))
    assert store.next_id() == "evals-0002"
    store.add(make_position("evals-0005"))             # a gap
    assert store.next_id() == "evals-0006"             # one past the max, not the count


def test_create_position_mints_id_adds_and_returns(tmp_path):
    store = KBStore("evals", root=tmp_path)
    first = store.create_position(statement="First position.", at=T0, first_source=make_source())
    second = store.create_position(statement="Second position.", at=T0)
    assert first.position_id == "evals-0001"
    assert second.position_id == "evals-0002"
    assert second.sources == []
    assert store.get("evals-0002") is second


def test_wrong_topic_position_rejected(tmp_path):
    store = KBStore("evals", root=tmp_path)
    with pytest.raises(ValueError):
        store.add(make_position(topic="small-models"))


def test_load_dedups_would_reject_duplicate_ids(tmp_path):
    # Hand-craft a corrupt file with two positions sharing an id -> load refuses it.
    store = KBStore("evals", root=tmp_path)
    store.add(make_position())
    store.save()
    data = json.loads(store.json_path.read_text(encoding="utf-8"))
    data["positions"].append(dict(data["positions"][0]))   # duplicate id
    store.json_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        KBStore.load("evals", root=tmp_path)
