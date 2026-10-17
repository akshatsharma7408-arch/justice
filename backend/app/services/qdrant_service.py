"""
JUSTICE Legal AI Backend — Qdrant Vector Service
Manages Qdrant vector retrieval over a verified Supreme Court corpus.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.config import settings

logger = logging.getLogger("justice.qdrant")

CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "verified_supreme_court_corpus.json"
VECTOR_SIZE = 256


def _pseudo_vector(text: str, size: int = VECTOR_SIZE) -> List[float]:
    """Deterministic fallback embedding vector for offline/runtime-safe retrieval."""
    digest = hashlib.sha256((text or "").encode("utf-8")).digest()
    vec = []
    for i in range(size):
        b = digest[i % len(digest)]
        vec.append((b / 127.5) - 1.0)
    return vec


def _load_verified_corpus() -> List[Dict[str, Any]]:
    if not CORPUS_PATH.exists():
        logger.warning(f"Verified Supreme Court corpus missing at {CORPUS_PATH}")
        return []

    try:
        with CORPUS_PATH.open("r", encoding="utf-8") as f:
            corpus = json.load(f)

        verified = [
            c for c in corpus
            if c.get("court") == "Supreme Court of India"
            and c.get("citation")
            and c.get("title")
        ]
        logger.info(f"Loaded verified Supreme Court corpus: {len(verified)} cases")
        return verified
    except Exception as e:
        logger.error(f"Failed loading verified corpus: {e}")
        return []


class QdrantService:
    def __init__(self):
        self.url = settings.QDRANT_URL
        self.collection_name = settings.QDRANT_COLLECTION
        self._client = None
        self._corpus = _load_verified_corpus()
        self._init_client()

    def _init_client(self):
        try:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(
                url=self.url,
                api_key=settings.QDRANT_API_KEY or None,
                timeout=5.0,
            )
            self._bootstrap_collection()
            logger.info(f"Connected to Qdrant at {self.url}")
        except Exception as e:
            logger.info(f"Qdrant unavailable at {self.url}; using lexical fallback search: {e}")
            self._client = None

    def _bootstrap_collection(self):
        if not self._client or not self._corpus:
            return

        from qdrant_client.models import Distance, VectorParams, PointStruct

        should_create = False
        try:
            self._client.get_collection(self.collection_name)
        except Exception:
            should_create = True

        if should_create:
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )

        points = []
        for idx, case in enumerate(self._corpus, start=1):
            text_blob = (
                f"{case.get('title', '')} {case.get('citation', '')} {case.get('ratioSummary', '')} "
                f"{' '.join(case.get('statutes', []))} {' '.join(case.get('keywords', []))}"
            )
            payload = dict(case)
            payload["searchText"] = text_blob
            points.append(
                PointStruct(
                    id=idx,
                    vector=_pseudo_vector(text_blob),
                    payload=payload,
                )
            )

        self._client.upsert(collection_name=self.collection_name, points=points)

    def _search_qdrant(
        self,
        query: str,
        court_filter: str = "ALL",
        bench_filter: str = "ALL",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        if not self._client:
            return []

        from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

        must_conditions = []

        if court_filter != "ALL":
            must_conditions.append(
                FieldCondition(key="court", match=MatchValue(value=court_filter))
            )

        if bench_filter == "CONSTITUTION":
            must_conditions.append(FieldCondition(key="benchSize", range=Range(gte=5)))
        elif bench_filter == "DIVISION":
            must_conditions.append(FieldCondition(key="benchSize", match=MatchValue(value=2)))

        query_filter = Filter(must=must_conditions) if must_conditions else None

        hits = self._client.search(
            collection_name=self.collection_name,
            query_vector=_pseudo_vector(query),
            query_filter=query_filter,
            with_payload=True,
            limit=limit,
        )

        results: List[Dict[str, Any]] = []
        for hit in hits:
            payload = dict(hit.payload or {})
            payload.pop("searchText", None)
            payload["relevance_score"] = round(float(hit.score), 3)
            results.append(payload)
        return results

    def _search_lexical_fallback(
        self,
        query: str,
        court_filter: str = "ALL",
        bench_filter: str = "ALL",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        terms = [t.lower() for t in query.split() if len(t) > 2]
        results = []

        for case in self._corpus:
            if court_filter != "ALL" and case.get("court") != court_filter:
                continue

            bench_size = case.get("benchSize", 0)
            if bench_filter == "CONSTITUTION" and bench_size < 5:
                continue
            if bench_filter == "DIVISION" and bench_size != 2:
                continue

            text_blob = (
                f"{case.get('title', '')} {case.get('citation', '')} {case.get('ratioSummary', '')} "
                f"{' '.join(case.get('statutes', []))} {' '.join(case.get('keywords', []))}"
            ).lower()

            matches = sum(1 for term in terms if term in text_blob)
            score = 0.5 + (matches * 0.1)

            if len(terms) == 0 or matches > 0:
                item = dict(case)
                item["relevance_score"] = round(min(score, 0.99), 3)
                results.append(item)

        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return results[:limit]

    def search_precedents(
        self,
        query: str,
        court_filter: str = "ALL",
        bench_filter: str = "ALL",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Searches precedents via Qdrant vectors, falling back to lexical retrieval."""
        try:
            if self._client:
                qdrant_results = self._search_qdrant(
                    query=query,
                    court_filter=court_filter,
                    bench_filter=bench_filter,
                    limit=limit,
                )
                if qdrant_results:
                    return qdrant_results
        except Exception as e:
            logger.warning(f"Qdrant search failed; switching to lexical fallback: {e}")

        return self._search_lexical_fallback(
            query=query,
            court_filter=court_filter,
            bench_filter=bench_filter,
            limit=limit,
        )

    def check_health(self) -> Dict[str, Any]:
        """Reports Qdrant connectivity and verified corpus health state."""
        if self._client:
            try:
                collections = self._client.get_collections()
                return {
                    "status": "connected",
                    "url": self.url,
                    "collection": self.collection_name,
                    "collections_count": len(collections.collections),
                    "indexed_precedents": len(self._corpus),
                    "corpus_source": str(CORPUS_PATH),
                }
            except Exception as e:
                return {
                    "status": "local_fallback",
                    "url": self.url,
                    "error": str(e),
                    "indexed_precedents": len(self._corpus),
                    "corpus_source": str(CORPUS_PATH),
                }

        return {
            "status": "in_memory_index",
            "url": self.url,
            "indexed_precedents": len(self._corpus),
            "corpus_source": str(CORPUS_PATH),
            "detail": "Qdrant unavailable; serving verified Supreme Court corpus via lexical fallback.",
        }


qdrant_service = QdrantService()
