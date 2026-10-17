"""
JUSTICE Legal AI Backend — Legal Maxims Router
Provides comprehensive Latin Legal Maxims reference for law students and practitioners.
Endpoints:
- GET /api/v1/maxims (search, category, letter, pagination)
- GET /api/v1/maxims/{id}
- GET /api/v1/maxims/random (maxim of the day, stable per calendar date)
- POST /api/v1/maxims/explain (grounded Gemini explanation for maxim or fact scenario)
"""

import os
import json
import hashlib
import logging
from datetime import date
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.gemini_service import gemini_service
from app.config import settings

logger = logging.getLogger("justice.maxims")

router = APIRouter(prefix="/api/v1/maxims", tags=["Legal Maxims"])

# Load maxims from backend/data/maxims.json
DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "maxims.json"

_MAXIMS_CACHE: List[Dict[str, Any]] = []
_MAXIMS_BY_ID: Dict[str, Dict[str, Any]] = {}

def _load_maxims() -> List[Dict[str, Any]]:
    global _MAXIMS_CACHE, _MAXIMS_BY_ID
    if not _MAXIMS_CACHE and DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                _MAXIMS_CACHE = json.load(f)
                _MAXIMS_BY_ID = {m["id"]: m for m in _MAXIMS_CACHE}
            logger.info(f"Loaded {len(_MAXIMS_CACHE)} legal maxims into memory.")
        except Exception as e:
            logger.error(f"Failed to load maxims from {DATA_FILE}: {e}")
    return _MAXIMS_CACHE

# Initialize cache
_load_maxims()


# Schemas
class MaximExplainRequest(BaseModel):
    maxim: Optional[str] = Field(None, description="Latin maxim or English keyword")
    id: Optional[str] = Field(None, description="Exact maxim ID if known")
    fact_situation: Optional[str] = Field(None, description="Optional real-world facts to apply the maxim to")


@router.get("", response_model=Dict[str, Any])
async def list_maxims(
    q: Optional[str] = Query(None, description="Search term in Latin maxim, meaning, or explanation"),
    category: Optional[str] = Query(None, description="Filter by legal category (e.g. Constitutional, Criminal, Contract)"),
    letter: Optional[str] = Query(None, description="Single starting letter of Latin maxim (A-Z)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(25, ge=1, le=250, description="Items per page")
):
    """
    Search and filter Latin Legal Maxims with pagination, category filter, and A-Z indexing.
    """
    maxims = _load_maxims()
    filtered = maxims

    # Category filter
    if category and category.lower() != "all":
        cat_lower = category.lower().strip()
        filtered = [m for m in filtered if m.get("category", "").lower() == cat_lower]

    # Letter filter (A-Z)
    if letter and len(letter.strip()) == 1:
        char = letter.strip().lower()
        filtered = [m for m in filtered if m.get("maxim", "").strip().lower().startswith(char)]

    # Search filter
    if q and q.strip():
        terms = q.strip().lower().split()
        filtered = [
            m for m in filtered
            if any(
                term in m.get("maxim", "").lower()
                or term in m.get("meaning", "").lower()
                or term in m.get("explanation", "").lower()
                for term in terms
            )
        ]

    # Calculate pagination
    total = len(filtered)
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    page_results = filtered[start_idx:end_idx]

    # Distinct categories for chips
    categories = sorted(list({m.get("category", "General") for m in maxims if m.get("category")}))

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total > 0 else 1,
        "categories": ["All"] + categories,
        "results": page_results
    }


@router.get("/random", response_model=Dict[str, Any])
async def get_random_maxim_of_the_day(
    target_date: Optional[str] = Query(None, description="Specific date YYYY-MM-DD for stable lookups")
):
    """
    Returns the Maxim of the Day, deterministically stable per calendar date.
    """
    maxims = _load_maxims()
    if not maxims:
        raise HTTPException(status_code=500, detail="Legal maxims dataset is empty")

    date_str = target_date or date.today().isoformat()
    # Compute deterministic integer hash from date string
    hash_val = int(hashlib.md5(date_str.encode("utf-8")).hexdigest(), 16)
    index = hash_val % len(maxims)

    selected = maxims[index]
    return {
        "date": date_str,
        "maxim": selected
    }


@router.get("/{maxim_id}", response_model=Dict[str, Any])
async def get_maxim_by_id(maxim_id: str):
    """
    Retrieve full details for a specific legal maxim by ID.
    """
    _load_maxims()
    maxim = _MAXIMS_BY_ID.get(maxim_id)
    if not maxim:
        # Try case-insensitive lookup
        for m in _MAXIMS_CACHE:
            if m["id"].lower() == maxim_id.lower():
                return m
        raise HTTPException(status_code=404, detail=f"Legal maxim with ID '{maxim_id}' not found.")
    return maxim


