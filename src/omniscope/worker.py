from __future__ import annotations

import time

from .config import settings
from .db import SessionLocal
from .ingestion import claim_job, run_job


def run_forever() -> None:
    while True:
        db = SessionLocal()
        try:
            job = claim_job(db)
            if job is not None:
                run_job(db, job)
            else:
                time.sleep(settings.worker_poll_seconds)
        finally:
            db.close()


if __name__ == "__main__":
    run_forever()
