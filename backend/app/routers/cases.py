"""
JUSTICE Legal AI Backend — Cases Router (/api/v1/cases)
Provides full collection search across all 1,740+ Supreme Court & High Court precedents,
with stable case IDs and detailed record retrieval for Precedent Comparison & Doctrine Matrix.
"""

import re
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from app.services.qdrant_service import (
    qdrant_service,
    normalize_citation,
    clean_judgment_text,
    extract_statutes_from_text,
    SEARCH_STOPWORDS
)
from app.routers.casechat import (
    _init_case_data,
    _CASE_METADATA_INDEX,
    get_case_record
)

logger = logging.getLogger("justice.router.cases")
router = APIRouter(prefix="/api/v1/cases", tags=["Case Precedents Collection & Comparison"])

# Dual-mount aliases on /api/cases as well
alias_router = APIRouter(prefix="/api/cases", tags=["Case Precedents Collection & Comparison"])


class CaseListItem(BaseModel):
    id: str
    title: str
    citation: Optional[str] = ""
    court: Optional[str] = "Supreme Court of India"
    decisionYear: Optional[int] = None
    benchSize: Optional[int] = None
    benchType: Optional[str] = None
    statutes: List[str] = Field(default_factory=list)
    ratioSummary: Optional[str] = ""


class CaseSearchResponse(BaseModel):
    total: int
    query: str
    cases: List[CaseListItem]


class CaseDetailResponse(BaseModel):
    id: str
    title: str
    citation: Optional[str] = ""
    court: Optional[str] = "Supreme Court of India"
    decisionYear: Optional[int] = None
    benchSize: Optional[int] = None
    benchType: Optional[str] = None
    leadJudge: Optional[str] = None
    statutes: List[str] = Field(default_factory=list)
    ratioSummary: Optional[str] = ""
    ratioLabel: Optional[str] = "RATIO DECIDENDI / LEGAL PRINCIPLE"
    holding: Optional[str] = None
    overruledCases: List[str] = Field(default_factory=list)
    treatmentHistory: List[Dict[str, Any]] = Field(default_factory=list)
    text: Optional[str] = None


