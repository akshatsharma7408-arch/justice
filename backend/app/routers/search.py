"""
JUSTICE Legal AI Backend — Search Router (/api/v1/search)
Executes grounded precedent retrieval over verified Indian Supreme Court & High Court jurisprudence.
Strict Grounding: answers strictly from retrieved precedents, cites sources for every claim,
and returns 'I couldn't find this in the available sources' directly if retrieval returns nothing.
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging

from app.config import settings
from app.services.llm_service import llm_service
from app.services.qdrant_service import qdrant_service

logger = logging.getLogger("justice.router.search")
router = APIRouter(prefix="/api/v1", tags=["Universal Search"])

class SearchRequest(BaseModel):
    query: str = Field(..., description="Legal query or statutory issue (e.g., 'Section 27 non-compete enforceability')")
    court: Optional[str] = Field("ALL", description="Court filter: 'ALL', 'Supreme Court of India', 'Delhi High Court'")
    bench_type: Optional[str] = Field("ALL", description="Bench filter: 'ALL', 'CONSTITUTION', 'DIVISION'")
    enable_hyde: bool = Field(True, description="Whether to synthesize judicial ratio from retrieved precedents")
    limit: int = Field(5, ge=1, le=50, description="Maximum number of precedents to return")
    force_fallback: bool = Field(False, description="Whether to force deterministic legal fallback")

class SearchResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    query: str
    hyde_synthetic_ratio: Optional[str] = None
    ai_answer: Optional[str] = None
    citations: Optional[List[str]] = None
    model_used: str
    results_count: int
    results: List[Dict[str, Any]]

class SearchAnswerRequest(BaseModel):
    query: str = Field(..., description="Legal query or statutory issue")
    court: Optional[str] = Field("ALL", description="Court filter: 'ALL', 'Supreme Court of India', 'Delhi High Court'")
    bench_type: Optional[str] = Field("ALL", description="Bench filter: 'ALL', 'CONSTITUTION', 'DIVISION'")
    force_fallback: bool = Field(False, description="Whether to force deterministic legal fallback")
    results: Optional[List[Dict[str, Any]]] = Field(None, description="Optional pre-retrieved cases to avoid re-querying Qdrant")

class SearchAnswerResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    query: str
    ai_answer: Optional[str] = None
    ratio_decidendi: Optional[str] = None
    citations: Optional[List[str]] = []
    tier: str = Field("tier2", description="'tier1', 'tier2', 'case_lookup', or 'not_found'")
    tier_label: str = Field("AI answer, not verified, not legal advice", description="Human-readable badge label")
    model_used: str
    is_case_lookup: bool = False
    source_cases: Optional[List[Dict[str, Any]]] = []
    no_strong_case_match: bool = False

def is_pure_case_lookup_query(query: str) -> bool:
    """
    Returns True only if the query is a pure case title, landmark case name,
    or formal citation lookup without question words or conceptual topics.
    """
    import re
    q = query.strip()
    q_lower = q.lower()

    # Question or topic indicator words
    topic_indicators = [
        "what", "why", "how", "when", "where", "can", "could", "should", "would",
        "is", "are", "do", "does", "did", "rights", "bribe", "bribes", "evict",
        "eviction", "liquidated damages", "arrest", "warrant", "valid", "validity",
        "enforce", "enforceability", "compensation", "explain", "meaning", "definition",
        "penalty", "procedure", "remedy", "relief", "doctrine"
    ]
    words = re.findall(r'[a-zA-Z0-9]+', q_lower)
    if any(ti in words for ti in topic_indicators):
        return False

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

    # Citations
    try:
        from app.services.qdrant_service import detect_citation, is_pure_citation_query
        if detect_citation(q) and is_pure_citation_query(q):
            return True
    except Exception:
        if re.search(r'\b(?:\d{4}\s+)?(?:scc|air|scr|scale|insc)\b', q_lower):
            return True

    # Party v. Party format
    if re.search(r'\b[a-z0-9\.\']+\s+(?:v\.|vs\.?|versus)\s+[a-z0-9\.\']+', q_lower):
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
    results = qdrant_service.search_precedents(
        query=payload.query,
        court_filter=payload.court or "ALL",
        bench_filter=payload.bench_type or "ALL",
        limit=payload.limit
    )

    if not payload.enable_hyde or is_pure_case_lookup_query(payload.query):
        return SearchResponse(
            query=payload.query,
            hyde_synthetic_ratio=results[0].get("ratioSummary") if results else None,
            ai_answer=None,
            citations=[f"{results[0].get('title')} ({results[0].get('citation')})"] if results else [],
            model_used="case_lookup" if is_pure_case_lookup_query(payload.query) else "retrieval_only",
            results_count=len(results),
            results=results
        )

    # Synthesize AI answer using the Two-Tier framework
    synthesis = await llm_service.synthesize_search_answer(
        payload.query, 
        results, 
        force_fallback=payload.force_fallback
    )
    tier1_results = synthesis.get("results", [])

    from app.services.citation_checker import citation_checker
    is_tier2 = "tier2" in synthesis.get("model_used", "").lower()
    ai_ans = citation_checker.check_and_badge_text(synthesis.get("answer") or "", is_tier2=is_tier2)
    ratio = citation_checker.check_and_badge_text(synthesis.get("ratio_decidendi") or ai_ans, is_tier2=is_tier2)
    citations = citation_checker.badge_citations_list(synthesis.get("citations", [])) if not is_tier2 else []

    return SearchResponse(
        query=payload.query,
        hyde_synthetic_ratio=ratio,
        ai_answer=ai_ans,
        citations=citations,
        model_used=synthesis.get("model_used", settings.LLM_MODEL),
        results_count=len(tier1_results),
        results=tier1_results
    )

@router.post("/search/answer", response_model=SearchAnswerResponse)
async def search_answer_post(payload: SearchAnswerRequest):
    """
    POST /api/v1/search/answer
    Dedicated AI answer synthesis endpoint for Universal Search.
    Returns:
    - Pure case lookups (e.g. 'Kesavananda', 'AIR 1973 SC 1461'): is_case_lookup=True (no AI answer card needed)
    - Tier 1: Grounded answer with verified citations, tier_label='Verified citations'
    - Tier 2: Plain-language explanation, tier_label='AI answer, not verified, not legal advice'
    - No strong match: Tier 2 explanation with no_strong_case_match=True
    """
    if is_pure_case_lookup_query(payload.query):
        return SearchAnswerResponse(
            query=payload.query,
            ai_answer=None,
            ratio_decidendi=None,
            citations=[],
            tier="case_lookup",
            tier_label="Showing the case you searched for",
            model_used="case_lookup",
            is_case_lookup=True,
            source_cases=[],
            no_strong_case_match=False
        )

    # Use provided results or retrieve from Qdrant
    results = payload.results
    if results is None:
        results = qdrant_service.search_precedents(
            query=payload.query,
            court_filter=payload.court or "ALL",
            bench_filter=payload.bench_type or "ALL",
            limit=5
        )

    synthesis = await llm_service.synthesize_search_answer(
        payload.query,
        results,
        force_fallback=payload.force_fallback
    )

    from app.services.citation_checker import citation_checker
    model_used = synthesis.get("model_used", "")
    is_tier2 = "tier2" in model_used.lower()
    is_not_found = "not_found" in model_used.lower()

    ai_ans = citation_checker.check_and_badge_text(synthesis.get("answer") or "", is_tier2=is_tier2)
    ratio = citation_checker.check_and_badge_text(synthesis.get("ratio_decidendi") or ai_ans, is_tier2=is_tier2)
    citations = citation_checker.badge_citations_list(synthesis.get("citations", [])) if not is_tier2 else []

    # Determine source cases and Tier/Label
    if is_not_found:
        tier = "not_found"
        tier_label = "AI answer, not verified"
        source_cases = []
        no_strong = True
    elif is_tier2:
        tier = "tier2"
        tier_label = "AI answer, not verified"
        source_cases = synthesis.get("results", []) or []
        no_strong = len(source_cases) == 0
    else:
        tier = "tier1"
        tier_label = "Verified citations"
        source_cases = synthesis.get("results", []) or results or []
        no_strong = len(source_cases) == 0

    return SearchAnswerResponse(
        query=payload.query,
        ai_answer=ai_ans,
        ratio_decidendi=ratio,
        citations=citations,
        tier=tier,
        tier_label=tier_label,
        model_used=model_used or settings.LLM_MODEL,
        is_case_lookup=False,
        source_cases=source_cases,
        no_strong_case_match=no_strong
    )

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
    search_text = q or query or "Section 27 non-compete"
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
    search_text = q or query or "Section 27 non-compete"
    req = SearchRequest(
        query=search_text,
        court=court,
        bench_type=bench,
        enable_hyde=enable_hyde,
        limit=limit,
        force_fallback=force_fallback
    )
    return await search_precedents_post(req)

