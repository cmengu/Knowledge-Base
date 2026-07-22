"""URL/id parsing and seed-file reading — pure, no I/O beyond tmp files."""

from __future__ import annotations

import pytest

from kb.ingest.urls import canonical_watch_url, parse_video_id, read_seed_file

VID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "raw",
    [
        f"https://www.youtube.com/watch?v={VID}",
        f"http://youtube.com/watch?v={VID}",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://music.youtube.com/watch?v={VID}",
        f"https://www.youtube.com/watch?v={VID}&list=PLxyz&index=2&t=42s",
        f"https://www.youtube.com/watch?app=desktop&v={VID}",
        f"https://youtu.be/{VID}",
        f"https://youtu.be/{VID}?t=30",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/embed/{VID}",
        f"https://www.youtube.com/embed/{VID}?rel=0",
        f"https://www.youtube.com/live/{VID}",
        f"https://www.youtube.com/v/{VID}",
        f"youtu.be/{VID}",
        f"www.youtube.com/watch?v={VID}",
        f"  https://youtu.be/{VID}  ",  # surrounding whitespace
        VID,  # bare id
    ],
)
def test_parse_video_id_extracts_id(raw):
    assert parse_video_id(raw) == VID


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "not a url",
        "https://example.com/watch?v=whatever",
        "https://vimeo.com/123456789",
        "https://www.youtube.com/watch?v=short",  # too short
        "https://www.youtube.com/@SomeChannel",  # channel page, no video
        "https://www.youtube.com/results?search_query=evals",
        None,
    ],
)
def test_parse_video_id_returns_none_for_non_videos(raw):
    assert parse_video_id(raw) is None


def test_bare_id_with_reserved_chars_is_still_id():
    # 11 chars including - and _ is a valid id.
    assert parse_video_id("a_b-c1D2e3F") == "a_b-c1D2e3F"


def test_canonical_watch_url():
    assert canonical_watch_url(VID) == f"https://www.youtube.com/watch?v={VID}"


def test_read_seed_file_skips_comments_and_blanks(tmp_path):
    seed = tmp_path / "evals.txt"
    seed.write_text(
        "# a comment\n"
        f"https://youtu.be/{VID}\n"
        "\n"
        "   \n"
        "  # indented comment\n"
        f"  {VID}  \n",
        encoding="utf-8",
    )
    entries = read_seed_file(seed)
    assert entries == [f"https://youtu.be/{VID}", VID]


def test_read_seed_file_preserves_order_and_duplicates(tmp_path):
    seed = tmp_path / "evals.txt"
    seed.write_text(f"{VID}\nsecond0id123\n{VID}\n", encoding="utf-8")
    assert read_seed_file(seed) == [VID, "second0id123", VID]


def test_read_seed_file_strips_inline_comments(tmp_path):
    seed = tmp_path / "evals.txt"
    seed.write_text(
        f"https://www.youtube.com/watch?v={VID}   # Karpathy talk\n"
        f"{VID}\t# tab-separated note\n",
        encoding="utf-8",
    )
    entries = read_seed_file(seed)
    assert entries == [f"https://www.youtube.com/watch?v={VID}", VID]
    # And each parses back to the id.
    assert [parse_video_id(e) for e in entries] == [VID, VID]


def test_read_seed_file_keeps_fragment_hash(tmp_path):
    # A '#' with no preceding whitespace (URL fragment) is NOT a comment.
    seed = tmp_path / "evals.txt"
    seed.write_text(f"https://youtu.be/{VID}#t=1m\n", encoding="utf-8")
    assert read_seed_file(seed) == [f"https://youtu.be/{VID}#t=1m"]


def test_example_seed_file_parses(tmp_path):
    # The committed example seed file must yield exactly its two video ids.
    from pathlib import Path

    example = Path(__file__).resolve().parent.parent / "seed" / "evals.example.txt"
    entries = read_seed_file(example)
    ids = [parse_video_id(e) for e in entries]
    assert ids == ["zjkBMFhNj_g", "hM_h0UA7upI"]
