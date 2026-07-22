"""Pure helpers for turning curator input into YouTube video ids.

The video id is the dedup key for the whole pipeline, so parsing is centralized
and thoroughly tested here — no network, no I/O beyond reading the seed file.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# A YouTube video id is exactly 11 URL-safe base64 characters.
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Host path prefixes that carry the id as the first path segment,
# e.g. youtu.be/<id>, youtube.com/shorts/<id>, /embed/<id>, /live/<id>, /v/<id>.
_PATH_PREFIXES = ("shorts", "embed", "live", "v", "e")

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


def _valid(candidate: str | None) -> str | None:
    if candidate and _VIDEO_ID_RE.match(candidate):
        return candidate
    return None


def parse_video_id(raw: str) -> str | None:
    """Extract an 11-char YouTube video id from a URL or bare id.

    Accepts the common URL forms (``watch?v=``, ``youtu.be/``, ``/shorts/``,
    ``/embed/``, ``/live/``, ``/v/``), a bare id, and tolerates extra query
    params. Deliberately conservative: a recognized YouTube host with no
    id-bearing pattern (a channel handle, a search page, …) returns ``None``
    rather than guessing from arbitrary path text — a false-positive id would
    silently corrupt the dedup key.
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None

    # Bare 11-char id.
    direct = _valid(text)
    if direct:
        return direct

    # Add a scheme so urlparse populates netloc for scheme-less inputs like
    # "youtu.be/<id>" or "www.youtube.com/watch?v=<id>".
    to_parse = text if "//" in text else f"https://{text}"
    parsed = urlparse(to_parse)
    host = (parsed.netloc or "").lower().split(":", 1)[0]  # drop any ":port"

    if host not in _YOUTUBE_HOSTS:
        return None

    # youtu.be/<id>[?...]
    if host in ("youtu.be", "www.youtu.be"):
        first_segment = parsed.path.lstrip("/").split("/", 1)[0]
        return _valid(first_segment)

    # /watch?v=<id> (or any ?v=<id>)
    v_values = parse_qs(parsed.query).get("v", [])
    if v_values:
        candidate = _valid(v_values[0])
        if candidate:
            return candidate

    # /<prefix>/<id> — shorts, embed, live, v, e
    segments = [s for s in parsed.path.split("/") if s]
    if len(segments) >= 2 and segments[0] in _PATH_PREFIXES:
        return _valid(segments[1])

    return None


def canonical_watch_url(video_id: str) -> str:
    """The canonical watch URL for a video id."""
    return f"https://www.youtube.com/watch?v={video_id}"


_INLINE_COMMENT_RE = re.compile(r"\s+#.*$")


def read_seed_file(path: str | Path) -> list[str]:
    """Read a seed file into a list of raw entries.

    One URL/id per line. Blank lines and ``#`` full-line comments are skipped.
    A whitespace-preceded inline comment (pip-requirements style, e.g.
    ``https://youtu.be/<id>  # a note``) is stripped; a ``#`` with no preceding
    whitespace (such as a URL fragment) is kept. Order and duplicates are
    preserved — the ingest loop dedups by video id.
    """
    entries: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        stripped = _INLINE_COMMENT_RE.sub("", stripped).strip()
        if stripped:
            entries.append(stripped)
    return entries
