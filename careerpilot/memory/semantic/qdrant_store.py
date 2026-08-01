"""
Purpose
    Wraps Qdrant: embed text, upsert points, and run similarity search —
    dense-only (pure semantic) or hybrid (dense + sparse/BM25-style,
    fused with Reciprocal Rank Fusion). This is the biggest architectural
    difference from waku-agent — waku's default semantic store is SQLite
    FTS5 keyword search; CareerPilot uses Qdrant + real embeddings from
    day one, with hybrid search as an optional upgrade on top of that.

Responsibilities
    - EmbeddingProvider / SparseEmbeddingProvider: interfaces any
      embedding backend must implement (Strategy pattern) — SemanticStore
      never knows or cares which concrete backend is behind them
    - OpenAIEmbeddingProvider, FastEmbedProvider, FastEmbedSparseProvider:
      the concrete backends actually available today
    - build_embedding_provider() / build_sparse_provider(): factories that
      pick a concrete class from a plain string, so switching backends is
      a one-line config change, never a code change
    - SemanticStore: the class that actually talks to Qdrant, given
      whichever providers it was built with

Inputs:  free text (notes, facts, queries)
Outputs: vectors in, ranked SearchResult objects out

Dependencies:   qdrant-client, openai (optional), fastembed (optional)
Related files:  tools/notes.py, memory/retrieval_gate.py, memory/consolidation.py, config/settings.py
Design patterns:
    - Strategy: EmbeddingProvider/SparseEmbeddingProvider are swappable
      implementations behind one interface
    - Factory: build_embedding_provider()/build_sparse_provider() decide
      which concrete class to instantiate from a config string
    - Repository: SemanticStore hides every Qdrant-specific detail
      (collections, named vectors, fusion queries) behind plain methods
Difficulty:     advanced

Agentic AI concepts used: embeddings, vector databases, hybrid search
  (dense semantic + sparse lexical, fused via RRF), retrieval, RAG
Software engineering concepts used: Strategy pattern, Factory pattern,
  Repository pattern, dependency injection (SemanticStore is handed its
  providers, it never constructs them itself — this is exactly what
  makes it testable without a real API key or network access)

A note on providers, since it matters more than it looks
    Anthropic does not offer an embeddings API at all — there is no
    endpoint to call, so there is no AnthropicEmbeddingProvider below.
    That's not an oversight; adding one would mean faking behavior that
    doesn't exist. If Anthropic ever ships embeddings, adding support is
    exactly one new class + one line in build_embedding_provider() — nothing
    else in this file, or in SemanticStore, would need to change. That
    "add one class, touch nothing else" property is the entire point of
    the Strategy pattern used here.

Future implementation notes
    Decide your embedding model once and be consistent — mixing
    embedding models/dimensions in one collection silently breaks
    similarity search. Hybrid search is opt-in: only set
    CAREERPILOT_SPARSE_EMBEDDING_MODEL if you want it; leaving it unset
    gives you clean dense-only search with zero extra dependencies.

Common beginner mistakes
    - Creating a new Qdrant client on every call instead of reusing one
    - Forgetting payload metadata (company/text), which makes filtered
      recall and manage_memory's delete/correct actions impossible
    - Not calling ensure_collection() before the first upsert
    - Assuming your chat model's API key also works for embeddings — it
      doesn't if you're on Groq/Anthropic for chat, since neither offers
      an embeddings endpoint at all
    - Switching embedding models on a collection that already has data —
      old vectors and new vectors would have different meanings/sizes,
      silently corrupting search quality
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

# import openai

from qdrant_client import QdrantClient, models as qmodels

from careerpilot.config.settings import settings

# Every embedding model produces vectors of a FIXED size — this table
# exists so ensure_collection() never has to guess. Add a line here if
# you add a new OpenAI embedding model.
OPENAI_EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

# _client: QdrantClient | None = None
# _embedding_client: openai.OpenAI | None = None
# ---------------------------------------------------------------------
# Strategy pattern: SemanticStore only ever talks to these interfaces —
# never to OpenAI or fastembed directly. That's what makes "just choose
# a provider name" possible without touching SemanticStore's code.
# ---------------------------------------------------------------------


class EmbeddingProvider(ABC):
    """Anything that can turn text into a dense vector of a fixed size."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """The fixed vector size this provider always produces."""

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...


class SparseEmbeddingProvider(ABC):
    """Anything that can turn text into a sparse (BM25-style) vector.
    Optional — only needed if you want hybrid search.
    """

    @abstractmethod
    def embed(self, text: str) -> qmodels.SparseVector: ...


# ---------------------------------------------------------------------
# Concrete providers
# ---------------------------------------------------------------------


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Calls OpenAI's embeddings API. Requires a real OpenAI key even if
    your chat provider is Groq/Anthropic — embeddings and chat are
    completely separate endpoints, possibly different providers.
    """

    def __init__(self, model: str, api_key: str):
        import openai  # lazy import: don't require openai installed if you use fastembed instead

        if model not in OPENAI_EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Unknown OpenAI embedding model {model!r} — add its size to "
                f"OPENAI_EMBEDDING_DIMENSIONS above before using it."
            )
        self._model = model
        self._dims = OPENAI_EMBEDDING_DIMENSIONS[model]
        self._client = openai.OpenAI(api_key=api_key)

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(model=self._model, input=text)
        return response.data[0].embedding


