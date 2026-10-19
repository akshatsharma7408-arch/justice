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
TIER2_START_LABEL = "General explanation, not verified against a legal database: "
TIER2_END_LABEL = "Check a primary source before relying on this."


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
        "sr bommai", "bommai", "puttaswamy ii", "aadhaar", "mohori bibee",
        "hadley v baxendale", "carlill", "donoghue", "salomon v salomon", "balfour v balfour",
        "m.c. mehta", "mc mehta", "d.k. basu", "dk basu", "aruna shanbaug"
    ]
    for name in outside_landmark_cases:
        if name in q:
            return True

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
    # 1. Strip formal law citations like (2015) 4 SCC 136 or AIR 1967 SC 1098
    cleaned = re.sub(r'\(?\b\d{4}\)?\s*\d*\s*(?:SCC|AIR|SCR|SCALE|CompCas|ILR)[^\n,;.]*', '', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bAIR\s+\d{4}\s+[A-Za-z\s]+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b\d+\s+SCC\s+\d+\b', '', cleaned, flags=re.IGNORECASE)

    # 2. Strip case party names e.g. 'X v. Y' or 'X vs. Y'
    cleaned = re.sub(r'\b[A-Z][a-zA-Z0-9\s\.\']+\s+(?:v\.|vs\.?|versus)\s+[A-Z][a-zA-Z0-9\s\.\']+', 'judicial precedent', cleaned)

    # 2b. Strip specific precedent and party names
    known_precedent_tokens = [
        r'\bkailash\s+nath(?:\s+associates)?\b',
        r'\bdelhi\s+development\s+authority\b|\bdda\b',
        r'\bpercept\s+d\'?mark\b',
        r'\bzaheer\s+khan\b',
        r'\bkrishan\s+murgai\b',
        r'\bsuperintendence\s+co(?:mpany)?(?:\s+of\s+india)?\b',
        r'\bniranjan\s+shankar\s+golikari\b|\bgolikari\b',
        r'\bputtaswamy\b|\bjustice\s+k\.?s\.?\s+puttaswamy\b',
        r'\badm\s+jabalpur\b|\bshivkant\s+shukla\b',
        r'\bdawoodi\s+bohra(?:\s+community)?\b',
        r'\bambiance\s+india\b|\bnaveen\s+jain\b',
        r'\bstellar\s+information(?:\s+technology)?\b|\brakesh\s+kumar\b',
        r'\baffle\s+holdings\b',
        r'\bkesavananda\s+bharati\b',
        r'\bminerva\s+mills\b',
        r'\bmaneka\s+gandhi\b',
    ]
    for p_pat in known_precedent_tokens:
        cleaned = re.sub(p_pat, 'judicial precedent', cleaned, flags=re.IGNORECASE)

    # 3. Strip specific section numbers (e.g. 'Section 27', 'Section 74', 'Sec. 10')
    cleaned = re.sub(r'\b(?:sections?|secs?\.?|s\.)\s*\d+[a-zA-Z]*\b', 'statutory provisions', cleaned, flags=re.IGNORECASE)

    # 4. Strip specific article numbers (e.g. 'Article 21', 'Art. 141')
    cleaned = re.sub(r'\b(?:articles?|arts?\.?)\s*\d+[a-zA-Z]*\b', 'constitutional provisions', cleaned, flags=re.IGNORECASE)

    # 5. Clean up duplicate spaces and punctuation
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ,;:-')
    return cleaned


def format_tier2_response(explanation: str) -> str:
    """
    Formats a general conceptual legal explanation to strictly start with
    'General explanation, not verified against a legal database: ' and end with
    'Check a primary source before relying on this.'
    """
    # Strip any preexisting prefixes/suffixes
    raw = explanation.strip()
    raw = re.sub(r'^general explanation[,\s\-:]*(?:not verified against a legal database)?[:\s\-]*', '', raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r'check a primary source before relying on this\.?$', '', raw, flags=re.IGNORECASE).strip()

    # Sanitize any accidental cases, sections, or articles
    sanitized = sanitize_tier2_text(raw)
    if not sanitized.endswith('.'):
        sanitized += '.'

    return f"{TIER2_START_LABEL}{sanitized} {TIER2_END_LABEL}"
