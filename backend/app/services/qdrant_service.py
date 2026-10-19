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
import os
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


TOPIC_DEFINITIONS = {
    "arrest_detention": {
        "phrases": [
            "police custody", "custodial", "illegal detention", "unlawful detention",
            "without a warrant", "without warrant", "arrest warrant", "right to be informed",
            "produce before magistrate", "police arrest", "remand to custody", "judicial custody",
            "statutory bail", "default bail", "anticipatory bail", "grounds of arrest",
            "article 22"
        ],
        "words": [
            "arrest", "detention", "remand", "bail", "warrant", "handcuff", "handcuffing", "custody"
        ]
    },
    "police_misconduct": {
        "phrases": [
            "police excesses", "custodial death", "custodial torture", "police atrocities",
            "compensation for police", "police violence", "police brutality", "torture in custody",
            "fake encounter", "third degree", "custodial violence"
        ],
        "words": [
            "torture", "atrocities", "excesses", "encounter"
        ]
    },
    "bribery_corruption": {
        "phrases": [
            "prevention of corruption act", "illegal gratification", "demand and acceptance",
            "public servant", "trap case", "asking for a bribe", "anti-corruption", "take a bribe",
            "pay a bribe"
        ],
        "words": [
            "bribe", "bribery", "corruption", "gratification"
        ]
    },
    "housing_tenancy": {
        "phrases": [
            "rent control", "unlawful ejectment", "evict without notice", "evict me",
            "landlord and tenant", "tenant protection", "rent control act", "ejectment of tenant",
            "landlord evict", "fixation of fair rent"
        ],
        "words": [
            "tenant", "eviction", "evict", "landlord", "tenancy", "ejectment", "rent"
        ]
    },
    "traffic_police_powers": {
        "phrases": [
            "motor vehicles act", "search and seizure", "stop and search", "search vehicle",
            "stopped on my bike", "stopped by police", "traffic police", "issue challan",
            "impound vehicle", "traffic violation", "seizure of vehicle", "power to stop",
            "stopped on bike", "traffic cop"
        ],
        "words": [
            "challan", "traffic", "bike", "motorcycle", "scooter", "vehicle"
        ]
    },
    "fundamental_rights": {
        "phrases": [
            "article 21", "right to life", "personal liberty", "right to life and personal liberty",
            "article 19", "freedom of speech", "fundamental rights", "reasonable restrictions",
            "fundamental right", "habeas corpus", "right to privacy", "article 14"
        ],
        "words": [
            "fundamental"
        ]
    }
}

SEARCH_STOPWORDS = {
    "what", "to", "do", "if", "a", "an", "the", "in", "on", "of", "and", "or", "for", "with", "is", "are", "can",
    "my", "me", "you", "your", "by", "under", "without", "when", "how", "why", "who", "whom", "which", "where",
    "about", "tell", "show", "give", "explain", "law", "legal", "court", "judgment", "matter", "case", "state",
    "india", "act", "acts", "section", "sections", "rule", "rules", "rights", "powers", "this", "that", "these",
    "those", "from", "into", "over", "than", "then", "also", "any", "all", "its", "been", "being", "having",
    "guidelines", "remedies", "protection"
}


def classify_query_topic(query: str) -> Optional[str]:
    """Classifies a user query into one of the 6 citizen rights topics or returns None."""
    q_lower = query.lower()
    scores = {}
    for topic, config in TOPIC_DEFINITIONS.items():
        score = 0.0
        for phrase in config["phrases"]:
            if phrase in q_lower:
                score += 3.0
        for word in config["words"]:
            if re.search(r"\b" + re.escape(word) + r"\b", q_lower):
                score += 1.0
        if score > 0:
            scores[topic] = score
    if scores:
        best_topic, best_score = max(scores.items(), key=lambda x: x[1])
        if best_score >= 1.0:
            return best_topic
    return None


def extract_substantive_terms(query: str) -> List[str]:
    """Extracts substantive content words and section numbers from query, excluding generic stopwords."""
    tokens = re.findall(r"[a-zA-Z]{3,}|\b\d+\b", query.lower())
    return [t for t in tokens if t not in SEARCH_STOPWORDS]