class FastEmbedProvider(EmbeddingProvider):
    """Local, free, no API key, no network call per embedding — runs a
    small ONNX model on your own machine via the `fastembed` library
    (maintained by the Qdrant team, so it's a natural pairing). Trades
    a one-time model download and slightly slower embedding for zero
    ongoing cost.
    """

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5"):
        from fastembed import (
            TextEmbedding,
        )  # lazy import: don't require fastembed if you use OpenAI instead

        self._model = TextEmbedding(model_name=model)
        # fastembed doesn't expose dimensions as a plain attribute, so we
        # determine it once, here, by embedding a throwaway string — this
        # only happens once per process, not per call.
        probe = next(iter(self._model.embed(["dimension probe"])))
        self._dims = len(probe)

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed(self, text: str) -> list[float]:
        # .embed() takes a batch (even for one string) and returns numpy
        # arrays — next(iter(...)) pulls out the single result, .tolist()
        # converts it to a plain Python list for Qdrant.
        vector = next(iter(self._model.embed([text])))
        return vector.tolist()


class FastEmbedSparseProvider(SparseEmbeddingProvider):
    """Local BM25-style sparse embeddings, also via fastembed. Pairs
    with any dense provider above to enable hybrid search — set
    CAREERPILOT_SPARSE_EMBEDDING_MODEL to enable this.
    """

    def __init__(self, model: str = "Qdrant/bm25"):
        from fastembed import SparseTextEmbedding

        self._model = SparseTextEmbedding(model_name=model)

    def embed(self, text: str) -> qmodels.SparseVector:
        sparse = next(iter(self._model.embed([text])))
        return qmodels.SparseVector(
            indices=sparse.indices.tolist(),
            values=sparse.values.tolist(),
        )


# ---------------------------------------------------------------------
# Factories: the ONLY place that reads a config string and decides which
# concrete class to build. Everything downstream just uses the
# EmbeddingProvider/SparseEmbeddingProvider interface.
# ---------------------------------------------------------------------


def build_embedding_provider(
    provider: str, model: str, api_key: str | None = None
) -> EmbeddingProvider:
    """provider is a plain string: "openai" or "fastembed". Adding a new
    backend later means adding one branch here and one new class above —
    nothing else in this file changes.
    """
    if provider == "openai":
        if not api_key:
            raise ValueError(
                "OpenAI embeddings require an API key (settings.embedding_api_key or settings.api_key)."
            )
        return OpenAIEmbeddingProvider(model=model, api_key=api_key)
    if provider == "fastembed":
        return FastEmbedProvider(model=model)
    raise ValueError(
        f"Unknown embedding provider {provider!r}. Choices: 'openai', 'fastembed'."
    )


def build_sparse_provider(model: str | None) -> SparseEmbeddingProvider | None:
    """Returns None (hybrid disabled) if no sparse model is configured —
    hybrid search is opt-in, not a default you have to actively turn off.
    """
    if not model:
        return None
    return FastEmbedSparseProvider(model=model)


# ---------------------------------------------------------------------
# The Repository: hides every Qdrant-specific detail (named vectors,
# fusion queries, collection setup) behind three plain methods.
# ---------------------------------------------------------------------


@dataclass
class SearchResult:
    id: str
    company: str
    text: str
    score: float


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        if settings.qdrant_url == ":memory:":
            _client = QdrantClient(location=":memory:")  # in-memory testing mode
        else:
            _client = QdrantClient(
                url=settings.qdrant_url, api_key=settings.qdrant_api_key
            )
    return _client


def delete_note(point_id: str) -> None:
    """Deletes one point by id — needed by manage_memory's 'forget' and
    'correct' actions.
    """
    get_client().delete(
        collection_name=settings.qdrant_collection, points_selector=[point_id]
    )