@router.post("/explain", response_model=Dict[str, Any])
async def explain_maxim(req: MaximExplainRequest):
    """
    Takes a maxim identifier or query and optional fact situation.
    Uses Gemini service to explain it in simple, student-friendly language,
    grounded strictly in the verified stored entry.
    """
    maxims = _load_maxims()
    target_entry = None

    # 1. Match by ID (exact or partial slug)
    if req.id:
        target_entry = _MAXIMS_BY_ID.get(req.id)
        if not target_entry:
            clean_id = req.id.strip().lower()
            for m in maxims:
                m_id = m["id"].lower()
                if m_id == clean_id or clean_id in m_id or m_id in clean_id:
                    target_entry = m
                    break

    # 2. Match by Latin query
    if not target_entry and req.maxim:
        query_clean = req.maxim.strip().lower()
        # Direct exact match
        for m in maxims:
            if m["maxim"].lower() == query_clean or m["id"].lower() == query_clean:
                target_entry = m
                break
        
        # Substring match if exact match not found
        if not target_entry:
            for m in maxims:
                if query_clean in m["maxim"].lower() or query_clean in m["meaning"].lower():
                    target_entry = m
                    break

    # Accuracy constraint: if not in data, say so rather than making it up
    if not target_entry:
        return {
            "found": False,
            "message": f"The legal maxim '{req.maxim or req.id}' is not in the verified legal maxims corpus. Under strict accuracy rules, explanations are only generated for verified maxims.",
            "query": req.maxim or req.id,
            "explanation": None,
            "application_to_facts": None,
            "model_used": "corpus_not_found"
        }

    # Generate grounded explanation using Gemini service if active
    stored_maxim = target_entry["maxim"]
    stored_meaning = target_entry["meaning"]
    stored_explanation = target_entry["explanation"]
    stored_example = target_entry.get("example", "")
    stored_category = target_entry.get("category", "")
    stored_cases = target_entry.get("indian_case_refs", [])

    prompt_context = (
        f"Grounded Maxim: {stored_maxim}\n"
        f"Literal Meaning: {stored_meaning}\n"
        f"Legal Category: {stored_category}\n"
        f"Verified Explanation: {stored_explanation}\n"
        f"Standard Example: {stored_example}\n"
        f"Verified Indian Cases: {json.dumps(stored_cases)}\n"
    )

    if req.fact_situation:
        prompt_context += f"\nUser's Fact Situation: {req.fact_situation.strip()}\n"

    system_instruction = (
        "You are a distinguished legal educator explaining Latin legal maxims to Indian law students and lawyers. "
        "Explain the maxim in calm, simple, and precise terms. "
        "CRITICAL RULE: You must ground your answer strictly in the provided verified maxim details. "
        "Do not invent fictitious case citations or ungrounded principles. "
        "If a fact situation is provided, analyze how this specific maxim applies to those facts."
    )

    explanation_text = stored_explanation
    application_text = None
    used_gemini = False

    if gemini_service.is_active and gemini_service.client:
        try:
            from google.genai import types
            prompt = (
                f"{prompt_context}\n\n"
                f"Please provide:\n"
                f"1. A simple 2-sentence explanation of this maxim for law students.\n"
                f"2. {'How this maxim applies to the user fact situation.' if req.fact_situation else 'A 1-sentence key takeaway.'}"
            )
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                max_output_tokens=500
            )
            response = gemini_service.client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=config
            )
            if response.text:
                explanation_text = response.text.strip()
                used_gemini = True
        except Exception as e:
            logger.warning(f"Gemini explanation for maxim {stored_maxim} failed: {e}. Using stored baseline.")

    if req.fact_situation:
        application_text = (
            f"Applying {stored_maxim} ({stored_meaning}): Under the principle that {stored_explanation.split('.')[0]}, "
            f"the factual scenario involves an assessment of whether the rights or obligations contemplated by the maxim were adhered to."
        )

    return {
        "found": True,
        "id": target_entry["id"],
        "maxim": stored_maxim,
        "meaning": stored_meaning,
        "category": stored_category,
        "explanation": explanation_text,
        "application_to_facts": application_text,
        "stored_example": stored_example,
        "indian_case_refs": stored_cases,
        "related_maxims": target_entry.get("related_maxims", []),
        "model_used": settings.GEMINI_MODEL if used_gemini else "stored_corpus_baseline"
    }


@router.post("/{maxim_id}/explain", response_model=Dict[str, Any])
async def explain_maxim_path(maxim_id: str, req: Optional[MaximExplainRequest] = None):
    """Path-based convenience endpoint for explaining a legal maxim by slug."""
    payload = req or MaximExplainRequest(id=maxim_id)
    if not payload.id:
        payload.id = maxim_id
    return await explain_maxim(payload)
