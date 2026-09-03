from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db, ping
from .models import Document, DocumentVersion, IngestionJob
from .retrieval import search


app = FastAPI(title="Enterprise Paper Search", version="0.1.0")


class UploadResponse(BaseModel):
    document_id: str
    version_id: int
    job_id: int
    status: str


class JobResponse(BaseModel):
    id: int
    version_id: int
    status: str
    attempts: int
    error: str


class SearchHit(BaseModel):
    document_id: str
    title: str
    authors: str
    language: str
    version_id: int
    chunk_id: int
    chunk_no: int
    text: str
    section_path: str
    page_start: int | None
    page_end: int | None
    score: float
    dense_score: float
    lexical_score: float


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[SearchHit]


def require_api_key(x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid X-API-Key")


@app.get("/healthz", include_in_schema=False)
def healthz(db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        healthy = ping(db)
    except Exception:
        healthy = False
    return {"status": "ok" if healthy else "degraded", "database": healthy, "embedding_backend": settings.embedding_backend}


@app.post("/v1/documents", response_model=UploadResponse, dependencies=[Depends(require_api_key)])
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = None,
    language: str = "und",
    db: Session = Depends(get_db),
) -> UploadResponse:
    filename = Path(file.filename or "paper.pdf").name
    suffix = Path(filename).suffix.lower() or ".pdf"
    temp_path = settings.data_dir / f".upload-{hashlib.sha256(filename.encode()).hexdigest()[:16]}{suffix}"
    digest = hashlib.sha256()
    with temp_path.open("wb") as handle:
        while block := await file.read(1024 * 1024):
            digest.update(block)
            handle.write(block)
    sha = digest.hexdigest()
    stored_path = settings.data_dir / f"{sha}{suffix}"
    if not stored_path.exists():
        temp_path.replace(stored_path)
    else:
        temp_path.unlink(missing_ok=True)
    existing_version = db.execute(select(DocumentVersion).where(DocumentVersion.sha256 == sha)).scalar_one_or_none()
    if existing_version:
        job = db.execute(select(IngestionJob).where(IngestionJob.version_id == existing_version.id).order_by(IngestionJob.id.desc())).scalars().first()
        if job is None:
            job = IngestionJob(version_id=existing_version.id, status="queued")
            db.add(job)
            db.commit()
            db.refresh(job)
        return UploadResponse(document_id=existing_version.document_id, version_id=existing_version.id, job_id=job.id, status=job.status)
    document = Document(title=(title or Path(filename).stem)[:1000], language=language[:16], source="local")
    db.add(document)
    db.flush()
    version = DocumentVersion(
        document_id=document.id,
        sha256=sha,
        source_path=str(stored_path),
        embedding_model=settings.embedding_model,
        status="queued",
    )
    db.add(version)
    db.flush()
    job = IngestionJob(version_id=version.id, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    return UploadResponse(document_id=document.id, version_id=version.id, job_id=job.id, status=job.status)


@app.get("/v1/jobs/{job_id}", response_model=JobResponse, dependencies=[Depends(require_api_key)])
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobResponse:
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobResponse(id=job.id, version_id=job.version_id, status=job.status, attempts=job.attempts, error=job.error)


@app.get("/v1/search", response_model=SearchResponse, dependencies=[Depends(require_api_key)])
def search_endpoint(
    q: Annotated[str, Query(min_length=1, max_length=2000)],
    top_k: Annotated[int, Query(ge=1, le=100)] = 10,
    language: str | None = None,
    db: Session = Depends(get_db),
) -> SearchResponse:
    hits = search(db, q, top_k=top_k, language=language)
    return SearchResponse(
        query=q,
        count=len(hits),
        results=[
            SearchHit(
                document_id=hit.document.id,
                title=hit.document.title,
                authors=hit.document.authors,
                language=hit.document.language,
                version_id=hit.version.id,
                chunk_id=hit.chunk.id,
                chunk_no=hit.chunk.chunk_no,
                text=hit.chunk.text,
                section_path=hit.chunk.section_path,
                page_start=hit.chunk.page_start,
                page_end=hit.chunk.page_end,
                score=round(hit.score, 8),
                dense_score=round(hit.dense_score, 8),
                lexical_score=round(hit.lexical_score, 8),
            )
            for hit in hits
        ],
    )
