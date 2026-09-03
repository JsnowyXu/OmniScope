from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://paper_search:change-me@127.0.0.1:5432/paper_search",
    )
    api_key: str = os.getenv("PAPER_SEARCH_API_KEY", "change-me")
    data_dir: Path = Path(os.getenv("PAPER_SEARCH_DATA_DIR", "./data/papers"))
    grobid_url: str = os.getenv("GROBID_URL", "http://127.0.0.1:8070")
    embedding_backend: str = os.getenv("EMBEDDING_BACKEND", "hashing").lower()
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    embedding_dim: int = int(os.getenv("EMBEDDING_DIM", "1024"))
    embedding_device: str = os.getenv("EMBEDDING_DEVICE", "cpu")
    embedding_batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
    dense_k: int = int(os.getenv("DENSE_K", "80"))
    lexical_k: int = int(os.getenv("LEXICAL_K", "80"))
    rrf_k: int = int(os.getenv("RRF_K", "60"))
    worker_poll_seconds: float = float(os.getenv("WORKER_POLL_SECONDS", "2"))
    job_stale_seconds: int = int(os.getenv("JOB_STALE_SECONDS", "3600"))


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
