"""
JUSTICE Legal AI Backend — Search Router (/api/v1/search)
Executes dual-encoder HyDE (Hypothetical Document Embeddings) synthesis and hybrid vector search
grounded in Indian Supreme Court jurisprudence.
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging

from app.services.gemini_service import gemini_service
from app.services.qdrant_service import qdrant_service

logger = logging.getLogger("justice.router.search")
router = APIRouter(prefix="/api/v1", tags=["Universal Search"])

class SearchRequest(BaseModel):
    query: str = Field(..., description="Legal query or statutory issue (e.g., 'Section 27 non-compete enforceability')")
    court: Optional[str] = Field("ALL", description="Court filter: 'ALL', 'Supreme Court of India', 'Delhi High Court'")
    bench_type: Optional[str] = Field("ALL", description="Bench filter: 'ALL', 'CONSTITUTION', 'DIVISION'")
    enable_hyde: bool = Field(True, description="Whether to synthesize hypothetical ratio decidendi using gemini-3.8-flash")
    limit: int = Field(5, ge=1, le=50, description="Maximum number of precedents to return")

class SearchResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    query: str
    hyde_synthetic_ratio: Optional[str] = None
    model_used: str
    results_count: int
    results: List[Dict[str, Any]]

@router.post("/search", response_model=SearchResponse)
async def search_precedents_post(payload: SearchRequest):
    """
    POST /api/v1/search
    Synthesizes judicial holding via HyDE on gemini-3.8-flash, then conducts dense/sparse retrieval.
    """
    hyde_ratio = None
    if payload.enable_hyde:
        hyde_ratio = await gemini_service.generate_hyde_ratio(payload.query)

    search_query = f"{payload.query} {hyde_ratio}" if hyde_ratio else payload.query
    results = qdrant_service.search_precedents(
        query=search_query,
        court_filter=payload.court or "ALL",
        bench_filter=payload.bench_type or "ALL",
        limit=payload.limit
    )

    return SearchResponse(
        query=payload.query,
        hyde_synthetic_ratio=hyde_ratio,
        model_used="gemini-3.8-flash",
        results_count=len(results),
        results=results
    )

@router.get("/search", response_model=SearchResponse)
async def search_precedents_get(
    q: str = Query(..., description="Search query string"),
    court: str = Query("ALL", description="Court filter"),
    bench: str = Query("ALL", description="Bench filter"),
    enable_hyde: bool = Query(True, description="Enable HyDE with gemini-3.8-flash"),
    limit: int = Query(5, ge=1, le=50, description="Results limit")
):
    """
    GET /api/v1/search
    Convenience query-param endpoint for browser and quick REST querying.
    """
    req = SearchRequest(
        query=q,
        court=court,
        bench_type=bench,
        enable_hyde=enable_hyde,
        limit=limit
    )
    return await search_precedents_post(req)
