from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .config import settings
from .text import embed_many, lexicalize, normalize_space


@dataclass
class Page:
    number: int
    text: str


@dataclass
class Section:
    path: str
    text: str
    page_start: int | None = None
    page_end: int | None = None


@dataclass
class ChunkDraft:
    no: int
    text: str
    section_path: str
    page_start: int | None
    page_end: int | None
    char_start: int
    char_end: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_pages(path: Path) -> list[Page]:
    if path.suffix.lower() != ".pdf":
        text = path.read_text(encoding="utf-8", errors="ignore")
        return [Page(1, normalize_space(text))] if normalize_space(text) else []
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required for PDF ingestion") from exc
    reader = PdfReader(str(path))
    pages: list[Page] = []
    for index, raw_page in enumerate(reader.pages, start=1):
        text = normalize_space(raw_page.extract_text() or "")
        if text:
            pages.append(Page(index, text))
    return pages


def parse_grobid(path: Path) -> list[Section]:
    with path.open("rb") as handle:
        response = requests.post(
            f"{settings.grobid_url.rstrip('/')}/api/processFulltextDocument",
            files={"input": (path.name, handle, "application/pdf")},
            data={"consolidateHeader": "1", "consolidateCitations": "0"},
            timeout=300,
        )
    response.raise_for_status()
    root = ET.fromstring(response.text)
    sections: list[Section] = []
    for div in root.iter():
        if _local_name(div.tag) != "div":
            continue
        heads = [node for node in div if _local_name(node.tag) == "head"]
        title = normalize_space(" ".join(node.itertext() for node in heads)) if heads else ""
        paragraphs = [normalize_space(" ".join(node.itertext())) for node in div if _local_name(node.tag) == "p"]
        body = normalize_space(" ".join(item for item in paragraphs if item))
        if not body:
            continue
        path_name = title or f"section-{len(sections) + 1}"
        sections.append(Section(path=path_name, text=body))
    if not sections:
        raise ValueError("GROBID returned no text sections")
    return sections


def build_fallback_sections(pages: list[Page]) -> list[Section]:
    sections: list[Section] = []
    for page in pages:
        if not page.text:
            continue
        sections.append(Section(path=f"page-{page.number}", text=page.text, page_start=page.number, page_end=page.number))
    return sections


def load_sections(path: Path) -> tuple[list[Section], str, int]:
    pages = extract_pages(path)
    if path.suffix.lower() == ".pdf":
        try:
            return parse_grobid(path), "grobid", len(pages)
        except (OSError, requests.RequestException, ET.ParseError, ValueError):
            pass
    return build_fallback_sections(pages), "fallback", len(pages)


def make_chunks(sections: list[Section], max_chars: int = 1800, overlap: int = 180) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    number = 0
    for section in sections:
        text = normalize_space(section.text)
        if not text:
            continue
        # Keep paragraph boundaries when possible; long paragraphs are windowed.
        paragraphs = [part.strip() for part in re.split(r"(?<=[。！？.!?])\s+|\n+", text) if part.strip()]
        buffer = ""
        offset = 0
        for paragraph in paragraphs:
            if len(paragraph) > max_chars:
                if buffer:
                    drafts.append(ChunkDraft(number, buffer, section.path, section.page_start, section.page_end, offset, offset + len(buffer)))
                    number += 1
                    buffer = ""
                start = 0
                while start < len(paragraph):
                    end = min(start + max_chars, len(paragraph))
                    piece = paragraph[start:end].strip()
                    if piece:
                        drafts.append(
                            ChunkDraft(number, piece, section.path, section.page_start, section.page_end, offset + start, offset + end)
                        )
                        number += 1
                    if end >= len(paragraph):
                        break
                    start = max(end - overlap, start + 1)
                offset += len(paragraph) + 1
                continue
            if buffer and len(buffer) + len(paragraph) + 1 > max_chars:
                drafts.append(
                    ChunkDraft(number, buffer, section.path, section.page_start, section.page_end, offset, offset + len(buffer))
                )
                number += 1
                tail = buffer[-overlap:] if overlap else ""
                buffer = f"{tail} {paragraph}".strip()
                offset += max(1, len(buffer) - len(tail))
            else:
                buffer = f"{buffer} {paragraph}".strip()
        if buffer:
            drafts.append(ChunkDraft(number, buffer, section.path, section.page_start, section.page_end, offset, offset + len(buffer)))
            number += 1
    return drafts


def ingest_version(db: Session, version: "DocumentVersion") -> int:
    from .models import Chunk

    path = Path(version.source_path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    sections, parser, page_count = load_sections(path)
    drafts = make_chunks(sections)
    vectors = embed_many([draft.text for draft in drafts])
    db.query(Chunk).filter(Chunk.version_id == version.id).delete()
    for draft, vector in zip(drafts, vectors, strict=True):
        db.add(
            Chunk(
                version_id=version.id,
                chunk_no=draft.no,
                text=draft.text,
                lexical_text=lexicalize(draft.text),
                section_path=draft.section_path,
                page_start=draft.page_start,
                page_end=draft.page_end,
                char_start=draft.char_start,
                char_end=draft.char_end,
                embedding=vector,
                embedding_model=settings.embedding_model,
            )
        )
    version.page_count = page_count
    version.parser = parser
    version.status = "succeeded"
    version.error = ""
    version.processed_at = datetime.now(timezone.utc)
    db.commit()
    return len(drafts)


def claim_job(db: Session) -> "IngestionJob | None":
    from .models import IngestionJob

    now = datetime.now(timezone.utc)
    stale = now.timestamp() - settings.job_stale_seconds
    stmt = (
        select(IngestionJob)
        .where(
            or_(
                IngestionJob.status == "queued",
                (IngestionJob.status == "running") & (IngestionJob.locked_at < datetime.fromtimestamp(stale, timezone.utc)),
            )
        )
        .order_by(IngestionJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = db.execute(stmt).scalar_one_or_none()
    if job is None:
        return None
    job.status = "running"
    job.attempts += 1
    job.locked_at = now
    db.commit()
    return job


def run_job(db: Session, job: "IngestionJob") -> None:
    from .models import DocumentVersion

    version = db.get(DocumentVersion, job.version_id)
    if version is None:
        job.status = "failed"
        job.error = "document version not found"
        db.commit()
        return
    try:
        ingest_version(db, version)
        job.status = "succeeded"
        job.error = ""
    except Exception as exc:  # worker must mark the job and continue
        db.rollback()
        version = db.get(DocumentVersion, job.version_id)
        if version:
            version.status = "failed"
            version.error = str(exc)[:4000]
        job = db.get(IngestionJob, job.id) or job
        job.status = "failed"
        job.error = str(exc)[:4000]
    job.finished_at = datetime.now(timezone.utc)
    db.commit()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
