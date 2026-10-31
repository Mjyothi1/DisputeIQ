"""Text embeddings (configurable) used for similar-case retrieval.

* ``hash``  - dependency-free deterministic feature hashing (unigrams + bigrams). Default, and the
              fallback when sentence-transformers is not installed.
* ``local`` - sentence-transformers (e.g. all-MiniLM-L6-v2, 384 dims).
* ``openai``- text-embedding-3-small, requested at ``EMBEDDING_DIM`` dimensions.
All vectors are L2-normalised and have exactly ``EMBEDDING_DIM`` entries (the pgvector column size).
"""

import logging
import math
import re
import zlib
from collections.abc import Sequence
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger(__name__)
_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def _normalise(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


class HashEmbedder:
    """Signed feature hashing; similar wording gives high cosine similarity. Offline and fast."""

    name = "hash"

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            toks = _TOKEN.findall(text.lower())
            feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
            vec = [0.0] * self.dim
            for f in feats:
                h = zlib.crc32(f.encode())
                vec[h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
            out.append(_normalise(vec))
        return out


class SentenceTransformerEmbedder:
    name = "local"

    def __init__(self, model_name: str, dim: int) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name or "all-MiniLM-L6-v2")
        actual = self.model.get_sentence_embedding_dimension()
        if actual != dim:
            raise ValueError(f"model outputs {actual} dims but EMBEDDING_DIM={dim}")
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [
            list(map(float, v)) for v in self.model.encode(list(texts), normalize_embeddings=True)
        ]


class OpenAIEmbedder:
    name = "openai"

    def __init__(self, api_key: str, model: str, dim: int) -> None:
        import openai

        self.client = openai.OpenAI(api_key=api_key)
        self.model, self.dim = model or "text-embedding-3-small", dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(
            model=self.model, input=list(texts), dimensions=self.dim
        )
        return [_normalise(list(d.embedding)) for d in resp.data]


def build_embedder(settings: Settings) -> Embedder:
    """Create the configured embedder, degrading to hashing if a local model is unavailable."""
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is empty")
        return OpenAIEmbedder(
            settings.openai_api_key, settings.embedding_model, settings.embedding_dim
        )
    if settings.embedding_provider == "local":
        try:
            return SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_dim)
        except Exception as exc:  # not installed, offline, or wrong dimension
            logger.warning("local embeddings unavailable, using hash embedder: %s", exc)
    return HashEmbedder(settings.embedding_dim)