def extract_query_aliases(query: str) -> List[str]:
    """
    Identifies if a query contains an alias, short name, or citation of a landmark case,
    ignoring punctuation and spacing (e.g. 'AIR 1973 SC 1461', '(1973) 4 SCC 225', 'Kesavananda').
    Returns matching canonical alias strings for Qdrant filtering.
    """
    if not query or len(query.strip()) < 3:
        return []

    q_norm = re.sub(r'[\s\W_]+', '', query).lower()
    matched = []

    try:
        from app.ingest.landmark_pipeline import LANDMARK_CASES
    except Exception:
        LANDMARK_CASES = []

    for case_def in LANDMARK_CASES:
        all_aliases = [
            case_def["common_name"],
            case_def["short_name"],
            f"{case_def['short_name']} case",
            f"{case_def['common_name']} case",
        ] + case_def.get("extra_aliases", [])

        for a in all_aliases:
            if not a:
                continue
            a_norm = re.sub(r'[\s\W_]+', '', a).lower()
            if len(a_norm) >= 4 and a_norm in q_norm:
                matched.append(a)

    return list(dict.fromkeys(matched))


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
        """Loads and caches chunks and dense vectors from the SC dataset if local indexing is active."""
        if self._sc_loaded:
            return
        self._sc_loaded = True

        # Render & Production RAM Protection:
        # Never load the 33k-vector local dataset into RAM on Render (512MB RAM free-tier limit),
        # or when Qdrant Cloud is configured. The deployed app queries Qdrant Cloud directly.
        # If Qdrant Cloud is unreachable, it gracefully falls back to the lightweight 12-precedent
        # landmark corpus (<1MB RAM) and Tier 2 AI explanations without triggering an OOM kill.
        if (
            os.getenv("RENDER")
            or os.getenv("DISABLE_LOCAL_SC_DATASET", "").lower() in ("true", "1")
            or (self._client and os.getenv("LOAD_LOCAL_SC_INDEX", "false").lower() not in ("true", "1"))
        ):
            logger.info(
                "Skipping local SC dataset loading into RAM (conserving memory for Render; "
                "using Qdrant Cloud with graceful 12-precedent fallback)."
            )
            return

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

        # Small exact-match boost for landmark aliases and citations
        exact_boost_results: List[Dict[str, Any]] = []
        matched_aliases = extract_query_aliases(query)
        if matched_aliases:
            try:
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                conditions = [FieldCondition(key="aliases", match=MatchValue(value=a)) for a in matched_aliases]
                boost_hits, _ = self._client.scroll(
                    collection_name=target_collection,
                    scroll_filter=Filter(should=conditions),
                    limit=limit,
                    with_payload=True,
                    with_vectors=False
                )
                seen_boost = set()
                for hit in boost_hits:
                    p = dict(hit.payload or {})
                    if not self._matches_filters(p, court_filter, bench_filter):
                        continue
                    c_title = p.get("common_name") or p.get("case_name") or p.get("title")
                    c_key = (c_title or "").strip().lower()
                    if not c_key or c_key in seen_boost:
                        continue
                    seen_boost.add(c_key)

                    p["title"] = c_title
                    p["decisionYear"] = p.get("year")
                    p["ratioSummary"] = p.get("text", "")[:450] + ("..." if len(p.get("text", "")) > 450 else "")
                    p["court"] = "Supreme Court of India"
                    p["benchType"] = "Supreme Court Bench"
                    p["benchSize"] = p.get("benchSize", 5 if p.get("landmark") else 2)
                    p["statutes"] = p.get("statutes", ["Constitution of India", "Supreme Court of India Jurisprudence"])
                    p["relevance_score"] = 0.99
                    p["retrieval_mode"] = f"qdrant_exact_boost+{target_collection}"
                    exact_boost_results.append(p)
                    if len(exact_boost_results) >= limit:
                        break
            except Exception as e:
                logger.debug("Exact match boost failed: %s", e)

        topic = classify_query_topic(query)
        substantive_terms = extract_substantive_terms(query)

        from qdrant_client.models import Filter, FieldCondition, MatchValue
        hits = []

        # 1. Topic-filtered retrieval if a citizen rights topic is detected
        if topic:
            try:
                topic_filter = Filter(must=[FieldCondition(key="topic", match=MatchValue(value=topic))])
                topic_hits = self._client.search(
                    collection_name=target_collection,
                    query_vector=vector,
                    query_filter=topic_filter,
                    limit=25
                )
                hits.extend(topic_hits)
            except Exception as e:
                logger.debug("Topic filtered search failed: %s", e)

        # Also get general hits across the collection to merge and re-rank top candidates
        general_hits = self._client.search(
            collection_name=target_collection,
            query_vector=vector,
            limit=25
        )
        hits.extend(general_hits)

        # Deduplicate hits by point ID
        unique_hits = []
        seen_hit_ids = set()
        for h in hits:
            if h.id not in seen_hit_ids:
                seen_hit_ids.add(h.id)
                unique_hits.append(h)

        # 2. Re-rank candidates combining vector score, topic match, and key-term overlap
        candidates = []

        # (a) First evaluate verified landmark precedents from self.corpus (e.g. Kailash Nath, Percept D'Mark, Puttaswamy)
        corpus_vecs = self._get_corpus_vectors()
        norm_v = math.sqrt(sum(q * q for q in vector)) or 1.0
        for case_item, c_vec in zip(self.corpus, corpus_vecs):
            c_copy = dict(case_item)
            if not self._matches_filters(c_copy, court_filter, bench_filter):
                continue

            dot = sum(q * c for q, c in zip(vector, c_vec))
            norm_c = math.sqrt(sum(c * c for c in c_vec)) or 1.0
            cos_sim = dot / (norm_v * norm_c)

            c_title = c_copy.get("title", "")
            c_text = f"{c_title} {c_copy.get('citation', '')} {c_copy.get('ratioSummary', '')} {' '.join(c_copy.get('statutes', []))} {' '.join(c_copy.get('keywords', []))}".lower()
            t_matches = sum(1 for t in substantive_terms if t in c_title.lower())
            tx_matches = sum(1 for t in substantive_terms if t in c_text)
            t_ratio = (tx_matches / max(len(substantive_terms), 1)) if substantive_terms else 1.0
            t_boost = min(0.35, t_matches * 0.15 + t_ratio * 0.15)
            c_keywords = [k.lower() for k in c_copy.get("keywords", [])]
            kw_matches = sum(1 for k in c_keywords if k in query.lower())
            landmark_boost = min(0.35, kw_matches * 0.15)
            c_comb_score = cos_sim + t_boost + landmark_boost + 0.15

            if (cos_sim >= 0.45) or (cos_sim >= 0.35 and (len(substantive_terms) == 0 or tx_matches > 0)):
                c_copy["relevance_score"] = round(float(c_comb_score), 3)
                c_copy["raw_vector_score"] = round(float(cos_sim), 3)
                c_copy["retrieval_mode"] = f"qdrant+verified_precedents+{embedding_service.mode}"
                candidates.append(c_copy)

        # (b) Evaluate Qdrant cloud hits
        for hit in unique_hits:
            case = dict(hit.payload or {})

            # Populate standard case fields BEFORE _matches_filters so court/bench filters don't drop valid SC cases
            if case.get("common_name"):
                case["title"] = case.get("common_name")
            elif not case.get("title") and case.get("case_name"):
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
                case["statutes"] = ["Constitution of India", "Supreme Court of India Jurisprudence"]

            if not self._matches_filters(case, court_filter, bench_filter):
                continue

            case_name = case.get("case_name") or case.get("title") or ""
            text = case.get("text") or case.get("ratioSummary") or ""
            comb_text = f"{case_name} {text}".lower()
            name_lower = case_name.lower()

            v_score = float(hit.score)

            # Topic match boost:
            if topic:
                case_topic = case.get("topic")
                if case_topic == topic:
                    topic_boost = 0.20
                elif case_topic is None:
                    topic_boost = -0.15
                else:
                    topic_boost = 0.0
            else:
                topic_boost = 0.0

            # Key-term overlap in case title and headnote:
            title_matches = sum(1 for t in substantive_terms if t in name_lower)
            text_matches = sum(1 for t in substantive_terms if t in comb_text)
            term_ratio = (text_matches / max(len(substantive_terms), 1)) if substantive_terms else 1.0
            term_boost = min(0.35, title_matches * 0.15 + term_ratio * 0.15)

            combined_score = v_score + topic_boost + term_boost

            # 3. Relevance Floor:
            if v_score < 0.40:
                continue
            if combined_score < 0.50:
                continue
            if substantive_terms and text_matches == 0:
                continue

            # Specific everyday-rights filter for vehicle/bike stops:
            if "bike" in substantive_terms:
                has_bike = any(bt in comb_text for bt in ["bike", "motorcycle", "scooter", "two-wheeler", "two wheeler"])
                has_stop = any(st in comb_text for st in ["stop", "stopped", "police", "challan", "search", "seizure", "inspection", "officer"])
                if not (has_bike and has_stop):
                    continue

            case["relevance_score"] = round(float(combined_score), 3)
            case["raw_vector_score"] = round(float(v_score), 3)
            case["retrieval_mode"] = f"qdrant+{target_collection}+{embedding_service.mode}"
            candidates.append(case)

        # Re-rank by combined score descending
        candidates.sort(key=lambda x: x["relevance_score"], reverse=True)

        # Prepend exact match boost results and deduplicate
        results: List[Dict[str, Any]] = list(exact_boost_results)
        seen_cases = set()
        for r in exact_boost_results:
            for k in [r.get("title"), r.get("case_name"), r.get("common_name")]:
                if k:
                    seen_cases.add(k.strip().lower())

        seen_parties = []
        max_to_return = max(limit, 3)
        for c in candidates:
            title_key = (c.get("title") or "").strip().lower()
            if title_key and title_key in seen_cases:
                continue
            party_tokens = set(re.findall(r'[a-z]{4,}', title_key)) - {
                "versus", "state", "union", "india", "court", "limited", "authority", "corporation", "company"
            }
            if party_tokens and any(len(party_tokens & prev) >= 2 for prev in seen_parties):
                continue
            if title_key:
                seen_cases.add(title_key)
                if party_tokens:
                    seen_parties.append(party_tokens)
            results.append(c)
            if len(results) >= max_to_return:
                break

        return results[:limit]

    def _search_local(self, query: str, court_filter: str, bench_filter: str, limit: int) -> List[Dict[str, Any]]:
        query_vec = embedding_service.embed_query(query)
        corpus_vecs = self._get_corpus_vectors()
        norm_q = math.sqrt(sum(q * q for q in query_vec)) or 1.0

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

        self._ensure_sc_dataset_loaded()
        if self._sc_vectors is not None and self._sc_chunks:
            q_arr = np.array(query_vec, dtype=np.float32)
            q_arr_norm = q_arr / (np.linalg.norm(q_arr) or 1.0)

            sims = np.dot(self._sc_vectors, q_arr_norm)
            candidate_indices = np.where(sims >= 0.30)[0]

            if len(candidate_indices) > 0:
                top_order = candidate_indices[np.argsort(sims[candidate_indices])[::-1]]
                seen_cases = {r.get("title", "").lower() for r in results}

                for idx in top_order:
                    chunk = self._sc_chunks[idx]
                    c_name = chunk.get("case_name", "").strip()
                    if not c_name or c_name.lower() in seen_cases:
                        continue

                    c_text_lower = (c_name + " " + chunk.get("text", "")).lower()
                    kw_matches = sum(1 for t in terms if t in c_text_lower)
                    sim_score = float(sims[idx])

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

        matched_aliases = extract_query_aliases(query)
        if matched_aliases:
            landmark_chunks_file = SC_DATASET_DIR / "chunks" / "landmark_chunks.json"
            if landmark_chunks_file.exists():
                try:
                    with open(landmark_chunks_file, "r", encoding="utf-8") as f:
                        l_chunks = json.load(f)
                    seen_boost = {r.get("title", "").strip().lower() for r in results}
                    for lc in l_chunks:
                        c_title = lc.get("common_name") or lc.get("case_name")
                        c_key = (c_title or "").strip().lower()
                        if not c_key or c_key in seen_boost:
                            continue
                        lc_aliases = [re.sub(r'[\s\W_]+', '', a).lower() for a in lc.get("aliases", [])]
                        if any(re.sub(r'[\s\W_]+', '', ma).lower() in lc_aliases for ma in matched_aliases):
                            seen_boost.add(c_key)
                            results.insert(0, {
                                "id": lc.get("case_id"),
                                "title": c_title,
                                "citation": lc.get("citation") or lc.get("neutral_citation") or f"[{lc.get('year')}] SCR",
                                "court": "Supreme Court of India",
                                "benchType": "Supreme Court Bench",
                                "benchSize": 5,
                                "decisionYear": lc.get("year"),
                                "statutes": ["Constitution of India", "Indian Precedents"],
                                "ratioSummary": lc.get("text", "")[:450] + ("..." if len(lc.get("text", "")) > 450 else ""),
                                "relevance_score": 0.99,
                                "retrieval_mode": f"local_exact_boost+landmark_cases+{embedding_service.mode}",
                                "source_link": lc.get("source_link"),
                                "neutral_citation": lc.get("neutral_citation"),
                                "bench": lc.get("bench")
                            })
                except Exception as e:
                    logger.debug("Local landmark boost failed: %s", e)

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
            alt_cits = [ac.lower() for ac in (c.get("altCitations") or c.get("alternateCitations") or [])]
            if (q in title or title in q) or (q in cit or cit in q) or any(q in ac or ac in q for ac in alt_cits):
                return {
                    "verified": True,
                    "title": c.get("title"),
                    "citation": c.get("citation"),
                    "court": c.get("court"),
                    "year": c.get("decisionYear"),
                    "source_collection": "12_precedents",
                    "badge": "verified"
                }

            # Distinct landmark keywords (e.g. Golikari, Puttaswamy, Kailash Nath, Percept D'Mark, Dawoodi Bohra)
            c_keywords = [k.lower() for k in c.get("keywords", [])]
            if any(k in q for k in c_keywords):
                return {
                    "verified": True,
                    "title": c.get("title"),
                    "citation": c.get("citation"),
                    "court": c.get("court"),
                    "year": c.get("decisionYear"),
                    "source_collection": "12_precedents",
                    "badge": "verified"
                }

            # Normalized title check (ignoring "the", punctuation, spacing)
            norm_q = re.sub(r'[^a-z0-9]', '', re.sub(r'\bthe\b', '', q))
            norm_title = re.sub(r'[^a-z0-9]', '', re.sub(r'\bthe\b', '', title))
            if norm_q and (norm_q in norm_title or norm_title in norm_q):
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

