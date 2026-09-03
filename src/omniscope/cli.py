from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import requests


def evaluate(path: Path, url: str, api_key: str, k: int) -> dict[str, float]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    recall = 0.0
    reciprocal = 0.0
    count = 0
    for row in rows:
        response = requests.get(
            f"{url.rstrip('/')}/v1/search",
            params={"q": row["query"], "top_k": k},
            headers={"X-API-Key": api_key},
            timeout=120,
        )
        response.raise_for_status()
        ids = [hit["document_id"] for hit in response.json()["results"]]
        relevant = set(row["relevant_document_ids"])
        if relevant & set(ids):
            recall += 1
        positions = [ids.index(item) + 1 for item in relevant if item in ids]
        if positions:
            reciprocal += 1.0 / min(positions)
        count += 1
    return {"queries": float(count), f"recall@{k}": recall / count if count else 0.0, f"mrr@{k}": reciprocal / count if count else 0.0}


def main() -> None:
    parser = argparse.ArgumentParser(prog="paper-search")
    sub = parser.add_subparsers(dest="command", required=True)
    eval_parser = sub.add_parser("eval")
    eval_parser.add_argument("--queries", type=Path, required=True)
    eval_parser.add_argument("--url", default=os.getenv("PAPER_SEARCH_URL", "http://127.0.0.1:8088"))
    eval_parser.add_argument("--key", default=os.getenv("PAPER_SEARCH_API_KEY", "change-me"))
    eval_parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()
    if args.command == "eval":
        print(json.dumps(evaluate(args.queries, args.url, args.key, args.k), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
