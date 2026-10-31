import math

from app.core.config import Settings
from app.services.embeddings import HashEmbedder, build_embedder


def cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_dimension_and_normalisation() -> None:
    v = HashEmbedder(384).embed(["charged twice by KartKing"])[0]
    assert len(v) == 384 and math.isclose(sum(x * x for x in v), 1.0, rel_tol=1e-9)


def test_deterministic_and_similarity_ordering() -> None:
    e = HashEmbedder(384)
    a, b, c = e.embed(
        ["I was charged twice for one order", "charged twice for my order", "ATM did not give cash"]
    )
    assert e.embed(["abc def"]) == e.embed(["abc def"])
    assert cos(a, b) > cos(a, c)


def test_empty_text_does_not_crash() -> None:
    assert HashEmbedder(8).embed([""]) == [[0.0] * 8]


def test_factory_default_is_hash() -> None:
    assert build_embedder(Settings(embedding_provider="hash")).name == "hash"
