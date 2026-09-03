from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from .config import settings


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", re.U)


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\x00", "")).strip()


def lexicalize(text: str) -> str:
    """Create simple-config tokens that work for English and Chinese n-grams."""
    clean = normalize_space(text).lower()
    try:
        import jieba  # type: ignore

        tokens = [t.strip() for t in jieba.cut(clean, cut_all=False) if t.strip()]
    except ImportError:
        tokens = TOKEN_RE.findall(clean)
    return " ".join(tokens)


def hashing_embed(text: str) -> list[float]:
    tokens = TOKEN_RE.findall((text or "").lower())
    tokens.extend(f"{a}_{b}" for a, b in zip(tokens, tokens[1:]))
    vector = [0.0] * settings.embedding_dim
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        raw = int.from_bytes(digest, "big")
        index = raw % settings.embedding_dim
        vector[index] += 1.0 if raw & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else vector


@lru_cache(maxsize=1)
def embedding_model():
    if settings.embedding_backend != "sentence-transformers":
        return None
    from sentence_transformers import SentenceTransformer  # type: ignore

    return SentenceTransformer(settings.embedding_model, device=settings.embedding_device)


def embed_many(texts: list[str]) -> list[list[float]]:
    if settings.embedding_backend != "sentence-transformers":
        return [hashing_embed(text) for text in texts]
    model = embedding_model()
    vectors = model.encode(
        texts,
        batch_size=settings.embedding_batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [[float(x) for x in row] for row in vectors.tolist()]


def embed_one(text: str) -> list[float]:
    return embed_many([text])[0]
