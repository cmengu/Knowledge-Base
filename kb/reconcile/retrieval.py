"""Stage 1 of the matcher: retrieve the candidate positions worth adjudicating.

The two-stage matcher never merges on embedding distance alone (spec). Stage 1's only job
is to *narrow*: from all of a topic's positions, return the few that are semantically
closest to an incoming unit, so the expensive Opus adjudicator (stage 2) judges a handful
rather than the whole KB. Distance decides *what the adjudicator looks at*, never what
merges.

Like the extraction LLM seam, the retriever is an **injected dependency** behind a narrow
protocol (:class:`CandidateRetriever`), so the reconciliation engine — and its tests — do
not depend on any embedding model or vector database. Production injects
:class:`LocalVectorRetriever`; tests inject a scripted fake.

:class:`LocalVectorRetriever` follows the locked architecture (research finding #2/#3):

* embeddings are computed **locally** with **BGE-M3** via ``sentence-transformers`` — no
  metered API, CPU-fine at this scale (Anthropic has no embedding model);
* vectors live in **LanceDB**, an embedded on-disk index, treated as a *derived, rebuildable
  cache*: the flat position JSON stays canonical, so the table is (re)built from the
  positions passed on each call and never drifts from the source of truth.

Both libraries are imported lazily inside the class so ``import kb.reconcile`` — as the
test suite does — needs neither installed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from kb.reconcile.schema import Position

__all__ = ["Candidate", "CandidateRetriever", "LocalVectorRetriever", "BGE_M3_MODEL"]

BGE_M3_MODEL = "BAAI/bge-m3"


class Candidate(BaseModel):
    """A retrieved position and its cosine similarity to the incoming unit.

    ``score`` is cosine similarity in roughly ``[0, 1]`` (higher = closer). It is provided
    for transparency and the retrieval floor only — the adjudicator judges meaning, not the
    number.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    position: Position = Field(description="A candidate position from the topic's KB.")
    score: float = Field(description="Cosine similarity of the unit's text to the position's statement.")


@runtime_checkable
class CandidateRetriever(Protocol):
    """Stage-1 retrieval: the ``top_k`` positions closest to a unit's text.

    Implementations receive the *current* positions on every call (so a vector cache can be
    kept in lock-step with the canonical KB) and must return at most ``k`` candidates whose
    ``score`` is ``>= min_score``, sorted by descending score. An empty topic (or no
    candidate clearing the floor) yields an empty list — the engine reads that as "nothing
    to compare against, so this unit is novel", never as a merge.
    """

    def top_k(
        self, *, query_text: str, positions: Sequence[Position], k: int, min_score: float
    ) -> list[Candidate]: ...


class LocalVectorRetriever:
    """Real :class:`CandidateRetriever` — local BGE-M3 embeddings over a LanceDB cache.

    The embedding model is loaded lazily on first use and reused for the rest of the run;
    position embeddings are cached in memory keyed by ``(position_id, statement)`` so an
    unchanged position is never re-embedded across the units of a batch. LanceDB holds the
    vectors as a rebuildable index, rebuilt from the positions handed to :meth:`top_k`
    whenever their id→statement mapping changes — the canonical JSON always wins.

    Never exercised by the test suite (that uses a fake); used by the prototype script and
    the production pipeline.
    """

    def __init__(
        self,
        *,
        model_name: str = BGE_M3_MODEL,
        db_path: str | None = None,
        table_name: str = "positions",
    ) -> None:
        self._model_name = model_name
        self._db_path = db_path
        self._table_name = table_name
        self._model = None                       # lazily loaded SentenceTransformer
        self._db = None                          # lazily opened LanceDB connection
        self._vector_cache: dict[str, tuple[str, list[float]]] = {}  # id -> (statement, vector)
        self._table_key: tuple[tuple[str, str], ...] | None = None   # signature of the built table

    # -- lazy resources -----------------------------------------------------

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - environment guard
                raise RuntimeError(
                    "LocalVectorRetriever needs sentence-transformers; "
                    "`pip install sentence-transformers`."
                ) from exc
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _get_db(self):
        if self._db is None:
            try:
                import lancedb
            except ImportError as exc:  # pragma: no cover - environment guard
                raise RuntimeError(
                    "LocalVectorRetriever needs lancedb; `pip install lancedb`."
                ) from exc
            import tempfile

            # Vectors are a rebuildable cache; a temp dir is a fine default. A caller who
            # wants the index to persist across runs passes db_path.
            path = self._db_path or tempfile.mkdtemp(prefix="kb-lancedb-")
            self._db = lancedb.connect(path)
        return self._db

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._get_model()
        # BGE-M3 with normalized embeddings makes cosine the natural metric.
        vectors = model.encode(list(texts), normalize_embeddings=True)
        return [list(map(float, v)) for v in vectors]

    # -- cache sync ---------------------------------------------------------

    def _ensure_position_vectors(self, positions: Sequence[Position]) -> None:
        """Embed any position whose ``(id, statement)`` is not already cached."""

        to_embed = [
            p for p in positions
            if self._vector_cache.get(p.position_id, (None,))[0] != p.statement
        ]
        if to_embed:
            vectors = self._embed([p.statement for p in to_embed])
            for position, vector in zip(to_embed, vectors):
                self._vector_cache[position.position_id] = (position.statement, vector)

    def _rebuild_table(self, positions: Sequence[Position]):
        """(Re)build the LanceDB table iff the current positions differ from what's built."""

        db = self._get_db()
        key = tuple((p.position_id, p.statement) for p in positions)
        rows = [
            {
                "position_id": p.position_id,
                "vector": self._vector_cache[p.position_id][1],
            }
            for p in positions
        ]
        if key == self._table_key and self._table_name in db.table_names():
            return db.open_table(self._table_name)
        if self._table_name in db.table_names():
            db.drop_table(self._table_name)
        table = db.create_table(self._table_name, data=rows)
        self._table_key = key
        return table

    # -- retrieval ----------------------------------------------------------

    def top_k(
        self, *, query_text: str, positions: Sequence[Position], k: int, min_score: float
    ) -> list[Candidate]:
        if not positions or k <= 0:
            return []

        self._ensure_position_vectors(positions)
        by_id = {p.position_id: p for p in positions}
        table = self._rebuild_table(positions)

        query_vector = self._embed([query_text])[0]
        hits = (
            table.search(query_vector)
            .metric("cosine")
            .limit(min(k, len(positions)))
            .to_list()
        )

        candidates: list[Candidate] = []
        for hit in hits:
            # LanceDB cosine "_distance" is 1 - cosine_similarity; convert back.
            score = 1.0 - float(hit["_distance"])
            if score < min_score:
                continue
            position = by_id.get(hit["position_id"])
            if position is not None:
                candidates.append(Candidate(position=position, score=score))
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates
