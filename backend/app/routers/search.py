import asyncio
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
import re

from app.config import settings
from app.services.llm_service import llm_service
from app.services.qdrant_service import qdrant_service
from app.services.spelling_service import correct_query
from app.services.answer_tiers import UNRELIABLE_TIER2_MSG
from app.services.statute_service import statute_service

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
    statute_notice: Optional[str] = None

_ART_SUFFIX_RE = re.compile(
    r'\b((?i:articles?|arts?\.?)\s*\d{1,3})\s+([A-Z]{1,2}|aa|ab|ba|bb)\b(?!\s*[A-Za-z])'
)


def _allow_question_only_fallback():
    """Search answers see only the typed question and public corpus text, so an external fallback model may be
    used here (when configured). Every other route (uploads, contract audit, case/doc chat) leaves it off."""
    from app.services.groq_client import ALLOW_EXTERNAL_FALLBACK
    ALLOW_EXTERNAL_FALLBACK.set(True)


def normalize_article_suffix(query: str) -> str:
    """Join a spaced letter suffix to its article number ("article 339 AA" -> "article 339AA").

    Without this the lookup silently dropped the letters and answered the bare
    article (339) as if it were what was asked. Suffix must be uppercase (1-2
    letters) or aa/ab/ba/bb, so ordinary words ("article 21 in", "article 14 or")
    are untouched.
    """
    return _ART_SUFFIX_RE.sub(lambda m: m.group(1) + m.group(2).upper(), query or "")


_MULTI_ART_RE = re.compile(
    r"\barticles?\s+(\d{1,3}[A-Za-z]{0,2})\s*(?:,|\bor\b|\band\b|&|/)\s*(?:articles?\s+)?(\d{1,3}[A-Za-z]{0,2})\b(?:\s*(?:,|\bor\b|\band\b|&|/)\s*(?:articles?\s+)?(\d{1,3}[A-Za-z]{0,2})\b)?",
    re.I)
_BARE_ART_RE = re.compile(r"^\s*(?:what\s+is|explain|define|meaning\s+of)?\s*(\d{1,3}\s?[A-Za-z]{1,2})\s*\??\s*$", re.I)


def split_multi_article(query: str):
    """'article 14 or 15' -> ['14', '15'] (max 3); otherwise None."""
    m = _MULTI_ART_RE.search(query or "")
    if not m:
        return None
    nums = [g.upper() for g in m.groups() if g]
    return nums if len(set(nums)) >= 2 else None


def resolve_bare_article(query: str) -> str:
    """A bare number with a letter suffix ("300A", "what is 21A") is routed as an article only when
    that exact article exists in the Constitution text we hold; otherwise unchanged."""
    m = _BARE_ART_RE.match(query or "")
    if not m:
        return query
    num = m.group(1).replace(" ", "").upper()
    try:
        from app.services.statute_service import statute_service
        if statute_service.get_provision("constitution", num):
            return f"article {num}"
    except Exception:
        pass
    return query


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
    _allow_question_only_fallback()
    """
    POST /api/v1/search
    Conducts dense/sparse retrieval over the verified precedent corpus.
    If enable_hyde is False, returns retrieved cases immediately without synthesis.
    If enable_hyde is True, synthesizes judicial holding strictly from retrieved precedents with source citations.
    """
    raw_query = normalize_article_suffix((payload.query or "").strip())
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
    tier1_results = synthesis.get("results") if "results" in synthesis else results

    from app.services.citation_checker import citation_checker
    is_tier2 = "tier2" in synthesis.get("model_used", "").lower()
    _nf = ("not_found" in (synthesis.get("model_used") or "").lower()) or (synthesis.get("model_used") == "unverified_ai_answer")
    ai_ans = (synthesis.get("answer") or "") if _nf else citation_checker.check_and_badge_text(synthesis.get("answer") or "", is_tier2=is_tier2)
    _base_ans = ai_ans
    ratio = None if is_tier2 else citation_checker.check_and_badge_text(synthesis.get("ratio_decidendi") or _base_ans, is_tier2=False)
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

ANSWER_TIME_BUDGET_S = 45



STATUTE_CARD_MAX_CHARS = 3000