class SemanticStore:
    DENSE_VECTOR_NAME = "dense"
    SPARSE_VECTOR_NAME = "sparse"

    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        dense_provider: EmbeddingProvider,
        sparse_provider: SparseEmbeddingProvider | None = None,
    ):
        """Providers are passed in, never constructed here — that's what
        lets tests hand this a fake provider instead of a real OpenAI/
        fastembed one, with no network access required.
        """
        self._client = client
        self._collection = collection_name
        self._dense = dense_provider
        self._sparse = sparse_provider  # None => dense-only search

    @property
    def hybrid_enabled(self) -> bool:
        return self._sparse is not None

    def ensure_collection(self) -> None:
        """Creates the collection if missing. Safe to call every time —
        collection_exists() checks first, so calling this 100 times has
        the same effect as calling it once ("idempotent").
        """
        if self._client.collection_exists(self._collection):
            return

        vectors_config = {
            self.DENSE_VECTOR_NAME: qmodels.VectorParams(
                size=self._dense.dimensions,
                # COSINE measures the ANGLE between two vectors (direction),
                # not their raw length — the standard choice for text
                # embeddings, since embedding models encode meaning in
                # direction, not magnitude.
                distance=qmodels.Distance.COSINE,
            )
        }
        sparse_vectors_config = None
        if self.hybrid_enabled:
            sparse_vectors_config = {
                self.SPARSE_VECTOR_NAME: qmodels.SparseVectorParams()
            }

        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_vectors_config,
        )

    def upsert_note(self, company: str, text: str) -> str:
        """Embeds `text` (and, if hybrid is enabled, also sparse-embeds
        it) and stores it as one point, tagged with company/text as
        payload — without that payload, a match would tell you THAT
        something matched but not WHAT or WHICH company it's about.

        Returns the point's id, which manage_memory (tools/memory_admin.py)
        needs later to delete or correct this specific note.
        """
        self.ensure_collection()
        point_id = str(uuid.uuid4())

        vector: dict = {self.DENSE_VECTOR_NAME: self._dense.embed(text)}
        if self.hybrid_enabled:
            vector[self.SPARSE_VECTOR_NAME] = self._sparse.embed(text)

        self._client.upsert(
            collection_name=self._collection,
            points=[
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={"company": company, "text": text},
                )
            ],
        )
        return point_id

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Dense-only search if no sparse provider was configured;
        otherwise hybrid search — both the dense and sparse sides are
        queried independently (over-fetching a wider candidate list
        each), then fused with Reciprocal Rank Fusion (RRF), which
        combines two differently-scaled rankings by their RANK
        position rather than trying to average two scores that aren't
        even on the same scale.
        """
        self.ensure_collection()

        if self.hybrid_enabled:
            response = self._client.query_points(
                collection_name=self._collection,
                prefetch=[
                    qmodels.Prefetch(
                        query=self._dense.embed(query),
                        using=self.DENSE_VECTOR_NAME,
                        limit=max(top_k * 4, 20),
                    ),
                    qmodels.Prefetch(
                        query=self._sparse.embed(query),
                        using=self.SPARSE_VECTOR_NAME,
                        limit=max(top_k * 4, 20),
                    ),
                ],
                query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
                limit=top_k,
            )
        else:
            response = self._client.query_points(
                collection_name=self._collection,
                query=self._dense.embed(query),
                using=self.DENSE_VECTOR_NAME,
                limit=top_k,
            )

        return [
            SearchResult(
                id=str(p.id),
                company=p.payload["company"],
                text=p.payload["text"],
                score=p.score,
            )
            for p in response.points
        ]


# ---------------------------------------------------------------------
# Module-level convenience: build one SemanticStore from settings, reused
# across the app (not one per call) — this is what tools/notes.py and
# memory/consolidation.py actually import and use.
# ---------------------------------------------------------------------

_client: QdrantClient | None = None
_store: SemanticStore | None = None


def get_store() -> SemanticStore:
    """Lazily builds one SemanticStore, wired up entirely from settings,
    and reuses it — a fresh Qdrant connection or a re-downloaded fastembed
    model on every call would be wasteful and slow.
    """
    global _client, _store
    if _store is None:
        if _client is None:
            _client = QdrantClient(
                url=settings.qdrant_url, api_key=settings.qdrant_api_key
            )

        dense_provider = build_embedding_provider(
            provider=settings.embedding_provider,
            model=settings.embedding_model,
            api_key=settings.embedding_api_key or settings.api_key,
        )
        sparse_provider = build_sparse_provider(settings.sparse_embedding_model)

        _store = SemanticStore(
            client=_client,
            collection_name=settings.qdrant_collection,
            dense_provider=dense_provider,
            sparse_provider=sparse_provider,
        )
    return _store


# Thin wrappers so tools/notes.py can keep calling simple functions
# without needing to know SemanticStore exists.


def upsert_note(company: str, text: str) -> str:
    return get_store().upsert_note(company, text)


def search_semantic(query: str, top_k: int = 5) -> list[dict]:
    results = get_store().search(query, top_k=top_k)
    return [
        {"id": r.id, "company": r.company, "text": r.text, "score": r.score}
        for r in results
    ]


def list_recent_notes(limit: int = 20) -> list[dict]:
    """Lists stored notes without needing a search query — uses
    Qdrant's scroll() API (paging through points directly) rather than
    search_semantic(), which requires a query vector and can't answer
    "show me everything."
    """
    ensure_collection()
    records, _ = get_client().scroll(
        collection_name=settings.qdrant_collection,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    return [
        {"id": str(r.id), "company": r.payload["company"], "text": r.payload["text"]}
        for r in records
    ]
