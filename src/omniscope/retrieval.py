from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .config import settings
from .text import embed_one, lexicalize, normalize_space


@dataclass
class Hit:
    chunk: Chunk
    document: Document
    version: DocumentVersion
    dense_score: float = 0.0
    lexical_score: float = 0.0
    score: float = 0.0


def reciprocal_rank_fusion(
    dense: list[tuple[int, float]], lexical: list[tuple[int, float]], *, rrf_k: int = 60
) -> dict[int, float]:
    fused: defaultdict[int, float] = defaultdict(float)
    for rank, (item_id, _) in enumerate(dense, start=1):
        fused[item_id] += 1.0 / (rrf_k + rank)
    for rank, (item_id, _) in enumerate(lexical, start=1):
        fused[item_id] += 1.0 / (rrf_k + rank)
    return dict(fused)


def search(db: Session, query: str, top_k: int = 10, language: str | None = None) -> list[Hit]:
    from .models import Chunk, Document, DocumentVersion

    query = normalize_space(query)
    if not query:
        return []
    embedding = embed_one(query)
    dense_distance = Chunk.embedding.cosine_distance(embedding).label("distance")
    dense_stmt = (
        select(Chunk, Document, DocumentVersion, dense_distance)
        .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Chunk.embedding_model == settings.embedding_model)
        .where(DocumentVersion.status == "succeeded")
        .order_by(dense_distance)
        .limit(settings.dense_k)
    )
    if language:
        dense_stmt = dense_stmt.where(Document.language == language)
    dense_rows = db.execute(dense_stmt).all()
    dense_ids = [(chunk.id, float(1.0 - distance)) for chunk, _, _, distance in dense_rows]

    lexical_query = lexicalize(query)
    ts_query = func.websearch_to_tsquery("simple", lexical_query)
    lexical_score = func.ts_rank_cd(Chunk.search_vector, ts_query).label("lexical_score")
    lexical_stmt = (
        select(Chunk, Document, DocumentVersion, lexical_score)
        .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Chunk.search_vector.op("@@")(ts_query))
        .where(DocumentVersion.status == "succeeded")
        .order_by(desc(lexical_score))
        .limit(settings.lexical_k)
    )
    if language:
        lexical_stmt = lexical_stmt.where(Document.language == language)
    lexical_rows = db.execute(lexical_stmt).all()
    lexical_ids = [(chunk.id, float(score)) for chunk, _, _, score in lexical_rows]

    fused = reciprocal_rank_fusion(dense_ids, lexical_ids, rrf_k=settings.rrf_k)
    candidates = {chunk.id: (chunk, document, version) for chunk, document, version, _ in dense_rows}
    candidates.update({chunk.id: (chunk, document, version) for chunk, document, version, _ in lexical_rows})
    dense_scores = dict(dense_ids)
    lexical_scores = dict(lexical_ids)
    hits = [
        Hit(
            chunk=chunk,
            document=document,
            version=version,
            dense_score=dense_scores.get(chunk_id, 0.0),
            lexical_score=lexical_scores.get(chunk_id, 0.0),
            score=score,
        )
        for chunk_id, score in fused.items()
        for chunk, document, version in [candidates[chunk_id]]
    ]
    hits.sort(key=lambda item: item.score, reverse=True)

    # One result per paper by default; this is better for downstream paper selection.
    selected: list[Hit] = []
    seen_documents: set[str] = set()
    for hit in hits:
        if hit.document.id in seen_documents:
            continue
        seen_documents.add(hit.document.id)
        selected.append(hit)
        if len(selected) >= top_k:
            break
    return selected
