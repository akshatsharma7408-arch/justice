"""
JUSTICE Legal AI Backend — Two-Tier AI Answer Framework
Tier 1: Grounded solely in verified sources (uploaded document or 12-case precedent corpus) with full citations.
Tier 2: Concise general conceptual legal explanation when not found in verified sources.
        - Must start with: 'General explanation, not verified against a legal database'
        - Must NOT name any case, citation, section number, or article.
        - Must end with: 'check a primary source before relying on this'
For queries needing a specific case or citation not present in our verified corpus:
        - Must reply: "I couldn't find a verified source for this"
"""

import re
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("justice.tiers")

NOT_FOUND_SPECIFIC_MSG = "I couldn't find a verified source for this"
TIER2_START_LABEL = "AI answer, not verified against a legal database."
TIER2_END_LABEL = "This is general information, not legal advice. Check a primary source or a lawyer before relying on it."
TIER2_UNAVAILABLE_MSG = "The AI service is currently unavailable to generate an explanation for this topic. Please try again shortly."
UNRELIABLE_TIER2_MSG = "I can't answer this reliably, please check the cases below"


def needs_specific_source(query: str) -> bool:
    """
    Detects if the query explicitly asks for or requires a specific case,
    judicial citation, statutory section, or constitutional article.
    """
    q = query.lower()

    # 1. Direct case name patterns (e.g. 'A v. B', 'A vs B', 'A versus B')
    if re.search(r'\b[a-z0-9\.\']+\s+(?:v\.|vs\.?|versus)\s+[a-z0-9\.\']+', q):
        return True

    # 2. Case citations (e.g. SCC, AIR, SCR, SCALE, Del HC)
    if re.search(r'\b(?:\d{4}\s+)?(?:scc|air|scr|scale)\b', q):
        return True

    # 3. Explicit queries asking for a case, citation, judgment, or bench
    case_query_patterns = [
        r'\b(?:which|what|name|cite|give|find|tell me the)\s+(?:landmark\s+)?(?:case|judgment|judgement|precedent|citation|ruling|decision)\b',
        r'\b(?:citation\s+for|cite\s+(?:the|a)\s+case|case\s+law\s+on)\b',
        r'\b(?:court\s+held|supreme\s+court\s+held|high\s+court\s+held|who\s+held|who\s+ruled)\b',
        r'\b(?:overruled\s+in|referred\s+to\s+larger\s+bench\s+in)\b',
        r'\b(?:bench\s+size|which\s+bench|who\s+were\s+the\s+judges)\b',
        r'\bin\s+which\s+(?:case|judgment|decision)\b',
    ]
    for pattern in case_query_patterns:
        if re.search(pattern, q):
            return True

    # 4. Inquiries specifying a section number, article number, or specific act
    if re.search(r'\b(?:sections?|secs?\.?|s\.)\s*\d+[a-zA-Z]*\b', q):
        return True
    if re.search(r'\b(?:articles?|arts?\.?)\s*\d+[a-zA-Z]*\b', q):
        return True
    if re.search(r'\b(?:which|what)\s+(?:section|article|statute|act|order|rule)\b', q):
        return True

    # 5. Well-known landmark judgments outside the 12-case corpus
    outside_landmark_cases = [
        "kesavananda", "minerva mills", "maneka gandhi", "bhim singh", "shah bano",
        "navtej", "shreya singhal", "vishaka", "golaknath", "shankari prasad",
        "sajjan singh", "brij bhushan", "romesh thappar", "champakam", "indira gandhi",
        "sr bommai", "bommai", "puttaswamy", "puttaswamy ii", "aadhaar", "mohori bibee",
        "hadley v baxendale", "carlill", "donoghue", "salomon v salomon", "balfour v balfour",
        "m.c. mehta", "mc mehta", "d.k. basu", "dk basu", "aruna shanbaug"
    ]
    for name in outside_landmark_cases:
        if name in q:
            return True

    try:
        from app.services.qdrant_service import fuzzy_word_match
        q_words = re.findall(r'[a-zA-Z0-9]{4,}', q)
        for name in outside_landmark_cases:
            name_words = [w for w in re.findall(r'[a-zA-Z0-9]{4,}', name)]
            if not name_words:
                continue
            hit = [any(len(nw) >= 4 and fuzzy_word_match(qw, nw) for qw in q_words) for nw in name_words]
            # multi-word names need every word matched (so "in india" no longer matches "indira gandhi");
            # single-word names need a reasonably long word to tolerate typos
            if len(name_words) >= 2:
                if all(hit):
                    return True
            elif hit[0] and len(name_words[0]) >= 6:
                return True
    except Exception:
        pass

    return False


def is_document_specific_query(query: str) -> bool:
    """
    Detects if the query is asking about a specific fact, clause, or party
    within an uploaded document (as opposed to an abstract legal concept).
    """
    q = query.lower()
    doc_specific_terms = [
        "this agreement", "this contract", "this document", "my contract", "my agreement",
        "the company", "the employer", "the consultant", "the employee", "the client",
        "clause", "section", "paragraph", "schedule", "stipulation", "provision in",
        "notice period", "severance", "compensation in this", "salary", "remuneration",
        "effective date", "termination date", "governing law of this", "parties to",
        "who is", "who are", "when does", "what is the date", "page", "signatory", "signed by"
    ]
    return any(term in q for term in doc_specific_terms)


def sanitize_tier2_text(text: str) -> str:
    """
    Strictly strips out any case names, citations, section numbers, or article numbers
    from text to guarantee compliance with Tier 2 restrictions.
    """
    from app.services.citation_checker import citation_checker
    return citation_checker.check_and_badge_text(text, is_tier2=True)


def format_tier2_response(explanation: str) -> str:
    """
    Formats a general conceptual or practical legal explanation to end with
    'This is general information, not legal advice. Check a primary source or a lawyer before relying on it.'
    The first line disclaimer is removed from the body because the UI badge already displays it.
    """
    raw = explanation.strip()

    # Strip any preexisting legacy or current start labels
    raw = re.sub(
        r'^(?:AI answer|General explanation)[,\s\-:]*(?:not verified against a legal database)?[:\s\-\.]*',
        '',
        raw,
        flags=re.IGNORECASE
    ).strip()

    # Strip any preexisting legacy or current end labels
    raw = re.sub(
        r'(?:This is general information, not legal advice\.?\s*Check a primary source or a lawyer before relying on it\.?|Check a primary source before relying on this\.?)$',
        '',
        raw,
        flags=re.IGNORECASE
    ).strip()

    # Sanitize any accidental cases, sections, or articles
    sanitized = sanitize_tier2_text(raw).strip()

    return f"{sanitized}\n\n{TIER2_END_LABEL}"