def _search_full_case_collection(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Searches across all records available to the application:
    1. Verified Precedent Corpus & Tenancy Precedents (section27_precedents.json)
    2. Landmark SC Cases (landmark_chunks.json)
    3. Entire SC Judgments Metadata Index (1,740+ cases from chunks.json & citizen_rights_chunks.json)
    
    Supports:
    - Full case name
    - Partial name (e.g. 'Dhanapal', 'Atma Ram', 'Babu', 'Maneka', 'Niranjan')
    - Formal citation (e.g. 'AIR 1979 SC 1745', '[1975] 3 S.C.R. 1', '(2006) 4 SCC 227')
    - Decision Year
    - Statutory keywords
    """
    _init_case_data()
    q = (query or "").strip()
    q_low = q.lower()
    q_norm = normalize_citation(q) if q else ""
    q_tokens = [t for t in re.findall(r'[a-zA-Z0-9]{2,}', q_low) if t not in SEARCH_STOPWORDS]

    scored_cases: List[tuple[float, str, Dict[str, Any]]] = []
    seen_ids = set()

    # Pre-index cases list from corpus first (to give high priority to hand-verified precedents)
    corpus_cases = qdrant_service.corpus or []
    for c in corpus_cases:
        cid = c.get("id") or c.get("case_id")
        if not cid:
            continue
        seen_ids.add(cid.lower())
        title = (c.get("title") or "").strip()
        cit = (c.get("citation") or "").strip()
        year_str = str(c.get("decisionYear") or c.get("year") or "")
        statutes_str = " ".join(c.get("statutes", [])).lower()
        alt_cits = " ".join(c.get("altCitations", [])).lower()

        if not q:
            # Blank query: return initial landmark collection
            scored_cases.append((100.0, cid, c))
            continue

        score = 0.0
        # 1. Exact ID match
        if q_low == cid.lower():
            score += 200.0

        # 2. Exact citation match
        cit_norm = normalize_citation(cit)
        if q_norm and (q_norm == cit_norm or (len(q_norm) >= 4 and q_norm in cit_norm)):
            score += 150.0
        elif q_low in cit.lower() or q_low in alt_cits:
            score += 100.0

        # 3. Exact Title match or Substring
        title_low = title.lower()
        if q_low == title_low:
            score += 180.0
        elif q_low in title_low:
            score += 90.0

        # 4. Token overlap in title
        if q_tokens:
            matched_tokens = sum(1 for t in q_tokens if t in title_low)
            if matched_tokens == len(q_tokens):
                score += 80.0
            elif matched_tokens > 0:
                score += (matched_tokens / len(q_tokens)) * 50.0

        # 5. Year match
        if q == year_str:
            score += 40.0

        # 6. Statute match
        if q_low in statutes_str:
            score += 30.0

        if score > 0:
            scored_cases.append((score, cid, c))

    # Search remaining cases from _CASE_METADATA_INDEX
    for cid, c in _CASE_METADATA_INDEX.items():
        cid_clean = str(cid).strip()
        if cid_clean.lower() in seen_ids:
            continue

        title = (c.get("title") or c.get("case_name") or c.get("common_name") or "").strip()
        cit = (c.get("citation") or c.get("neutral_citation") or "").strip()
        year_str = str(c.get("year") or c.get("decisionYear") or "")
        statutes_str = " ".join(c.get("statutes", [])).lower()

        if not q:
            continue

        score = 0.0
        # 1. Exact ID match
        if q_low == cid_clean.lower():
            score += 200.0

        # 2. Citation match
        cit_norm = normalize_citation(cit)
        if q_norm and (q_norm == cit_norm or (len(q_norm) >= 4 and q_norm in cit_norm)):
            score += 120.0
        elif q_low in cit.lower():
            score += 80.0

        # 3. Title match
        title_low = title.lower()
        if q_low == title_low:
            score += 150.0
        elif q_low in title_low:
            score += 70.0

        # 4. Token overlap
        if q_tokens:
            matched_tokens = sum(1 for t in q_tokens if t in title_low)
            if matched_tokens == len(q_tokens):
                score += 60.0
            elif matched_tokens > 0:
                score += (matched_tokens / len(q_tokens)) * 35.0

        # 5. Year match
        if q == year_str:
            score += 30.0

        # 6. Statute match
        if q_low in statutes_str:
            score += 20.0

        if score > 0:
            seen_ids.add(cid_clean.lower())
            scored_cases.append((score, cid_clean, c))

    # Sort descending by score, tie-break by year descending
    scored_cases.sort(key=lambda x: (x[0], x[2].get("decisionYear") or x[2].get("year") or 0), reverse=True)
    return [item[2] for item in scored_cases[:limit]]


def _normalize_case_record(raw: Dict[str, Any], case_id: str) -> Dict[str, Any]:
    """Ensures consistent, honest fields across landmark and non-landmark cases."""
    cid = raw.get("id") or raw.get("case_id") or case_id
    title = raw.get("title") or raw.get("common_name") or raw.get("case_name") or cid
    citation = raw.get("citation") or raw.get("neutral_citation") or ""
    court = raw.get("court") or "Supreme Court of India"
    year = raw.get("decisionYear") or raw.get("year")

    # Bench details
    bench_size = raw.get("benchSize")
    bench_type = raw.get("benchType")
    if not bench_size:
        bench_str = raw.get("bench") or ""
        if bench_str:
            judges_list = [j.strip() for j in re.split(r'[,;&]|\band\b', bench_str) if j.strip()]
            bench_size = len(judges_list) if len(judges_list) > 0 else None
    if not bench_type and bench_size:
        bench_type = "Constitution Bench" if bench_size >= 5 else ("Division Bench" if bench_size == 2 else f"{bench_size}-Judge Bench")

    # Statutes
    statutes = list(raw.get("statutes", []))
    if not statutes and raw.get("text"):
        statutes = extract_statutes_from_text(raw.get("text", ""))

    # Ratio Summary / Holding
    ratio_summary = raw.get("ratioSummary") or raw.get("holding")
    if not ratio_summary and raw.get("text"):
        cleaned = clean_judgment_text(raw.get("text", ""))
        ratio_summary = cleaned[:350] + ("..." if len(cleaned) > 350 else "")

    return {
        "id": cid,
        "title": title,
        "citation": citation,
        "court": court,
        "decisionYear": year,
        "benchSize": bench_size,
        "benchType": bench_type,
        "leadJudge": raw.get("leadJudge"),
        "statutes": statutes,
        "ratioSummary": ratio_summary or "Ratio summary not recorded in available archive",
        "ratioLabel": raw.get("ratioLabel") or "RATIO DECIDENDI / LEGAL PRINCIPLE",
        "holding": raw.get("holding") or ratio_summary,
        "overruledCases": raw.get("overruledCases") or [],
        "treatmentHistory": raw.get("treatmentHistory") or [],
        "text": raw.get("text")
    }


@router.get("/search", response_model=CaseSearchResponse)
@alias_router.get("/search", response_model=CaseSearchResponse)
async def search_cases_endpoint(
    q: str = Query("", description="Case title, party name, partial name, citation, statute, or year"),
    limit: int = Query(20, ge=1, le=50, description="Maximum number of cases to return")
):
    """
    GET /api/v1/cases/search?q={query}&limit={limit}
    Searches across all 1,740+ available cases in the repository collection.
    Matches party names, partial names, citations, years, and statutes.
    Returns lightweight search hits for Precedent Comparison searchable case pickers.
    """
    raw_results = _search_full_case_collection(q, limit=limit)
    cases = []
    for r in raw_results:
        cid = r.get("id") or r.get("case_id") or ""
        normalized = _normalize_case_record(r, cid)
        cases.append(CaseListItem(
            id=normalized["id"],
            title=normalized["title"],
            citation=normalized["citation"],
            court=normalized["court"],
            decisionYear=normalized["decisionYear"],
            benchSize=normalized["benchSize"],
            benchType=normalized["benchType"],
            statutes=normalized["statutes"],
            ratioSummary=normalized["ratioSummary"]
        ))
    return CaseSearchResponse(
        total=len(cases),
        query=q,
        cases=cases
    )


@router.get("/{case_id}", response_model=CaseDetailResponse)
@alias_router.get("/{case_id}", response_model=CaseDetailResponse)
async def get_case_by_id_endpoint(case_id: str):
    """
    GET /api/v1/cases/{case_id}
    Retrieves the complete source record for a case by its stable ID.
    Used for Precedent Comparison and Doctrine Matrix analysis.
    Works for any case in the corpus, SC dataset, or Qdrant collection.
    """
    cid = case_id.strip()
    if not cid:
        raise HTTPException(status_code=400, detail="Case ID cannot be empty.")

    # 1. Check Qdrant service get_case_by_id
    raw_case = qdrant_service.get_case_by_id(cid)
    if not raw_case:
        # 2. Check casechat metadata index
        raw_case = get_case_record(cid)

    if not raw_case:
        raise HTTPException(
            status_code=404,
            detail=f"Case '{cid}' was not found in the verified dataset. I couldn't find a verified source for this."
        )

    normalized = _normalize_case_record(raw_case, cid)
    return CaseDetailResponse(**normalized)
