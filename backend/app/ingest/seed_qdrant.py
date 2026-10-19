"""
JUSTICE Legal AI Backend - Qdrant Precedent Seeder
Indexes the verified Section 27 / Article 141 precedent corpus
(backend/app/data/section27_precedents.json) into Qdrant.

- Creates the collection (cosine distance) if missing; embedding dimension is
  chosen by the active local embedding mode (all-MiniLM-L6-v2, 384-dim).
- Idempotent: point ids are stable UUID5 hashes of the case id, so re-running
  never duplicates.
- All payload metadata (citation, court, bench, status, source URL) is stored
  on the point so search results carry full provenance.

Usage:
    python -m app.ingest.seed_qdrant            # seed into live Qdrant
    python -m app.ingest.seed_qdrant --dry-run  # validate corpus + embeddings only
"""

import argparse
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings
from app.services.embedding_service import embedding_service

logger = logging.getLogger("justice.ingest.qdrant")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "section27_precedents.json"

# Namespace for stable, collision-free point ids (UUID5 of the case id).
POINT_NS = uuid.UUID("6f1c5c2e-9c3d-4a7b-8f2a-1d5a1c000000")


def load_corpus(path: Path = CORPUS_PATH) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    precedents = data.get("precedents", [])
    logger.info("Loaded %d precedents from %s", len(precedents), path)
    return precedents


def case_to_text(case: Dict[str, Any]) -> str:
    return (
        f"{case['title']}. {case['citation']}. {case['court']}. "
        f"{' '.join(case.get('statutes', []))}. {case.get('ratioSummary', '')}. "
        f"{' '.join(case.get('keywords', []))}"
    )


def seed_qdrant(dry_run: bool = False) -> Dict[str, Any]:
    cases = load_corpus()
    texts = [case_to_text(c) for c in cases]
    vectors = embedding_service.embed_texts(texts)
    dim = embedding_service.dimension
    logger.info("Embedding mode: %s (dim=%d)", embedding_service.mode, dim)

    report: Dict[str, Any] = {
        "collection": settings.QDRANT_COLLECTION,
        "cases": len(cases),
        "embedding": embedding_service.describe(),
        "seeded": 0,
        "dry_run": dry_run,
    }

    if dry_run:
        for c, v in zip(cases, vectors):
            assert len(v) == dim, f"vector dim mismatch for {c['id']}"
        report["seeded"] = len(cases)
        logger.info("Dry run OK: %d cases, all vectors dim=%d", len(cases), dim)
        return report

    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None, timeout=10.0)

    existing = {c.name for c in client.get_collections().collections}
    if settings.QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        logger.info("Created collection '%s' (dim=%d, cosine)", settings.QDRANT_COLLECTION, dim)
    else:
        info = client.get_collection(settings.QDRANT_COLLECTION)
        live_dim = info.config.params.vectors.size
        if live_dim != dim:
            raise RuntimeError(
                f"Collection '{settings.QDRANT_COLLECTION}' exists with dim={live_dim} but active "
                f"embedding mode produces dim={dim}. Delete/recreate the collection or match the "
                f"embedding mode (GEMINI_API_KEY configured?) before reseeding."
            )

    points = []
    for case, vector in zip(cases, vectors):
        payload = dict(case)
        payload["embedding_mode"] = embedding_service.mode
        points.append(
            PointStruct(id=str(uuid.uuid5(POINT_NS, case["id"])), vector=vector, payload=payload)
        )
    client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)
    report["seeded"] = len(points)
    logger.info("Upserted %d points into '%s'", len(points), settings.QDRANT_COLLECTION)
    return report


def main():
    parser = argparse.ArgumentParser(description="Seed the verified precedent corpus into Qdrant.")
    parser.add_argument("--dry-run", action="store_true", help="Validate corpus and embeddings without touching Qdrant")
    args = parser.parse_args()
    report = seed_qdrant(dry_run=args.dry_run)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
