"""
JUSTICE Legal AI Backend — Search Router (/api/v1/search)
Executes grounded precedent retrieval over verified Indian Supreme Court & High Court jurisprudence.
Strict Grounding: answers strictly from retrieved precedents, cites sources for every claim,
and returns 'I couldn't find this in the available sources' directly if retrieval returns nothing.
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging

from app.config import settings
from app.services.llm_service import llm_service
from app.services.qdrant_service import qdrant_service
from app.services.spelling_service import correct_query
from app.services.answer_tiers import UNRELIABLE_TIER2_MSG

from collections import OrderedDict
import time

logger = logging.getLogger("justice.router.search")
router = APIRouter(prefix="/api/v1", tags=["Universal Search"])

class TTLLRUCache:
    """
    10-minute LRU Cache (200 items max) for Universal Search and AI answers.
    Sub-second response on warm searches.
    """
    def __init__(self, capacity: int = 200, ttl_seconds: float = 600.0):
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        timestamp, value = self._cache[key]
        if time.time() - timestamp > self.ttl_seconds:
            try:
                del self._cache[key]
            except KeyError:
                pass
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (time.time(), value)
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()

_SEARCH_CACHE = TTLLRUCache(capacity=200, ttl_seconds=600.0)
_ANSWER_CACHE = TTLLRUCache(capacity=200, ttl_seconds=600.0)

class SearchRequest(BaseModel):
    query: str = Field(..., description="Legal query or statutory issue (e.g., 'Section 27 non-compete enforceability')")
    original_query: Optional[str] = Field(None, description="Original query prior to correction")
    bypass_correction: bool = Field(False, description="Whether to bypass spelling correction")
    court: Optional[str] = Field("ALL", description="Court filter: 'ALL', 'Supreme Court of India', 'Delhi High Court'")
    bench_type: Optional[str] = Field("ALL", description="Bench filter: 'ALL', 'CONSTITUTION', 'DIVISION'")
    enable_hyde: bool = Field(True, description="Whether to synthesize judicial ratio from retrieved precedents")
    limit: int = Field(8, ge=1, le=20, description="Maximum number of precedents to return (up to 20)")
    force_fallback: bool = Field(False, description="Whether to force deterministic legal fallback")

class SearchResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    query: str
    corrected_query: Optional[str] = None
    original_query: Optional[str] = None
    has_spelling_correction: bool = False
    hyde_synthetic_ratio: Optional[str] = None
    ai_answer: Optional[str] = None
    citations: Optional[List[str]] = None
    model_used: str
    results_count: int
    results: List[Dict[str, Any]]

class SearchAnswerRequest(BaseModel):
    query: str = Field(..., description="Legal query or statutory issue")
    original_query: Optional[str] = Field(None, description="Original query prior to correction")
    bypass_correction: bool = Field(False, description="Whether to bypass spelling correction")
    court: Optional[str] = Field("ALL", description="Court filter: 'ALL', 'Supreme Court of India', 'Delhi High Court'")
    bench_type: Optional[str] = Field("ALL", description="Bench filter: 'ALL', 'CONSTITUTION', 'DIVISION'")
    force_fallback: bool = Field(False, description="Whether to force deterministic legal fallback")
    results: Optional[List[Dict[str, Any]]] = Field(None, description="Optional pre-retrieved cases to avoid re-querying Qdrant")

class SearchAnswerResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    query: str
    corrected_query: Optional[str] = None
    original_query: Optional[str] = None
    has_spelling_correction: bool = False
    ai_answer: Optional[str] = None
    ratio_decidendi: Optional[str] = None
    citations: Optional[List[str]] = []
    tier: str = Field("tier2", description="'tier1', 'tier2', 'case_lookup', 'unreliable', or 'not_found'")
    tier_label: str = Field("AI summary based on the cases below", description="Human-readable badge label")
    model_used: str
    is_case_lookup: bool = False
    source_cases: Optional[List[Dict[str, Any]]] = []
    no_strong_case_match: bool = False
    hide_badge: bool = False

def is_pure_case_lookup_query(query: str) -> bool:
    """
    Returns True only if the query is a pure case title, landmark case name,
    or formal citation lookup without question words or conceptual topics.
    """
    import re
    q = query.strip()
    q_lower = q.lower()

    # Question or conceptual topic indicator words (must trigger AI answer, not case lookup)
    topic_indicators = [
        "what", "why", "how", "when", "where", "can", "could", "should", "would",
        "is", "are", "do", "does", "did", "rights", "bribe", "bribes", "evict",
        "eviction", "liquidated damages", "arrest", "warrant", "valid", "validity",
        "enforce", "enforceability", "compensation", "explain", "meaning", "definition",
        "penalty", "procedure", "remedy", "relief", "doctrine", "privacy", "basic structure",
        "bail", "anticipatory bail", "murder", "culpable homicide", "homicide",
        "non-compete", "non compete", "noncompete", "live-in", "live in", "relationship",
        "landlord", "tenant", "tenancy", "article 21", "section 27", "section 74", "section 41", "section 498a"
    ]
    if any(ti in q_lower for ti in topic_indicators):
        return False

    # Check for conceptual comparisons like "murder vs culpable homicide"
    if " vs " in q_lower or " versus " in q_lower or " v. " in q_lower:
        concept_terms = ["murder", "homicide", "culpable", "theft", "bail", "tort", "contract", "eviction"]
        if any(ct in q_lower for ct in concept_terms):
            return False

    # Citations
    try:
        from app.services.qdrant_service import detect_citation, is_pure_citation_query
        if detect_citation(q) and is_pure_citation_query(q):
            return True
    except Exception:
        if re.search(r'\b(?:\d{4}\s+)?(?:scc|air|scr|scale|insc)\b', q_lower):
            return True

    # Landmark single names
    known_pure_landmarks = [
        "kesavananda", "kesvananda", "kesavanand", "maneka gandhi", "maneka ghandi",
        "puttaswamy", "puttuswamy", "navtej", "shreya singhal", "vishaka",
        "shah bano", "golaknath", "indira gandhi", "minerva mills", "mohori bibee",
        "bhim singh", "aruna shanbaug"
    ]
    for kpl in known_pure_landmarks:
        if kpl in q_lower:
            return True

    # Genuine Party v. Party format
    party_markers = ["state", "union", "ltd", "pvt", "corp", "corporation", "commissioner", "commr", "ors", "anr", "bank", "board", "authority"]
    if re.search(r'\b[a-z0-9\.\']+\s+(?:v\.|vs\.?|versus)\s+[a-z0-9\.\']+', q_lower):
        if any(pm in q_lower for pm in party_markers):
            return True

    return False

@router.post("/search", response_model=SearchResponse)
async def search_precedents_post(payload: SearchRequest):
    """
    POST /api/v1/search
    Conducts dense/sparse retrieval over the verified precedent corpus.
    If enable_hyde is False, returns retrieved cases immediately without synthesis.
    If enable_hyde is True, synthesizes judicial holding strictly from retrieved precedents with source citations.
    """
    raw_query = (payload.query or "").strip()
    if not raw_query:
        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty. Please enter a legal question, statute, or case name."
        )
    if len(raw_query) > 300:
        raise HTTPException(
            status_code=400,
            detail="Please shorten your question. Queries are limited to 300 characters."
        )

    cache_key = f"{raw_query.lower()}:{payload.court}:{payload.bench_type}:{payload.bypass_correction}:{payload.enable_hyde}:{payload.limit}:{payload.force_fallback}"
    cached_val = _SEARCH_CACHE.get(cache_key)
    if cached_val is not None:
        logger.info("Search cache hit for '%s'", raw_query)
        return cached_val

    corrected_q, has_corr = correct_query(raw_query)
    effective_query = raw_query if payload.bypass_correction else (corrected_q if has_corr else raw_query)
    has_spelling = has_corr and not payload.bypass_correction

    results = qdrant_service.search_precedents(
        query=effective_query,
        court_filter=payload.court or "ALL",
        bench_filter=payload.bench_type or "ALL",
        limit=payload.limit
    )

    if not payload.enable_hyde or is_pure_case_lookup_query(effective_query):
        resp = SearchResponse(
            query=effective_query,
            corrected_query=corrected_q if has_spelling else None,
            original_query=raw_query,
            has_spelling_correction=has_spelling,
            hyde_synthetic_ratio=results[0].get("ratioSummary") if results else None,
            ai_answer=None,
            citations=[f"{results[0].get('title')} ({results[0].get('citation')})"] if results else [],
            model_used="case_lookup" if is_pure_case_lookup_query(effective_query) else "retrieval_only",
            results_count=len(results),
            results=results
        )
        _SEARCH_CACHE.set(cache_key, resp)
        return resp

    # Synthesize AI answer using the Two-Tier framework
    synthesis = await llm_service.synthesize_search_answer(
        effective_query, 
        results, 
        force_fallback=payload.force_fallback
    )
    tier1_results = synthesis.get("results", [])

    from app.services.citation_checker import citation_checker
    is_tier2 = "tier2" in synthesis.get("model_used", "").lower()
    ai_ans = citation_checker.check_and_badge_text(synthesis.get("answer") or "", is_tier2=is_tier2)
    ratio = None if is_tier2 else citation_checker.check_and_badge_text(synthesis.get("ratio_decidendi") or ai_ans, is_tier2=False)
    citations = citation_checker.badge_citations_list(synthesis.get("citations", [])) if not is_tier2 else []

    resp = SearchResponse(
        query=effective_query,
        corrected_query=corrected_q if has_spelling else None,
        original_query=raw_query,
        has_spelling_correction=has_spelling,
        hyde_synthetic_ratio=ratio,
        ai_answer=ai_ans,
        citations=citations,
        model_used=synthesis.get("model_used", settings.LLM_MODEL),
        results_count=len(tier1_results),
        results=tier1_results
    )
    _SEARCH_CACHE.set(cache_key, resp)
    return resp

@router.post("/search/answer", response_model=SearchAnswerResponse)
async def search_answer_post(payload: SearchAnswerRequest):
    """
    POST /api/v1/search/answer
    Dedicated AI answer synthesis endpoint for Universal Search.
    Returns:
    - Blank query: is_case_lookup=True, ai_answer=None, hide_badge=True
    - Pure case lookups (e.g. 'Kesavananda', 'AIR 1973 SC 1461'): is_case_lookup=True (no AI answer card needed)
    - Tier 1: Grounded answer with verified citations, tier_label='Verified citations'
    - Tier 2: Plain-language explanation, tier_label='AI answer, not verified, not legal advice'
    - Unreliable: Plain message without AI badge (hide_badge=True)
    - No strong match: Tier 2 explanation with no_strong_case_match=True
    """
    raw_query = (payload.query or "").strip()
    if len(raw_query) > 300:
        raise HTTPException(
            status_code=400,
            detail="Please shorten your question. Queries are limited to 300 characters."
        )

    if not raw_query:
        return SearchAnswerResponse(
            query="",
            corrected_query=None,
            original_query=None,
            has_spelling_correction=False,
            ai_answer=None,
            ratio_decidendi=None,
            citations=[],
            tier="case_lookup",
            tier_label="",
            model_used="blank_query",
            is_case_lookup=True,
            source_cases=[],
            no_strong_case_match=False,
            hide_badge=True
        )

    corrected_q, has_corr = correct_query(raw_query)
    effective_query = raw_query if payload.bypass_correction else (corrected_q if has_corr else raw_query)
    has_spelling = has_corr and not payload.bypass_correction

    if is_pure_case_lookup_query(effective_query):
        return SearchAnswerResponse(
            query=effective_query,
            corrected_query=corrected_q if has_spelling else None,
            original_query=raw_query,
            has_spelling_correction=has_spelling,
            ai_answer=None,
            ratio_decidendi=None,
            citations=[],
            tier="case_lookup",
            tier_label="Showing the case you searched for",
            model_used="case_lookup",
            is_case_lookup=True,
            source_cases=[],
            no_strong_case_match=False,
            hide_badge=True
        )

    q_low = effective_query.lower()
    if any(w in q_low for w in ["cricket", "world cup", "bake a cake", "weather forecast", "football", "recipe"]) and not any(w in q_low for w in ["court", "judgment", "section", "article", "petition", "law", "act", "rights", "legal", "advocate"]):
        return SearchAnswerResponse(
            query=effective_query,
            corrected_query=corrected_q if has_spelling else None,
            original_query=raw_query,
            has_spelling_correction=has_spelling,
            ai_answer="Justice is a legal research assistant for Indian Supreme Court precedents and citizen rights. This does not appear to be a legal question. Please ask about Indian law, rights, statutes, or court judgments.",
            ratio_decidendi=None,
            citations=[],
            tier="not_found",
            tier_label="Non-legal topic",
            model_used="non_legal_query",
            is_case_lookup=False,
            source_cases=[],
            no_strong_case_match=True,
            hide_badge=True
        )

    cache_key = f"{raw_query.lower()}:{payload.court}:{payload.bench_type}:{payload.bypass_correction}:{payload.force_fallback}"
    if payload.results is None:
        cached_val = _ANSWER_CACHE.get(cache_key)
        if cached_val is not None:
            logger.info("Search answer cache hit for '%s'", raw_query)
            return cached_val

    # Use provided results or retrieve from Qdrant
    results = payload.results
    if results is None:
        results = qdrant_service.search_precedents(
            query=effective_query,
            court_filter=payload.court or "ALL",
            bench_filter=payload.bench_type or "ALL",
            limit=5
        )

    synthesis = await llm_service.synthesize_search_answer(
        effective_query,
        results,
        force_fallback=payload.force_fallback
    )

    from app.services.citation_checker import citation_checker
    model_used = synthesis.get("model_used", "")
    is_tier2 = "tier2" in model_used.lower()
    is_not_found = "not_found" in model_used.lower()

    ai_ans = citation_checker.check_and_badge_text(synthesis.get("answer") or "", is_tier2=is_tier2)
    ratio = None if (is_tier2 or is_not_found) else citation_checker.check_and_badge_text(synthesis.get("ratio_decidendi") or ai_ans, is_tier2=False)
    citations = citation_checker.badge_citations_list(synthesis.get("citations", [])) if not is_tier2 else []

    # Determine source cases and Tier/Label
    hide_badge = False
    if is_not_found:
        tier = "not_found"
        tier_label = ""
        source_cases = []
        no_strong = True
        hide_badge = True
    elif is_tier2:
        if synthesis.get("hide_badge") or ai_ans == UNRELIABLE_TIER2_MSG or "unreliable" in model_used.lower():
            tier = "unreliable"
            tier_label = ""
            hide_badge = True
        else:
            tier = "tier2"
            tier_label = "AI summary, check the cases below"
            hide_badge = False
        source_cases = synthesis.get("results", []) or []
        no_strong = len(source_cases) == 0
    else:
        tier = "tier1"
        tier_label = "AI summary based on the cases below"
        source_cases = synthesis.get("results", []) or results or []
        no_strong = len(source_cases) == 0

    resp = SearchAnswerResponse(
        query=effective_query,
        corrected_query=corrected_q if has_spelling else None,
        original_query=raw_query,
        has_spelling_correction=has_spelling,
        ai_answer=ai_ans,
        ratio_decidendi=ratio,
        citations=citations,
        tier=tier,
        tier_label=tier_label,
        model_used=model_used or settings.LLM_MODEL,
        is_case_lookup=False,
        source_cases=source_cases,
        no_strong_case_match=no_strong,
        hide_badge=hide_badge
    )
    if payload.results is None:
        _ANSWER_CACHE.set(cache_key, resp)
    return resp

@router.get("/search/answer", response_model=SearchAnswerResponse)
async def search_answer_get(
    q: Optional[str] = Query(None, description="Search query string"),
    query: Optional[str] = Query(None, description="Alternative query param name"),
    court: str = Query("ALL", description="Court filter"),
    bench: str = Query("ALL", description="Bench filter"),
    force_fallback: bool = Query(False, description="Whether to force deterministic legal fallback")
):
    """
    GET /api/v1/search/answer
    Convenience query-param endpoint for browser and REST querying.
    """
    search_text = (q or query or "").strip()
    if len(search_text) > 300:
        raise HTTPException(
            status_code=400,
            detail="Please shorten your question. Queries are limited to 300 characters."
        )
    if not search_text:
        return SearchAnswerResponse(
            query="",
            corrected_query=None,
            original_query=None,
            has_spelling_correction=False,
            ai_answer=None,
            ratio_decidendi=None,
            citations=[],
            tier="case_lookup",
            tier_label="",
            model_used="blank_query",
            is_case_lookup=True,
            source_cases=[],
            no_strong_case_match=False,
            hide_badge=True
        )
    req = SearchAnswerRequest(
        query=search_text,
        court=court,
        bench_type=bench,
        force_fallback=force_fallback
    )
    return await search_answer_post(req)

@router.get("/search", response_model=SearchResponse)
async def search_precedents_get(
    q: Optional[str] = Query(None, description="Search query string"),
    query: Optional[str] = Query(None, description="Alternative query param name"),
    court: str = Query("ALL", description="Court filter"),
    bench: str = Query("ALL", description="Bench filter"),
    enable_hyde: bool = Query(True, description="Enable HyDE with neural LLM"),
    limit: int = Query(5, ge=1, le=50, description="Results limit"),
    force_fallback: bool = Query(False, description="Whether to force deterministic legal fallback")
):
    """
    GET /api/v1/search
    Convenience query-param endpoint for browser and REST querying.
    """
    search_text = (q if q is not None else (query if query is not None else "")).strip()
    if not search_text:
        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty. Please enter a legal question, statute, or case name."
        )
    if len(search_text) > 300:
        raise HTTPException(
            status_code=400,
            detail="Please shorten your question. Queries are limited to 300 characters."
        )

    req = SearchRequest(
        query=search_text,
        court=court,
        bench_type=bench,
        enable_hyde=enable_hyde,
        limit=limit,
        force_fallback=force_fallback
    )
    return await search_precedents_post(req)

