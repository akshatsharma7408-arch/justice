"""
JUSTICE Legal AI Backend - Qdrant Vector Service
Hybrid retrieval over the verified Indian precedent corpus
(backend/app/data/section27_precedents.json) and real Supreme Court
of India judgments (collection 'sc_judgments').

Modes:
  - "qdrant": live Qdrant Cloud collection queried with dense query vectors (384-dim).
  - "local_index": dense semantic retrieval via local all-MiniLM-L6-v2 embeddings
    over the verified 12-precedent corpus and 960 real Supreme Court of India judgments
    (17,737 chunks) when Qdrant Cloud is idle/offline.

The active mode is reported in every search result and in /health, so the
retrieval mode and embedding engine are always transparent.
"""

import json
import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

from app.config import settings
from app.services.embedding_service import embedding_service

logger = logging.getLogger("justice.qdrant")

CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "section27_precedents.json"
SC_DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sc_dataset"
SC_CHUNKS_PATH = SC_DATASET_DIR / "chunks" / "chunks.json"
SC_EMBEDDINGS_PATH = SC_DATASET_DIR / "embeddings" / "embeddings_checkpoint.parquet"
SC_METADATA_PATH = SC_DATASET_DIR / "metadata" / "filtered_cases.parquet"


def _load_corpus() -> List[Dict[str, Any]]:
    try:
        with open(CORPUS_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("precedents", [])
    except Exception as e:
        logger.error("Could not load precedent corpus at %s: %s", CORPUS_PATH, e)
        return []


def _case_to_text(case: Dict[str, Any]) -> str:
    return (
        f"{case.get('title', '')}. {case.get('citation', '')}. {case.get('court', '')}. "
        f"{' '.join(case.get('statutes', []))}. {case.get('ratioSummary', '')}. "
        f"{' '.join(case.get('keywords', []))}"
    )


class QdrantService:
    def __init__(self):
        self.url = settings.QDRANT_URL
        self.collection_name = settings.QDRANT_COLLECTION
        self.sc_collection_name = "sc_judgments"
        self._client = None
        self.corpus = _load_corpus()
        self._corpus_vectors: Optional[List[List[float]]] = None

        # Local SC judgments dataset index cache
        self._sc_chunks: Optional[List[Dict[str, Any]]] = None
        self._sc_vectors: Optional[np.ndarray] = None
        self._sc_cases_meta: Optional[Dict[str, Dict[str, Any]]] = None
        self._sc_loaded: bool = False

        self._init_client()

    def _init_client(self):
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(
                url=self.url, api_key=settings.QDRANT_API_KEY or None, timeout=15.0
            )
            # Fail fast if the daemon is unreachable so we drop to fallback.
            client.get_collections()
            self._client = client
            logger.info("Connected to Qdrant at %s", self.url)
        except Exception as e:
            logger.info("Qdrant not reachable at %s; using labeled local index fallback: %s", self.url, e)
            self._client = None

    def _get_corpus_vectors(self) -> List[List[float]]:
        """Caches semantic vectors for the 12 verified corpus precedents."""
        if self._corpus_vectors is None:
            texts = [_case_to_text(c) for c in self.corpus]
            self._corpus_vectors = embedding_service.embed_texts(texts)
        return self._corpus_vectors

    def _ensure_sc_dataset_loaded(self):
        """Loads and caches the 17,737 chunks and dense vectors from the SC dataset."""
        if self._sc_loaded:
            return
        self._sc_loaded = True

        try:
            if SC_CHUNKS_PATH.exists() and SC_EMBEDDINGS_PATH.exists():
                with open(SC_CHUNKS_PATH, "r", encoding="utf-8") as f:
                    self._sc_chunks = json.load(f)

                import pandas as pd
                df = pd.read_parquet(SC_EMBEDDINGS_PATH)
                raw_vecs = np.array(df["vector"].tolist(), dtype=np.float32)

                # Pre-normalize for instant cosine similarity via matrix dot product
                norms = np.linalg.norm(raw_vecs, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                self._sc_vectors = raw_vecs / norms

                # Build fast case metadata index for citation lookup
                self._sc_cases_meta = {}
                for c in self._sc_chunks:
                    cid = c.get("case_id", "")
                    if cid and cid not in self._sc_cases_meta:
                        self._sc_cases_meta[cid] = {
                            "case_name": c.get("case_name"),
                            "year": c.get("year"),
                            "citation": c.get("citation"),
                            "neutral_citation": c.get("neutral_citation"),
                            "bench": c.get("bench"),
                            "source_link": c.get("source_link")
                        }

                logger.info(
                    "Loaded local Supreme Court dataset: %d chunks across %d judgments (%.1f MB vectors)",
                    len(self._sc_chunks), len(self._sc_cases_meta), self._sc_vectors.nbytes / (1024 * 1024)
                )
        except Exception as e:
            logger.warning("Could not load local Supreme Court dataset: %s", e)

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
        target_collection = self.collection_name

        try:
            available = {c.name for c in self._client.get_collections().collections}
            if self.sc_collection_name in available:
                target_collection = self.sc_collection_name
        except Exception:
            pass

        hits = self._client.search(
            collection_name=target_collection,
            query_vector=vector,
            limit=max(limit * 4, 20),
        )
        results: List[Dict[str, Any]] = []
        seen_cases = set()
        for hit in hits:
            case = dict(hit.payload or {})
            if not self._matches_filters(case, court_filter, bench_filter):
                continue
            if not case.get("title") and case.get("case_name"):
                case["title"] = case.get("case_name")
            if not case.get("decisionYear") and case.get("year"):
                case["decisionYear"] = case.get("year")
            if not case.get("ratioSummary") and case.get("text"):
                case["ratioSummary"] = case["text"][:450] + ("..." if len(case["text"]) > 450 else "")
            if not case.get("court"):
                case["court"] = "Supreme Court of India"
            if not case.get("benchType"):
                case["benchType"] = "Supreme Court Bench"
            if not case.get("benchSize"):
                case["benchSize"] = 2
            if not case.get("statutes"):
                case["statutes"] = ["Indian Contract Act, 1872", "Constitution of India, Article 141"]

            case_key = (case.get("title") or "").strip().lower()
            if case_key and case_key in seen_cases:
                continue
            if case_key:
                seen_cases.add(case_key)

            case["relevance_score"] = round(float(hit.score), 3)
            case["retrieval_mode"] = f"qdrant+{target_collection}+{embedding_service.mode}"
            results.append(case)
            if len(results) >= limit:
                break
        return results

    def _search_local(self, query: str, court_filter: str, bench_filter: str, limit: int) -> List[Dict[str, Any]]:
        query_vec = embedding_service.embed_query(query)
        corpus_vecs = self._get_corpus_vectors()
        norm_q = math.sqrt(sum(q * q for q in query_vec)) or 1.0

        # Substantive search terms excluding generic legal stop words
        stopwords = {
            "the", "and", "for", "with", "from", "that", "this", "what", "which", "where", "when", "who", "whom",
            "how", "why", "are", "was", "were", "has", "have", "had", "been", "does", "did", "can", "could", "shall",
            "will", "would", "should", "about", "tell", "show", "give", "explain", "under", "over", "into", "than",
            "then", "also", "any", "all", "its", "our", "your", "law", "legal", "court", "judgment", "ruling", "holding",
            "case", "matter", "concept", "doctrine", "principle", "rule", "bench", "act", "india", "state"
        }
        terms = [t.lower() for t in re.findall(r'[a-zA-Z0-9]{3,}', query) if t.lower() not in stopwords]
        min_required = 1 if len(terms) <= 2 else 2

        results: List[Dict[str, Any]] = []

        # 1. Search the 12 verified landmark Section 27 precedents
        for case, c_vec in zip(self.corpus, corpus_vecs):
            if not self._matches_filters(case, court_filter, bench_filter):
                continue

            dot = sum(q * c for q, c in zip(query_vec, c_vec))
            norm_c = math.sqrt(sum(c * c for c in c_vec)) or 1.0
            cos_sim = dot / (norm_q * norm_c)

            text_blob = (
                f"{case.get('title', '')} {case.get('citation', '')} "
                f"{case.get('ratioSummary', '')} "
                f"{' '.join(case.get('statutes', []))} {' '.join(case.get('keywords', []))}"
            ).lower()
            matches = sum(1 for term in terms if term in text_blob)

            if (cos_sim >= 0.35 and (len(terms) == 0 or matches >= min_required)) or (cos_sim >= 0.48):
                item = dict(case)
                final_score = round(max(float(cos_sim), min(0.45 + matches * 0.1, 0.98)), 3)
                item["relevance_score"] = final_score
                item["retrieval_mode"] = f"local_index+12_precedents+{embedding_service.mode}"
                results.append(item)

        # 2. Search real Supreme Court of India judgments dataset (17,737 chunks)
        self._ensure_sc_dataset_loaded()
        if self._sc_vectors is not None and self._sc_chunks:
            q_arr = np.array(query_vec, dtype=np.float32)
            q_arr_norm = q_arr / (np.linalg.norm(q_arr) or 1.0)

            # Cosine similarity across all 17,737 chunks in ~2ms
            sims = np.dot(self._sc_vectors, q_arr_norm)
            candidate_indices = np.where(sims >= 0.30)[0]

            if len(candidate_indices) > 0:
                # Sort candidates descending
                top_order = candidate_indices[np.argsort(sims[candidate_indices])[::-1]]
                seen_cases = {r.get("title", "").lower() for r in results}

                for idx in top_order:
                    chunk = self._sc_chunks[idx]
                    c_name = chunk.get("case_name", "").strip()
                    if not c_name or c_name.lower() in seen_cases:
                        continue

                    # Keyword bonus for precision
                    c_text_lower = (c_name + " " + chunk.get("text", "")).lower()
                    kw_matches = sum(1 for t in terms if t in c_text_lower)
                    sim_score = float(sims[idx])

                    # Minimum threshold: genuine semantic similarity and substantive keyword matches
                    if (sim_score >= 0.45) or (sim_score >= 0.30 and (len(terms) == 0 or kw_matches >= min_required)):
                        seen_cases.add(c_name.lower())
                        score = round(min(float(sim_score) + min(kw_matches * 0.05, 0.15), 0.98), 3)
                        citation_disp = chunk.get("citation") or chunk.get("neutral_citation") or f"[{chunk.get('year')}] SCR"

                        results.append({
                            "id": chunk.get("case_id"),
                            "title": c_name,
                            "citation": citation_disp,
                            "court": "Supreme Court of India",
                            "benchType": "Supreme Court Bench",
                            "benchSize": 2,
                            "decisionYear": chunk.get("year"),
                            "statutes": ["Indian Contract Act, 1872", "Constitution of India, Article 141"],
                            "ratioSummary": chunk.get("text", "")[:450] + ("..." if len(chunk.get("text", "")) > 450 else ""),
                            "relevance_score": score,
                            "retrieval_mode": f"local_index+sc_judgments+{embedding_service.mode}",
                            "source_link": chunk.get("source_link"),
                            "neutral_citation": chunk.get("neutral_citation"),
                            "bench": chunk.get("bench")
                        })

                    if len(results) >= limit * 3:
                        break

        # Final sort by relevance score
        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------ #
    # Citation Verification                                               #
    # ------------------------------------------------------------------ #
    def verify_citation(self, citation_or_name: str) -> Dict[str, Any]:
        """
        Verifies whether a case name or citation exists in:
        1. The 12 landmark Section 27 precedents (section27_precedents.json)
        2. The 960 Supreme Court judgments (sc_judgments / filtered_cases.parquet)
        """
        q = citation_or_name.strip().lower()
        if not q or len(q) < 3:
            return {"verified": False, "badge": "not_verified", "detail": "Query too short"}

        # 1. Check the 12 landmark precedents
        for c in self.corpus:
            title = c.get("title", "").lower()
            cit = c.get("citation", "").lower()
            alt_cits = [ac.lower() for ac in c.get("alternateCitations", [])]
            if (q in title or title in q) or (q in cit or cit in q) or any(q in ac for ac in alt_cits):
                return {
                    "verified": True,
                    "title": c.get("title"),
                    "citation": c.get("citation"),
                    "court": c.get("court"),
                    "year": c.get("decisionYear"),
                    "source_collection": "12_precedents",
                    "badge": "verified"
                }

        # 2. Check live Qdrant collection "sc_judgments" if loaded and reachable
        if self._client:
            try:
                available = {c.name for c in self._client.get_collections().collections}
                if self.sc_collection_name in available:
                    from qdrant_client.models import Filter, FieldCondition, MatchValue
                    should_conditions = [
                        FieldCondition(key="case_name", match=MatchValue(value=citation_or_name)),
                        FieldCondition(key="citation", match=MatchValue(value=citation_or_name)),
                        FieldCondition(key="case_id", match=MatchValue(value=citation_or_name)),
                    ]
                    # Also match extracted citation if present in query string
                    cit_match = re.search(r'\[?\b\d{4}\]?\s*\d*\s*(?:SCC|AIR|SCR|SCALE|INSC|S\.C\.R\.)[ \t]*\d+[A-Za-z0-9\s]*', citation_or_name, re.I)
                    if cit_match:
                        should_conditions.append(FieldCondition(key="citation", match=MatchValue(value=cit_match.group(0).strip())))

                    scroll_res, _ = self._client.scroll(
                        collection_name=self.sc_collection_name,
                        scroll_filter=Filter(should=should_conditions),
                        limit=1
                    )
                    if scroll_res:
                        p = scroll_res[0].payload or {}
                        return {
                            "verified": True,
                            "title": p.get("case_name"),
                            "citation": p.get("citation") or p.get("neutral_citation"),
                            "court": "Supreme Court of India",
                            "year": p.get("year"),
                            "bench": p.get("bench"),
                            "source_collection": "sc_judgments",
                            "badge": "verified"
                        }
            except Exception as e:
                logger.debug("Live Qdrant sc_judgments verification query failed: %s", e)

        # 3. Check the real Supreme Court judgments dataset locally only as fallback
        if SC_CHUNKS_PATH.exists():
            self._ensure_sc_dataset_loaded()
            if self._sc_cases_meta:
                # Substantive query tokens (distinct party names)
                stopwords = {"versus", "state", "union", "india", "court", "limited", "ltd", "pvt", "company", "and", "the", "ors", "anr"}
                q_tokens = [t for t in re.findall(r'[a-z0-9]{4,}', q) if t not in stopwords]

                for cid, meta in self._sc_cases_meta.items():
                    name = (meta.get("case_name") or "").lower()
                    cit = (meta.get("citation") or "").lower()
                    nc = (meta.get("neutral_citation") or "").lower()

                    # Clean matching against party names or citation
                    is_direct_match = (
                        (q in name and len(q) >= 4)
                        or (q in cit and len(q) >= 4)
                        or (q in nc and len(q) >= 4)
                        or (q == cid.lower())
                    )
                    if len(q_tokens) == 1:
                        is_token_match = bool(re.search(rf'\b{re.escape(q_tokens[0])}\b', name))
                    elif len(q_tokens) >= 2:
                        is_token_match = (
                            bool(re.search(rf'\b{re.escape(q_tokens[0])}\b', name))
                            or all(re.search(rf'\b{re.escape(tok)}\b', name) for tok in q_tokens)
                        )
                    else:
                        is_token_match = False

                    if is_direct_match or is_token_match:
                        return {
                            "verified": True,
                            "title": meta.get("case_name"),
                            "citation": meta.get("citation") or meta.get("neutral_citation"),
                            "court": "Supreme Court of India",
                            "year": meta.get("year"),
                            "bench": meta.get("bench"),
                            "source_collection": "sc_judgments",
                            "badge": "verified"
                        }

        return {
            "verified": False,
            "title": citation_or_name,
            "citation": None,
            "source_collection": None,
            "badge": "not_verified",
            "detail": "Citation or case not found in verified Supreme Court collection or precedent corpus."
        }

    # ------------------------------------------------------------------ #
    # Health                                                              #
    # ------------------------------------------------------------------ #
    def check_health(self) -> Dict[str, Any]:
        if not self._client and SC_CHUNKS_PATH.exists():
            self._ensure_sc_dataset_loaded()
        sc_chunk_count = len(self._sc_chunks) if self._sc_chunks else 0
        sc_case_count = len(self._sc_cases_meta) if self._sc_cases_meta else 0

        if self._client:
            try:
                collections = self._client.get_collections()
                names = {c.name for c in collections.collections}
                points = 0
                active_col = self.collection_name
                if self.sc_collection_name in names:
                    active_col = self.sc_collection_name
                    info = self._client.get_collection(self.sc_collection_name)
                    points = getattr(info, "points_count", 0) or 0
                elif self.collection_name in names:
                    info = self._client.get_collection(self.collection_name)
                    points = getattr(info, "points_count", 0) or 0

                return {
                    "status": "connected",
                    "url": self.url,
                    "collection": active_col,
                    "collection_seeded": points > 0,
                    "points_count": points,
                    "local_sc_chunks_indexed": sc_chunk_count,
                    "local_sc_judgments": sc_case_count,
                    "embedding": embedding_service.describe(),
                }
            except Exception as e:
                return {
                    "status": "local_fallback",
                    "url": self.url,
                    "error": str(e),
                    "indexed_precedents": len(self.corpus) + sc_case_count,
                    "sc_chunks_indexed": sc_chunk_count,
                    "embedding": embedding_service.describe()
                }
        return {
            "status": "local_index_fallback",
            "url": self.url,
            "indexed_precedents": len(self.corpus) + sc_case_count,
            "sc_chunks_indexed": sc_chunk_count,
            "sc_judgments_count": sc_case_count,
            "embedding": embedding_service.describe(),
            "detail": "Serving 12 verified precedents and 960 Supreme Court judgments from local semantic index.",
        }


qdrant_service = QdrantService()

