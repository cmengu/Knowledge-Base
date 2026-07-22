"""Configuration for the pipeline.

Config lives in ``config/`` as YAML. Only the ingest layer is defined here;
later layers extend this module with their own sections. Loading tolerates a
missing file (built-in defaults) but fails fast on a malformed one or on an
enabled-but-unconfigured proxy, so misconfiguration surfaces at startup rather
than mid-batch.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config/ingest.yaml")


class ConfigError(ValueError):
    """Raised when a config file is present but invalid."""


@dataclass(frozen=True)
class ProxyConfig:
    """Webshare rotating-residential-proxy escape hatch for transcripts.

    OFF by default; ingest is meant to run on the local residential IP. When
    ``enabled`` is true both Webshare credentials must be present.
    """

    enabled: bool = False
    webshare_proxy_username: str = ""
    webshare_proxy_password: str = ""

    def __post_init__(self) -> None:
        if self.enabled and not (
            self.webshare_proxy_username and self.webshare_proxy_password
        ):
            raise ConfigError(
                "proxy.enabled is true but webshare_proxy_username / "
                "webshare_proxy_password are not both set"
            )


@dataclass(frozen=True)
class IngestConfig:
    """Everything Layer 1 needs to run."""

    database: str = "data/knowledge_base.sqlite3"
    languages: tuple[str, ...] = ("en",)
    metadata_proxy_url: str = ""
    proxy: ProxyConfig = field(default_factory=ProxyConfig)


def _coerce_proxy(raw: Any) -> ProxyConfig:
    if raw is None:
        return ProxyConfig()
    if not isinstance(raw, dict):
        raise ConfigError("'proxy' must be a mapping")
    defaults = ProxyConfig()
    return ProxyConfig(
        enabled=bool(raw.get("enabled", defaults.enabled)),
        webshare_proxy_username=str(
            raw.get("webshare_proxy_username", defaults.webshare_proxy_username)
        ),
        webshare_proxy_password=str(
            raw.get("webshare_proxy_password", defaults.webshare_proxy_password)
        ),
    )


def _coerce_languages(raw: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None:
        return default
    if isinstance(raw, str):
        langs = [raw]
    elif isinstance(raw, (list, tuple)):
        langs = [str(x) for x in raw]
    else:
        raise ConfigError("'languages' must be a string or list of strings")
    langs = [x.strip() for x in langs if str(x).strip()]
    if not langs:
        raise ConfigError("'languages' must not be empty")
    return tuple(langs)


def config_from_mapping(raw: dict[str, Any]) -> IngestConfig:
    """Build an :class:`IngestConfig` from a parsed mapping, over the defaults."""
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a mapping")
    defaults = IngestConfig()
    return replace(
        defaults,
        database=str(raw.get("database", defaults.database)),
        languages=_coerce_languages(raw.get("languages"), defaults.languages),
        metadata_proxy_url=str(
            raw.get("metadata_proxy_url", defaults.metadata_proxy_url)
        ),
        proxy=_coerce_proxy(raw.get("proxy")),
    )


def load_config(path: str | Path | None = None) -> IngestConfig:
    """Load ingest config from ``path`` (defaults to ``config/ingest.yaml``).

    A missing file yields built-in defaults; a present-but-malformed file
    raises :class:`ConfigError`.
    """
    if path is None:
        resolved = DEFAULT_CONFIG_PATH
        required = False
    else:
        resolved = Path(path)
        required = True

    if not resolved.exists():
        if required:
            raise ConfigError(f"config file not found: {resolved}")
        return IngestConfig()

    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - passthrough of parser text
        raise ConfigError(f"could not parse {resolved}: {exc}") from exc

    if raw is None:  # empty file
        return IngestConfig()
    return config_from_mapping(raw)
