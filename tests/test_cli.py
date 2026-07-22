"""CLI entrypoint wiring, exercised offline (real fetchers monkeypatched)."""

from __future__ import annotations

from kb.ingest import __main__ as cli
from kb.ingest.fetchers import metadata_from_info
from tests.conftest import (
    KARPATHY_LLM,
    KNOWN_IDS,
    NO_PRIORS,
    FakeMetadataFetcher,
    FakeTranscriptFetcher,
    load_rawinfo,
    load_transcript,
)


def _install_fakes(monkeypatch):
    meta = {vid: metadata_from_info(load_rawinfo(vid)) for vid in KNOWN_IDS}
    tr = {vid: load_transcript(vid) for vid in KNOWN_IDS}
    monkeypatch.setattr(
        cli, "YtDlpMetadataFetcher", lambda *a, **k: FakeMetadataFetcher(meta)
    )
    monkeypatch.setattr(
        cli, "TranscriptApiFetcher", lambda *a, **k: FakeTranscriptFetcher(tr)
    )


def test_cli_ingests_then_dedups(tmp_path, monkeypatch, capsys):
    _install_fakes(monkeypatch)
    seed = tmp_path / "evals.txt"
    seed.write_text(
        f"# seed\nhttps://youtu.be/{KARPATHY_LLM}\n"
        f"https://www.youtube.com/watch?v={NO_PRIORS}\n",
        encoding="utf-8",
    )
    db = tmp_path / "kb.sqlite3"

    rc = cli.main([str(seed), "--db", str(db)])
    assert rc == 0
    assert "2 ingested" in capsys.readouterr().out

    # Re-run over the same DB → dedup no-op.
    rc2 = cli.main([str(seed), "--db", str(db)])
    assert rc2 == 0
    assert "2 skipped" in capsys.readouterr().out


def test_cli_missing_seed_file_returns_2(tmp_path):
    assert cli.main([str(tmp_path / "nope.txt")]) == 2


def test_cli_strict_exits_nonzero_on_failure(tmp_path, monkeypatch):
    _install_fakes(monkeypatch)
    seed = tmp_path / "evals.txt"
    seed.write_text("this is not a url\n", encoding="utf-8")
    db = tmp_path / "kb.sqlite3"
    assert cli.main([str(seed), "--db", str(db), "--strict"]) == 1


def test_cli_quiet_prints_only_summary(tmp_path, monkeypatch, capsys):
    _install_fakes(monkeypatch)
    seed = tmp_path / "evals.txt"
    seed.write_text(f"https://youtu.be/{KARPATHY_LLM}\n", encoding="utf-8")
    db = tmp_path / "kb.sqlite3"
    cli.main([str(seed), "--db", str(db), "--quiet"])
    out = capsys.readouterr().out
    assert "1 ingested" in out
    assert "[+]" not in out  # per-entry lines suppressed
