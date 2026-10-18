"""
JUSTICE Legal AI Backend - Qdrant Vector Service
Hybrid retrieval over the verified Indian precedent corpus
(backend/app/data/section27_precedents.json).

Modes:
  - "qdrant":  live Qdrant collection queried with embedded query vectors
               (seed with: python -m app.ingest.seed_qdrant).
  - "local_index": deterministic lexical fallback over the same verified
               corpus JSON when no Qdrant server is reachable.

The active mode is reported in every search result and in /health, so the
fallback is always labeled, never silent.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.embedding_service import embedding_service

logger = logging.getLogger("justice.qdrant")

CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "section27_precedents.json"


def _load_corpus() -> List[Dict[str, Any]]:
    try:
        with open(CORPUS_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("precedents", [])
    except Exception as e:
        logger.error("Could not load precedent corpus at %s: %s", CORPUS_PATH, e)
        return []


class QdrantService:
    def __init__(self):
        self.url = settings.QDRANT_URL
        self.collection_name = settings.QDRANT_COLLECTION
        self._client = None
        self.corpus = _load_corpus()
        self._init_client()

    def _init_client(self):
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(
                url=self.url, api_key=settings.QDRANT_API_KEY or None, timeout=3.0
            )
            # Fail fast if the daemon is unreachable so we drop to fallback.
            client.get_collections()
            self._client = client
            logger.info("Connected to Qdrant at %s", self.url)
        except Exception as e:
            logger.info("Qdrant not reachable at %s; using labeled local index fallback: %s", self.url, e)
            self._client = None

    # ------------------------------------------------------------------ #
    # Retrieval                                                           #
    # ------------------------------------------------------------------ #
    def search_precedents(
        self,
        query: str,
        court_filter: str = "ALL",
        bench_filter: str = "ALL",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        if self._client:
            try:
                return self._search_qdrant(query, court_filter, bench_filter, limit)
            except Exception as e:
                logger.warning("Live Qdrant query failed, falling back to local index: %s", e)
        return self._search_local(query, court_filter, bench_filter, limit)

    def _matches_filters(self, case: Dict[str, Any], court_filter: str, bench_filter: str) -> bool:
        if court_filter != "ALL" and case.get("court") != court_filter:
            return False
        if bench_filter == "CONSTITUTION" and case.get("benchSize", 0) < 5:
            return False
        if bench_filter == "DIVISION" and case.get("benchSize") != 2:
            return False
        return True

    def _search_qdrant(self, query: str, court_filter: str, bench_filter: str, limit: int) -> List[Dict[str, Any]]:
        vector = embedding_service.embed_query(query)
        # Pull a generous window, then apply court/bench filters over payload.
        hits = self._client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            limit=max(limit * 4, 20),
        )
        results: List[Dict[str, Any]] = []
        for hit in hits:
            case = dict(hit.payload or {})
            if not self._matches_filters(case, court_filter, bench_filter):
                continue
            case["relevance_score"] = round(float(hit.score), 3)
            case["retrieval_mode"] = f"qdrant+{embedding_service.mode}"
            results.append(case)
            if len(results) >= limit:
                break
        return results

    def _search_local(self, query: str, court_filter: str, bench_filter: str, limit: int) -> List[Dict[str, Any]]:
        terms = [t.lower() for t in query.split() if len(t) > 2]
        results: List[Dict[str, Any]] = []
        for case in self.corpus:
            if not self._matches_filters(case, court_filter, bench_filter):
                continue
            text_blob = (
                f"{case.get('title', '')} {case.get('citation', '')} "
                f"{case.get('ratioSummary', '')} "
                f"{' '.join(case.get('statutes', []))} {' '.join(case.get('keywords', []))}"
            ).lower()
            matches = sum(1 for term in terms if term in text_blob)
            if len(terms) == 0 or matches > 0:
                item = dict(case)
                item["relevance_score"] = round(min(0.5 + matches * 0.1, 0.99), 3)
                item["retrieval_mode"] = "local_index_fallback"
                results.append(item)
        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------ #
    # Health                                                              #
    # ------------------------------------------------------------------ #
    def check_health(self) -> Dict[str, Any]:
        if self._client:
            try:
                collections = self._client.get_collections()
                seeded = False
                points = 0
                if self.collection_name in {c.name for c in collections.collections}:
                    info = self._client.get_collection(self.collection_name)
                    points = getattr(info, "points_count", 0) or 0
                    seeded = points > 0
                return {
                    "status": "connected",
                    "url": self.url,
                    "collection": self.collection_name,
                    "collection_seeded": seeded,
                    "points_count": points,
                    "embedding": embedding_service.describe(),
                    "hint": None if seeded else "Run: python -m app.ingest.seed_qdrant",
                }
            except Exception as e:
                return {"status": "local_fallback", "url": self.url, "error": str(e),
                        "indexed_precedents": len(self.corpus)}
        return {
            "status": "local_index_fallback",
            "url": self.url,
            "indexed_precedents": len(self.corpus),
            "detail": "Qdrant daemon idle; serving the verified corpus from local index. Start Qdrant and run: python -m app.ingest.seed_qdrant",
        }


qdrant_service = QdrantService()