def build_statute_card(query: str) -> str:
    """Non-LLM, verbatim provisions from the bare acts in the database whose heading is covered by the query.
    Returned as a separate, labelled block; it is source text, not an AI explanation."""
    try:
        matches = statute_service.match_provisions_for_general_query(query, limit=2)
    except Exception:
        return ""
    if not matches:
        return ""
    blocks = []
    for m in matches:
        body = re.sub(r"\s+", " ", (m.get("body") or "")).strip()
        if not body:
            continue
        total = len(body)
        cut = total > STATUTE_CARD_MAX_CHARS
        label = "Full text of the provision"
        if cut:
            body = body[:STATUTE_CARD_MAX_CHARS].rsplit(" ", 1)[0]
            label = (f"EXCERPT ONLY - first {len(body)} of {total} characters; the rest of the provision "
                     "(possibly including provisos, explanations or exceptions) is not shown")
        edition = (m.get("edition") or "edition not recorded").strip()
        src = m.get("source_url")
        if src and "prsindia.org" in src:
            src_label = "Third-party reference copy (PRS India, not the Gazette; the text above is from the Gazette named in the edition note)"
        else:
            src_label = "Source"
        blocks.append(
            f"{m.get('act_title')}, Section {m.get('section_number')} - {m.get('heading')}\n"
            f"Edition: {edition}\n{label}:\n\"{body}\"" + (f"\nRead the full provision - {src_label}: {src}" if (src and cut) else ("\nThe full provision is not linked here; check the official Act." if cut else "")) + (f"\n{src_label}: {src}" if (src and not cut) else "")
        )
    if not blocks:
        return ""
    return ("POSSIBLY RELEVANT PROVISION (a suggestion from matching your words to the section heading; it may not apply "
            "to your situation and is not a legal conclusion). Text is taken word for word from our statute database; it is not an AI "
            "explanation, and amendments and current applicability are not checked here.\n\n" + "\n\n".join(blocks))


_OLD_CODE_RE = re.compile(r"\b(?:IPC|CrPC|Cr\.P\.C|Indian Penal Code|Code of Criminal Procedure|Indian Evidence Act)\b", re.I)
OLD_CODE_NOTE = ("NOTE ON WHICH LAW APPLIES: The Indian Penal Code, 1860, the Code of Criminal Procedure, 1973 and the Indian Evidence "
                 "Act, 1872 were repealed and replaced by the Bharatiya Nyaya Sanhita (BNS), the Bharatiya Nagarik Suraksha Sanhita (BNSS) and the "
                 "Bharatiya Sakshya Adhiniyam (BSA), in force from 1 July 2024 (our database records the Gazette notifications "
                 "S.O. 848(E)-850(E) of 23 Feb 2024). Which code governs a matter is set by each new law's repeal and savings section "
                 "and is not a single date test. BNS s.358 saves the previous operation of the IPC and anything done or suffered under it. "
                 "BNSS s.531(2)(a) says an appeal, application, trial, inquiry or investigation pending immediately before commencement "
                 "continues under the CrPC; the BSA has its own savings section (s.170). Read those sections and check the facts and stage of the "
                 "matter before relying on any section number shown from an older judgment or the old codes.")


def old_code_note_needed(text: str, model_used: str) -> bool:
    if not text or "statut" in (model_used or "").lower() or "BNS" in text or "Bharatiya" in text or "NOTE ON WHICH LAW APPLIES" in text:
        return False
    return bool(_OLD_CODE_RE.search(text))

