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
from app.services.gemini_service import gemini_service

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

@router.get("/citator/{case_id}", response_model=CitatorCaseResponse)
async def get_citator_case_by_id(case_id: str, include_ai: bool = Query(True, description="Synthesize Gemini 3.8 Flash Article 141 analysis")):
    """
    GET /api/v1/citator/{case_id}
    Retrieves full Article 141 precedent treatment tree, overruling risks,
    DAG graph lineage, and Gemini 3.8 Flash constitutional synthesis.
    """
    case_data = neo4j_service.get_citator_case(case_id)
    if not case_data:
        raise HTTPException(
            status_code=404,
            detail=f"Precedent '{case_id}' not found in Article 141 citation database."
        )

    hierarchy = neo4j_service.evaluate_article_141_hierarchy(
        bench_size=case_data.get("benchSize", 2),
        bench_type=case_data.get("benchType", "Division Bench")
    )

    ai_analysis = None
    if include_ai:
        ai_analysis = await gemini_service.generate_citator_analysis(case_data)

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
        aiAnalysis=ai_analysis
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
