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

@router.post("/search", response_model=SearchResponse)
async def search_precedents_post(payload: SearchRequest):
    """
    POST /api/v1/search
    Conducts dense/sparse retrieval over the verified precedent corpus.
    If retrieval returns nothing, skips the model and answers 'I couldn't find this in the available sources'.
    Otherwise synthesizes judicial holding strictly from retrieved precedents with source citations.
    """
    results = qdrant_service.search_precedents(
        query=payload.query,
        court_filter=payload.court or "ALL",
        bench_filter=payload.bench_type or "ALL",
        limit=payload.limit
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