@router.post("/search/answer", response_model=SearchAnswerResponse)
async def search_answer_post(payload: SearchAnswerRequest):
    _allow_question_only_fallback()
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
    raw_query = resolve_bare_article(normalize_article_suffix((payload.query or "").strip()))
    if len(raw_query) > 300:
        raise HTTPException(
            status_code=400,
            detail="Please shorten your question. Queries are limited to 300 characters."
        )

    _multi = split_multi_article(raw_query)
    if _multi and not getattr(payload, "_sub", False):
        parts = []
        for n in _multi:
            sub = SearchAnswerRequest(query=f"article {n}")
            parts.append((n, await search_answer_post(sub)))
        first = parts[0][1]
        body = "\n\n".join(f"ARTICLE {n}" + (f" ({r.tier_label})" if r.tier_label else "") + f"\n\n{r.ai_answer or 'No verified source found for this article number.'}" for n, r in parts)
        merged = first.model_copy(deep=True)
        merged.ai_answer = f"Your question names several articles; each is answered separately below.\n\n{body}"
        merged.query = raw_query
        merged.original_query = raw_query
        for _n, r in parts[1:]:
            merged.citations = list(merged.citations or []) + [c for c in (r.citations or []) if c not in (merged.citations or [])]
            merged.source_cases = list(merged.source_cases or []) + list(r.source_cases or [])
        if True:
            merged.tier_label = "Several provisions - see the label under each article"
        merged.statute_notice = None
        return merged

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

    _timed_out = False
    try:
        # Whole-request time budget: a rate-limited model must not leave the user waiting for minutes.
        synthesis = await asyncio.wait_for(
            llm_service.synthesize_search_answer(effective_query, results, force_fallback=payload.force_fallback),
            timeout=ANSWER_TIME_BUDGET_S,
        )
    except asyncio.TimeoutError:
        logger.warning("Answer synthesis exceeded %ss; returning the model-free answer", ANSWER_TIME_BUDGET_S)
        _timed_out = True
        synthesis = await llm_service.synthesize_search_answer(effective_query, results, force_fallback=True)
        if isinstance(synthesis.get("answer"), str):
            synthesis["answer"] += ("\n\nThe AI service was too slow to finish an explanation in time, "
                                    "so only the verified source text above is shown. AI explanation temporarily unavailable.")

    from app.services.citation_checker import citation_checker
    model_used = synthesis.get("model_used", "")
    is_tier2 = "tier2" in model_used.lower()
    is_not_found = "not_found" in model_used.lower()
    is_unv = model_used == "unverified_ai_answer"

    _nf = ("not_found" in (synthesis.get("model_used") or "").lower()) or (synthesis.get("model_used") == "unverified_ai_answer")
    ai_ans = (synthesis.get("answer") or "") if _nf else citation_checker.check_and_badge_text(synthesis.get("answer") or "", is_tier2=is_tier2)
    _base_ans = ai_ans
    if is_tier2 and not _timed_out:
        _card = build_statute_card(effective_query)
        if _card:
            if ai_ans == UNRELIABLE_TIER2_MSG:
                ai_ans = "No AI explanation is available for this question. The provision text below is shown word for word."
            ai_ans = f"{ai_ans}\n\n{_card}"
    _withheld = False
    if not is_not_found and not is_unv and old_code_note_needed(ai_ans, model_used):
        _withheld = True
        ai_ans = ("A case-based AI summary was withheld here: it depends on section numbers of the old Indian Penal Code, "
                  "Code of Criminal Procedure or Indian Evidence Act, and which code applies depends on the facts and stage of the "
                  "matter. The cases found are listed below as sources to read, not as a stated answer.\n\n" + OLD_CODE_NOTE)
        if not is_tier2:
            _c2 = build_statute_card(effective_query)
            if _c2:
                ai_ans = f"{ai_ans}\n\n{_c2}"
    if (not is_tier2 and not is_not_found and "statut" not in (model_used or "").lower()
            and ai_ans.startswith("I couldn't verify all specific citations") and "POSSIBLY RELEVANT PROVISION" not in ai_ans):
        _c3 = build_statute_card(effective_query)
        if _c3:
            ai_ans = f"{ai_ans}\n\nThe AI answer could not be checked, so no AI explanation is shown. Related text from the statute database:\n\n{_c3}"
    ratio = None if (is_tier2 or is_not_found or is_unv) else citation_checker.check_and_badge_text(synthesis.get("ratio_decidendi") or _base_ans, is_tier2=False)
    if _withheld:
        ratio = None
    citations = citation_checker.badge_citations_list(synthesis.get("citations", [])) if not is_tier2 else []

    # Determine source cases and Tier/Label
    hide_badge = False
    if is_not_found:
        tier = "not_found"
        tier_label = ""
        source_cases = []
        no_strong = True
        hide_badge = True
    elif is_unv:
        tier = "unverified_ai"
        tier_label = synthesis.get("tier_label") or "AI-generated answer. Not checked against legal sources. May be wrong or outdated."
        source_cases = []
        no_strong = True
        hide_badge = True
    elif is_tier2:
        if synthesis.get("hide_badge") or ai_ans == UNRELIABLE_TIER2_MSG or "unreliable" in model_used.lower() or "unavailable" in model_used.lower():
            tier = "unreliable"
            tier_label = ""
            hide_badge = True
        else:
            tier = "tier2"
            tier_label = synthesis.get("tier_label") or "AI general information (not verified against any legal source)"
            hide_badge = False
        source_cases = synthesis.get("results") if "results" in synthesis else (results or [])
        no_strong = synthesis.get("no_strong_case_match", len(source_cases) == 0)
    else:
        tier = synthesis.get("tier") or "tier1"
        tier_label = synthesis.get("tier_label") or "AI summary based on the cases below"
        source_cases = synthesis.get("results") if "results" in synthesis else (results or [])
        no_strong = synthesis.get("no_strong_case_match", len(source_cases) == 0)
        hide_badge = synthesis.get("hide_badge", False)

    if _withheld:
        tier_label = "Case summary withheld: relies on old-code section numbers"
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
        hide_badge=hide_badge,
        statute_notice=(synthesis.get("statute_notice") if not is_not_found else None)
    )
    if payload.results is None and not _timed_out and not re.search(r"AI explanation (?:temporarily )?unavailable", resp.ai_answer or ""):
        # A temporary rate-limit or rejected explanation must not be frozen into the cache.
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

