"""
JUSTICE Legal AI Backend — Citator Router (/api/v1/citator/{case_id})
Computes Article 141 constitutional precedence hierarchy, treatment lineages,
and citation DAG traversal graphs.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging

from app.services.neo4j_service import neo4j_service
from app.services.llm_service import llm_service

logger = logging.getLogger("justice.router.citator")
router = APIRouter(prefix="/api/v1", tags=["Smart Citator & Article 141 Hierarchy"])

class TreatmentItem(BaseModel):
    case: str
    year: int
    court: str
    treatment: str
    note: str

class Article141Rule(BaseModel):
    level: str
    jurisdiction: str
    status: str

class Article141Hierarchy(BaseModel):
    targetBenchSize: int
    targetBenchType: str
    rules: List[Article141Rule]

class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    bench: int

class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: str

class CitatorCaseResponse(BaseModel):
    id: str
    title: str
    citation: str
    court: str
    benchType: str
    benchSize: int
    decisionYear: int
    status: str
    statusLabel: str
    citationCount: int
    statusDescription: str
    treatmentHistory: List[TreatmentItem]
    article141Evaluation: Article141Hierarchy
    graphNodes: List[GraphNode]
    graphEdges: List[GraphEdge]
    dataSource: Optional[str] = None
    aiAnalysis: Optional[Dict[str, Any]] = None
    citations: Optional[List[str]] = None

@router.get("/citator/verify-citation", response_model=Dict[str, Any])
async def verify_citation_endpoint(q: str = Query(..., description="Citation or case name to verify")):
    """
    GET /api/v1/citator/verify-citation?q={citation_or_case_name}
    Verifies whether a case citation or party name exists in the verified precedent collection
    (12 Section 27 landmark precedents or 960 Supreme Court of India judgments).
    """
    from app.services.qdrant_service import qdrant_service
    return qdrant_service.verify_citation(q)

@router.get("/citator/{case_id}", response_model=CitatorCaseResponse)
async def get_citator_case_by_id(case_id: str, include_ai: bool = Query(True, description="Synthesize Article 141 analysis")):
    """
    GET /api/v1/citator/{case_id}
    Retrieves full Article 141 precedent treatment tree, overruling risks,
    DAG graph lineage, and grounded constitutional synthesis.
    """
    case_data = neo4j_service.get_citator_case(case_id)
    if not case_data:
        from app.services.qdrant_service import qdrant_service
        q_case = qdrant_service.get_case_by_id(case_id)
        if not q_case:
            from app.routers.casechat import get_case_record
            q_case = get_case_record(case_id)
        if not q_case:
            raise HTTPException(
                status_code=404,
                detail=f"Case '{case_id}' was not found in the verified dataset."
            )

        bench_size = q_case.get("benchSize", 2)
        bench_type = q_case.get("benchType") or ("Constitution Bench" if bench_size >= 5 else "Division Bench")
        case_data = {
            "id": case_id,
            "title": q_case.get("title", case_id),
            "citation": q_case.get("citation", "Citation pending"),
            "court": q_case.get("court", "Supreme Court of India"),
            "benchType": bench_type,
            "benchSize": bench_size,
            "decisionYear": q_case.get("decisionYear") or q_case.get("year"),
            "status": "GREEN",
            "statusLabel": "RECORDED JUDGMENT (SUPREME COURT)",
            "citationCount": 0,
            "statusDescription": "citation graph not available for this case",
            "overruledCases": [],
            "treatmentHistory": [],
            "precedentChain": [f"{q_case.get('title', case_id)} ({q_case.get('citation', '')})"],
            "dataSource": "qdrant_dataset"
        }

    hierarchy = neo4j_service.evaluate_article_141_hierarchy(
        bench_size=case_data.get("benchSize", 2),
        bench_type=case_data.get("benchType", "Division Bench")
    )

    ai_analysis = None
    source_citation = f"{case_data.get('title')} ({case_data.get('citation')})"
    citations_list = [source_citation]
    from app.services.citation_checker import citation_checker
    if include_ai:
        ai_analysis = await llm_service.generate_citator_analysis(case_data)
        if ai_analysis:
            for f in ["constitutional_standing", "bench_strength_assessment", "overruling_risk", "article_141_doctrine", "executive_summary"]:
                if f in ai_analysis and isinstance(ai_analysis[f], str):
                    ai_analysis[f] = citation_checker.check_and_badge_text(ai_analysis[f], is_tier2=False)
            if ai_analysis.get("citations"):
                ai_analysis["citations"] = citation_checker.badge_citations_list(ai_analysis["citations"])
                citations_list = ai_analysis["citations"]

    citations_list = citation_checker.badge_citations_list(citations_list)

    return CitatorCaseResponse(
        id=case_data["id"],
        title=case_data["title"],
        citation=case_data["citation"],
        court=case_data["court"],
        benchType=case_data["benchType"],
        benchSize=case_data["benchSize"],
        decisionYear=case_data["decisionYear"],
        status=case_data["status"],
        statusLabel=case_data["statusLabel"],
        citationCount=case_data.get("citationCount", 0),
        statusDescription=case_data["statusDescription"],
        treatmentHistory=case_data.get("treatmentHistory", []),
        article141Evaluation=hierarchy,
        graphNodes=case_data.get("graphNodes", []),
        graphEdges=case_data.get("graphEdges", []),
        dataSource=case_data.get("dataSource", "in_memory_fallback"),
        aiAnalysis=ai_analysis,
        citations=citations_list
    )

@router.get("/citator", response_model=List[Dict[str, Any]])
async def list_available_citator_precedents():
    """
    GET /api/v1/citator
    Returns summary metadata for landmark precedents currently indexed in the knowledge graph.
    """
    from app.services.neo4j_service import ARTICLE_141_GRAPH_DATA
    summaries = []
    for k, v in ARTICLE_141_GRAPH_DATA.items():
        summaries.append({
            "id": v["id"],
            "title": v["title"],
            "citation": v["citation"],
            "court": v["court"],
            "benchSize": v["benchSize"],
            "benchType": v["benchType"],
            "status": v["status"],
            "statusLabel": v["statusLabel"]
        })
    return summaries
