"""Config loading — proxy OFF by default, fail-fast on misconfiguration."""

from __future__ import annotations

from pathlib import Path

import pytest

from kb.config import (
    ConfigError,
    IngestConfig,
    ProxyConfig,
    config_from_mapping,
    load_config,
)


def test_defaults_have_proxy_off():
    cfg = IngestConfig()
    assert cfg.proxy.enabled is False
    assert cfg.languages == ("en",)
    assert cfg.database.endswith(".sqlite3")
    assert cfg.metadata_proxy_url == ""


def test_missing_default_file_yields_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no config/ingest.yaml here
    cfg = load_config(None)
    assert cfg == IngestConfig()


def test_missing_explicit_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "does-not-exist.yaml")


def test_load_from_yaml_file(tmp_path):
    p = tmp_path / "ingest.yaml"
    p.write_text(
        "database: data/kb.sqlite3\n"
        "languages: [en, de]\n"
        "proxy:\n"
        "  enabled: true\n"
        "  webshare_proxy_username: user\n"
        "  webshare_proxy_password: pass\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.languages == ("en", "de")
    assert cfg.proxy.enabled is True
    assert cfg.proxy.webshare_proxy_username == "user"


def test_proxy_enabled_without_credentials_raises():
    with pytest.raises(ConfigError, match="webshare"):
        ProxyConfig(enabled=True)


def test_proxy_enabled_missing_one_credential_raises():
    with pytest.raises(ConfigError):
        config_from_mapping(
            {"proxy": {"enabled": True, "webshare_proxy_username": "only-user"}}
        )


def test_single_language_string_is_accepted():
    cfg = config_from_mapping({"languages": "fr"})
    assert cfg.languages == ("fr",)


def test_empty_languages_list_raises():
    with pytest.raises(ConfigError):
        config_from_mapping({"languages": []})


def test_empty_mapping_is_defaults():
    assert config_from_mapping({}) == IngestConfig()


def test_repo_config_file_parses_and_proxy_off():
    # The committed config/ingest.yaml must load and keep the proxy off.
    repo_config = Path(__file__).resolve().parent.parent / "config" / "ingest.yaml"
    cfg = load_config(repo_config)
    assert cfg.proxy.enabled is False
    assert cfg.languages == ("en",)
