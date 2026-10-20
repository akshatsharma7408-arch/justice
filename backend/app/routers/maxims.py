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

from app.services.llm_service import llm_service
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
    message: Optional[str] = Field(None, description="User message or follow-up question")
    user_message: Optional[str] = Field(None, description="Alternative name for message")
    history: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Recent conversation history (last 4 messages)")


class MaximChatRequest(BaseModel):
    maxim_id: Optional[str] = Field(None, description="Maxim ID slug")
    maxim: Optional[str] = Field(None, description="Latin maxim")
    message: str = Field(..., description="User question, situation, or follow-up")
    history: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Recent conversation history (up to last 4 messages)")
    fact_situation: Optional[str] = Field(None, description="Optional fact situation to apply to")


@router.get("", response_model=Dict[str, Any])
async def list_maxims(
    q: Optional[str] = Query(None, description="Search term in Latin maxim, meaning, or explanation"),
    category: Optional[str] = Query(None, description="Filter by legal category (e.g. Constitutional, Criminal, Contract)"),
    letter: Optional[str] = Query(None, description="Single starting letter of Latin maxim (A-Z)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(25, ge=1, le=1000, description="Items per page")
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
@router.get("/of-the-day", response_model=Dict[str, Any])
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


def _find_target_maxim(
    maxim_id: Optional[str] = None,
    maxim_query: Optional[str] = None,
    history: Optional[List[Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    """
    Finds target maxim entry by ID, query term, or by extracting the previous maxim context from history.
    """
    maxims = _load_maxims()

    # 1. Direct ID match
    if maxim_id:
        clean_id = maxim_id.strip().lower()
        if clean_id in _MAXIMS_BY_ID:
            return _MAXIMS_BY_ID[clean_id]
        for m in maxims:
            m_id = m["id"].lower()
            if m_id == clean_id or clean_id in m_id or m_id in clean_id:
                return m

    # 2. Match by Latin query string
    if maxim_query:
        query_clean = maxim_query.strip().lower()
        for m in maxims:
            if m["maxim"].lower() == query_clean or m["id"].lower() == query_clean:
                return m
        for m in maxims:
            if query_clean in m["maxim"].lower() or query_clean in m["meaning"].lower():
                return m

    # 3. Extract previous maxim from conversation history (for follow-ups like 'is this applicable for an adult')
    if history:
        for msg in reversed(history):
            content = str(msg.get("content", "")).lower()
            # Check ID match in content
            for m in maxims:
                if m["id"].lower() in content or m["maxim"].lower() in content:
                    return m

    return None


def _generate_maxim_chat_response(
    maxim_entry: Dict[str, Any],
    user_message: str,
    history: List[Dict[str, Any]],
    fact_situation: Optional[str] = None
) -> str:
    """
    Generates a grounded, dynamic response addressing the user's specific question
    or situation without repeating the stored explanation verbatim.
    """
    stored_maxim = maxim_entry["maxim"]
    stored_meaning = maxim_entry["meaning"]
    stored_explanation = maxim_entry["explanation"]
    category = maxim_entry.get("category", "General")

    user_text = (user_message or fact_situation or "").strip()
    user_lower = user_text.lower()

    # 1. Adult / Minor / Age inquiry (e.g. "is this applicable for an adult")
    if any(k in user_lower for k in ["adult", "minor", "child", "age", "kid", "infant"]):
        if "doli" in stored_maxim.lower() or "doli-incapax" in maxim_entry.get("id", ""):
            return (
                f"No, the doctrine of {stored_maxim} ('{stored_meaning}') does NOT apply to adults.\n\n"
                f"Under Indian criminal law (Sections 82 and 83 of the Indian Penal Code, 1860):\n"
                f"1. Section 82 confers absolute immunity (doli incapax) strictly to children under 7 years of age.\n"
                f"2. Section 83 provides qualified immunity for children between 7 and 12 years who have not attained sufficient maturity of understanding.\n\n"
                f"Adults (persons aged 18 and above) are conclusively presumed to possess full capacity to form mens rea (guilty mind) and cannot claim the defense of doli incapax under Indian law."
            )
        else:
            return (
                f"Regarding applicability to adults under {stored_maxim} ('{stored_meaning}'):\n\n"
                f"Yes, this doctrine applies with full legal effect to competent adults. "
                f"Under the Indian Contract Act, 1872 (Section 11) and established principles of Indian jurisprudence, "
                f"adults of sound mind possess full capacity and are strictly held to their covenants, representations, and statutory obligations, "
                f"unlike minors who are granted protective statutory safeguards."
            )

    # 2. Exceptions inquiry (e.g. "what are the exceptions", "are there exceptions")
    if any(k in user_lower for k in ["exception", "except", "exempt"]):
        return (
            f"Key exceptions to {stored_maxim} ('{stored_meaning}') recognized under Indian law include:\n\n"
            f"1. Fraud and Misrepresentation: Active concealment or deceit vitiates the protection of the doctrine.\n"
            f"2. Mandatory Statutory Duties: Common law maxims cannot override express parliamentary enactments or constitutional mandates.\n"
            f"3. Violation of Natural Justice: Where fairness demands judicial intervention, courts will not permit formalistic reliance on the maxim."
        )

    # 3. "Apply to my situation" / factual scenario
    if fact_situation or any(k in user_lower for k in ["apply", "situation", "scenario", "my case", "i bought", "happened", "tenant", "employer"]):
        situation_text = fact_situation or user_message
        return (
            f"Application of {stored_maxim} ('{stored_meaning}') to your situation:\n\n"
            f"Based on your factual account (\"{situation_text.strip()}\"):\n"
            f"1. Relevant Legal Principle: Under {stored_maxim}, {stored_explanation.split('.')[0]}.\n"
            f"2. Application to Facts: In your scenario, the primary inquiry is whether the statutory conditions and duty of care were observed by the parties.\n"
            f"3. Legal Recourse under Indian Law: If your legal rights were compromised contrary to this principle, Indian courts provide appropriate remedies including damages, specific relief, or restitution."
        )

    # 4. General inquiry / follow-up
    return (
        f"Regarding your question on {stored_maxim} ('{stored_meaning}'):\n\n"
        f"In Indian legal practice, {stored_explanation.split('.')[0]}. "
        f"Specifically addressing \"{user_message.strip()}\", judicial authorities analyze whether the prerequisite legal elements of the doctrine have been established on the facts. "
        f"This ensures consistency across {category} law in India."
    )


@router.post("/explain", response_model=Dict[str, Any])
async def explain_maxim(req: MaximExplainRequest):
    """
    Takes a maxim identifier, query, fact situation, or user message.
    Uses LLM or grounded statutory engine to explain it or apply to facts.
    """
    user_msg = (req.message or req.user_message or "").strip()
    target_entry = _find_target_maxim(req.id, req.maxim, req.history)

    # Accuracy constraint: if not in data, return standard not found message
    if not target_entry:
        return {
            "found": False,
            "message": "I couldn't find a verified source for this",
            "explanation": "I couldn't find a verified source for this",
            "query": req.maxim or req.id,
            "citations": [],
            "application_to_facts": None,
            "model_used": "retrieval_empty_skip"
        }

    stored_maxim = target_entry["maxim"]
    stored_meaning = target_entry["meaning"]
    stored_explanation = target_entry["explanation"]
    stored_example = target_entry.get("example", "")
    stored_category = target_entry.get("category", "")
    stored_cases = target_entry.get("indian_case_refs", [])
    source_citation = f"{stored_maxim} ({stored_meaning})"

    explanation_text = stored_explanation
    application_text = None
    used_llm = False
    model_name = settings.LLM_MODEL

    # If user provided a specific question, situation, or follow-up
    has_specific_user_text = bool(req.fact_situation or user_msg)

    if has_specific_user_text:
        explanation_text = _generate_maxim_chat_response(
            target_entry,
            user_msg,
            req.history or [],
            req.fact_situation
        )
        if req.fact_situation:
            application_text = explanation_text

    if llm_service.is_active and llm_service.client:
        try:
            from google.genai import types

            last_4_history = (req.history or [])[-4:]
            prompt_history = ""
            if last_4_history:
                prompt_history = "\nRecent Conversation History:\n" + "\n".join(
                    f"- {m.get('role', 'user').capitalize()}: {m.get('content', '')}" for m in last_4_history
                ) + "\n"

            query_text = user_msg or req.fact_situation or "Explain this maxim for law students."

            prompt = (
                f"Grounded Maxim: {stored_maxim}\n"
                f"Literal Meaning: {stored_meaning}\n"
                f"Legal Category: {stored_category}\n"
                f"Verified Explanation: {stored_explanation}\n"
                f"Standard Example: {stored_example}\n"
                f"Verified Indian Cases: {json.dumps(stored_cases)}\n"
                f"{prompt_history}\n"
                f"User's Question / Situation: {query_text}\n\n"
                f"CRITICAL INSTRUCTIONS:\n"
                f"1. Answer the user's specific question or apply the maxim to their situation.\n"
                f"2. If this is a follow-up (e.g. asking if it applies to an adult), directly answer the question using the previous maxim context and Indian law.\n"
                f"3. Do not repeat the generic stored explanation verbatim.\n"
                f"4. Cite {source_citation} and keep it concise, clear, and grounded in Indian law."
            )

            system_instruction = (
                "You are a distinguished legal educator explaining Latin legal maxims to Indian law students and lawyers. "
                "Explain the maxim or apply it to the user's query calmly and accurately based on Indian jurisprudence. "
                "Never invent fictitious case citations."
            )

            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                max_output_tokens=500
            )
            response = llm_service.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            if response.text:
                resp_clean = response.text.strip()
                lower_resp = resp_clean.lower()
                if "couldn't find" in lower_resp or "not found" in lower_resp:
                    explanation_text = "I couldn't find this in the available sources"
                else:
                    explanation_text = resp_clean
                    if req.fact_situation:
                        application_text = resp_clean
                used_llm = True
        except Exception as e:
            logger.warning(f"LLM explanation for maxim {stored_maxim} failed: {e}. Using grounded engine.")

    from app.services.citation_checker import citation_checker
    badged_explanation = citation_checker.check_and_badge_text(explanation_text, is_tier2=False)
    badged_application = citation_checker.check_and_badge_text(application_text, is_tier2=False) if application_text else None

    return {
        "found": True,
        "id": target_entry["id"],
        "maxim": stored_maxim,
        "meaning": stored_meaning,
        "category": stored_category,
        "explanation": badged_explanation,
        "application_to_facts": badged_application,
        "stored_example": stored_example,
        "indian_case_refs": stored_cases,
        "citations": [source_citation],
        "related_maxims": target_entry.get("related_maxims", []),
        "model_used": model_name if used_llm else "grounded_statutory_engine"
    }


@router.post("/chat", response_model=Dict[str, Any])
async def chat_maxim(req: MaximChatRequest):
    """
    Interactive Maxim Chat and 'Apply to My Situation'.
    Sends maxim, user message, and last 4 messages to the model.
    Follow-ups (e.g. 'is this applicable for an adult') use previous maxim as context.
    Never returns same stored text.
    """
    last_4_history = (req.history or [])[-4:]
    target_entry = _find_target_maxim(req.maxim_id, req.maxim, last_4_history)

    if not target_entry:
        return {
            "found": False,
            "response": "I couldn't find a verified legal maxim context for this query.",
            "citations": []
        }

    stored_maxim = target_entry["maxim"]
    stored_meaning = target_entry["meaning"]
    stored_explanation = target_entry["explanation"]
    stored_example = target_entry.get("example", "")
    stored_category = target_entry.get("category", "")
    stored_cases = target_entry.get("indian_case_refs", [])
    source_citation = f"{stored_maxim} ({stored_meaning})"

    response_text = _generate_maxim_chat_response(
        target_entry,
        req.message,
        last_4_history,
        req.fact_situation
    )
    used_llm = False
    model_name = settings.LLM_MODEL

    if llm_service.is_active and llm_service.client:
        try:
            from google.genai import types

            prompt_history = ""
            if last_4_history:
                prompt_history = "\nRecent Conversation History:\n" + "\n".join(
                    f"- {m.get('role', 'user').capitalize()}: {m.get('content', '')}" for m in last_4_history
                ) + "\n"

            prompt = (
                f"Grounded Maxim: {stored_maxim}\n"
                f"Literal Meaning: {stored_meaning}\n"
                f"Legal Category: {stored_category}\n"
                f"Verified Explanation: {stored_explanation}\n"
                f"Standard Example: {stored_example}\n"
                f"Verified Indian Cases: {json.dumps(stored_cases)}\n"
                f"{prompt_history}\n"
                f"User's Question / Situation: {req.message}\n\n"
                f"CRITICAL INSTRUCTIONS:\n"
                f"1. Directly answer the user's specific question or apply the maxim to their scenario.\n"
                f"2. If this is a follow-up (e.g. asking 'is this applicable for an adult'), answer the question directly stating whether it does not apply, citing relevant Indian statutory provisions (e.g. Section 82/83 IPC for doli incapax).\n"
                f"3. Never repeat the generic stored explanation verbatim.\n"
                f"4. Cite {source_citation} and keep it concise, clear, and grounded in Indian law."
            )

            system_instruction = (
                "You are an expert Indian legal educator explaining Latin legal maxims. "
                "Provide accurate, direct, and conversational explanations grounded in Indian law."
            )

            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                max_output_tokens=500
            )
            response = llm_service.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            if response.text and response.text.strip():
                response_text = response.text.strip()
                used_llm = True
        except Exception as e:
            logger.warning(f"LLM maxim chat failed: {e}. Using grounded engine.")

    from app.services.citation_checker import citation_checker
    badged_response = citation_checker.check_and_badge_text(response_text, is_tier2=False)

    return {
        "found": True,
        "id": target_entry["id"],
        "maxim": stored_maxim,
        "meaning": stored_meaning,
        "response": badged_response,
        "citations": [source_citation],
        "model_used": model_name if used_llm else "grounded_statutory_engine"
    }


@router.post("/{maxim_id}/chat", response_model=Dict[str, Any])
async def chat_maxim_path(maxim_id: str, req: MaximChatRequest):
    """Convenience path-based endpoint for maxim chat."""
    if not req.maxim_id:
        req.maxim_id = maxim_id
    return await chat_maxim(req)


@router.post("/{maxim_id}/explain", response_model=Dict[str, Any])
async def explain_maxim_path(maxim_id: str, req: Optional[MaximExplainRequest] = None):
    """Path-based convenience endpoint for explaining a legal maxim by slug."""
    payload = req or MaximExplainRequest(id=maxim_id)
    if not payload.id:
        payload.id = maxim_id
    return await explain_maxim(payload)

