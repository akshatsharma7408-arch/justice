"""
JUSTICE Legal AI Backend — Citation Verification and Badging Service
Ensures strict verification across all AI answer surfaces:
1. Doc Chat (/api/v1/doc/chat)
2. Universal Search (/api/v1/search)
3. Legal Maxims (/api/v1/maxims/explain)
4. Citator (/api/v1/citator/{case_id})

Every case name, citation, section, or article the model mentions must exist
in our corpus or database (the 12 landmark precedents and the Qdrant collection "sc_judgments").
If it does not exist:
- Removes that mention from the answer and shows a "[Not Verified]" badge on it instead.
- For Tier 2 general explanations: strictly strips any case name, citation, section, or article that appears.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple

from app.services.qdrant_service import qdrant_service
from app.services.statute_service import statute_service

logger = logging.getLogger("justice.citation_checker")

BADGE_NOT_VERIFIED = "[Not Verified]"

# Verified statutory sections in our corpus / database
VERIFIED_SECTIONS = {
    # Indian Contract Act, 1872
    "10", "11", "23", "27", "28", "29", "32", "56", "65", "70", "73", "74",
    # Specific Relief Act, 1963
    "14", "16", "20", "41", "42", "57",
    # Arbitration and Conciliation Act, 1996
    "8", "9", "11", "34", "37"
}

# Verified constitutional articles in our corpus / database
VERIFIED_ARTICLES = {
    "14", "19", "21", "32", "136", "141", "142", "145", "226", "359"
}

PREPOSITIONS = {"in", "see", "under", "per", "re", "as"}

# Pre-compiled regex patterns
PARTY_WORD = r"(?:[A-Za-z0-9&'\.\-]+|\((?![\[\s]*[12]\d{3}\b)[^\)]+\)|\[(?![\[\s]*[12]\d{3}\b)[^\]]+\])"
PARTY_A = rf"[A-Z][A-Za-z0-9&'\.\-]*(?:[ \t]+{PARTY_WORD}){{0,12}}"
PARTY_B = rf"[A-Z][A-Za-z0-9&'\.\-]*(?:[ \t]+{PARTY_WORD}){{0,12}}"

CASE_PATTERN = re.compile(
    rf'\b({PARTY_A}[ \t]+(?:v\.|vs\.?|versus)[ \t]+{PARTY_B})'
    r'(?:[ \t]*,?[ \t]*(\(?\[?\b[12]\d{3}\)?\]?[ \t]*\d*[ \t]*(?:SCC|AIR|SCR|SCALE|CompCas|ILR|PTC|DLT|INSC|S\.C\.R\.)[^\n,;\.]*))?',
    re.IGNORECASE
)

STANDALONE_CIT_PATTERN = re.compile(
    r'(\(?\[?\b[12]\d{3}\)?\]?[ \t]*\d*[ \t]*(?:SCC|AIR|SCR|SCALE|CompCas|ILR|PTC|DLT|INSC|S\.C\.R\.)[ \t]*\d+[A-Za-z0-9\s]*)',
    re.IGNORECASE
)

SECTION_PATTERN = re.compile(
    r'\b(Sections?|Secs?\.?|S\.)[\s\u202f]*(\d+[A-Za-z]*(?:\([0-9a-zA-Z]+\))*)\b',
    re.IGNORECASE
)

ARTICLE_PATTERN = re.compile(
    r'\b(Articles?|Arts?\.?)[ \s\u202f]*(\d+[A-Za-z]*(?:\([0-9a-zA-Z]+\))*)\b',
    re.IGNORECASE
)

OUTSIDE_FAMOUS_CASES = [
    r'\bkesavananda\s+bharati(?:\s+v\.?\s+state\s+of\s+kerala)?\b',
    r'\bmohori\s+bibee(?:\s+v\.?\s+dharmodas\s+ghose)?\b',
    r'\bmaneka\s+gandhi(?:\s+v\.?\s+union\s+of\s+india)?\b',
    r'\bminerva\s+mills(?:\s+v\.?\s+union\s+of\s+india)?\b',
    r'\bshah\s+bano\b',
    r'\bhadley\s+v\.?\s+baxendale\b',
    r'\bbalfour\s+v\.?\s+balfour\b',
    r'\bsalomon\s+v\.?\s+salomon\b',
    r'\bdonoghue\s+v\.?\s+stevenson\b',
    r'\brylands\s+v\.?\s+fletcher\b',
]


class CitationChecker:
    """
    Centralized service that enforces citation verification and badging.
    """

    @staticmethod
    def verify_section(sec_num: str, doc_context: str = "") -> bool:
        """Checks if a section number exists in verified database, corpus, or document."""
        clean = re.sub(r'[^0-9a-zA-Z]', '', sec_num).lower()
        if clean in VERIFIED_SECTIONS:
            return True
        if doc_context:
            d_lower = doc_context.lower()
            if f"section {clean}" in d_lower or f"clause {clean}" in d_lower or f"sec. {clean}" in d_lower:
                return True
        # Check SQLite statute database
        for act in ["contract", "specific", "arbitration"]:
            if statute_service.get_provision_by_section(act, clean):
                return True
        return False

    @staticmethod
    def verify_article(art_num: str, doc_context: str = "") -> bool:
        """Checks if a constitutional article exists in verified database, corpus, or document."""
        clean = re.sub(r'[^0-9a-zA-Z]', '', art_num).lower()
        if clean in VERIFIED_ARTICLES:
            return True
        if doc_context:
            d_lower = doc_context.lower()
            if f"article {clean}" in d_lower or f"art. {clean}" in d_lower:
                return True
        return False

    @staticmethod
    def verify_case(case_or_cit: str) -> bool:
        """Verifies whether a case title or citation exists in the 12 precedents or sc_judgments."""
        res = qdrant_service.verify_citation(case_or_cit)
        return bool(res.get("verified"))

    @classmethod
    def _clean_case_match(cls, full_str: str, case_name: str, cit: str) -> Tuple[str, str, str, str]:
        prefix = ""
        parts = case_name.split(None, 1)
        if len(parts) == 2 and parts[0].lower() in PREPOSITIONS:
            prefix = parts[0] + " "
            actual_name = parts[1]
        else:
            actual_name = case_name

        actual_full = (actual_name + (" " + cit if cit else "")).strip()
        return prefix, actual_name, cit, actual_full

    @classmethod
    def check_and_badge_text(
        cls,
        text: str,
        doc_context: str = "",
        is_tier2: bool = False
    ) -> str:
        """
        Main entry point for auditing an AI-generated text.
        - If is_tier2: Strictly strips all case names, citations, sections, and articles.
        - If normal / tier 1: Verifies each mention against our corpus. If unverified,
          removes the mention and replaces it with '[Not Verified]'.
        """
        if not text:
            return text

        # -------------------------------------------------------------
        # Tier 2: General explanation must never name any case, citation, section, or article
        # -------------------------------------------------------------
        if is_tier2:
            stripped = CASE_PATTERN.sub(
                lambda m: cls._clean_case_match(m.group(0), m.group(1), m.group(2) or "")[0],
                text
            )
            for pat in OUTSIDE_FAMOUS_CASES:
                stripped = re.sub(pat, '', stripped, flags=re.IGNORECASE)
            stripped = STANDALONE_CIT_PATTERN.sub('', stripped)
            stripped = SECTION_PATTERN.sub('', stripped)
            stripped = ARTICLE_PATTERN.sub('', stripped)
            # Clean dangling punctuation from stripped tokens
            stripped = re.sub(r'\b(?:In|Under|Per|See|As held in)\s*,\s*', '', stripped, flags=re.IGNORECASE)
            stripped = re.sub(r'\b(?:In|Under|Per|See)\s+(?:the\s+)?(?=court|judgment|ruling|holding)', '', stripped, flags=re.IGNORECASE)
            stripped = re.sub(r'[ \t]{2,}', ' ', stripped)
            stripped = re.sub(r'\s+,', ',', stripped)
            stripped = re.sub(r'\s+\.', '.', stripped)
            return stripped.strip()

        # -------------------------------------------------------------
        # Tier 1 / Normal AI answer: Verify and badge unverified items
        # -------------------------------------------------------------
        def replace_case(m):
            full_str = m.group(0)
            case_name = m.group(1)
            cit = m.group(2) or ""
            prefix, actual_name, cit, actual_full = cls._clean_case_match(full_str, case_name, cit)

            v_full = qdrant_service.verify_citation(actual_full)
            v_name = qdrant_service.verify_citation(actual_name)
            v = v_full if v_full.get("verified") else v_name

            if v.get("verified"):
                return full_str
            return (prefix + BADGE_NOT_VERIFIED).strip()

        badged = CASE_PATTERN.sub(replace_case, text)

        # Standalone famous outside cases
        for pat in OUTSIDE_FAMOUS_CASES:
            badged = re.sub(pat, BADGE_NOT_VERIFIED, badged, flags=re.IGNORECASE)

        # Standalone citations
        def replace_cit(m):
            cit_str = m.group(1).strip()
            v = qdrant_service.verify_citation(cit_str)
            if v.get("verified"):
                return m.group(0)
            return BADGE_NOT_VERIFIED

        badged = STANDALONE_CIT_PATTERN.sub(replace_cit, badged)

        # Sections
        def replace_sec(m):
            sec_num = m.group(2)
            if cls.verify_section(sec_num, doc_context):
                return m.group(0)
            return BADGE_NOT_VERIFIED

        badged = SECTION_PATTERN.sub(replace_sec, badged)

        # Articles
        def replace_art(m):
            art_num = m.group(2)
            if cls.verify_article(art_num, doc_context):
                return m.group(0)
            return BADGE_NOT_VERIFIED

        badged = ARTICLE_PATTERN.sub(replace_art, badged)

        # Clean duplicate consecutive badges: '[Not Verified] [Not Verified]' -> '[Not Verified]'
        badged = re.sub(r'(\[Not Verified\][ \t]*)+', '[Not Verified] ', badged)
        badged = re.sub(r'[ \t]+,', ',', badged)
        badged = re.sub(r'[ \t]+\.', '.', badged)
        return badged.strip()

    @classmethod
    def badge_citations_list(cls, citations: List[str], doc_context: str = "") -> List[str]:
        """
        Badges an array of citation strings if any unverified mentions are present.
        """
        if not citations:
            return []
        verified_list = []
        for c in citations:
            if not isinstance(c, str):
                verified_list.append(c)
                continue
            # If it's a clause reference in document, verify it
            if doc_context and ("clause" in c.lower() or "section" in c.lower()):
                verified_list.append(c)
                continue
            badged_c = cls.check_and_badge_text(c, doc_context=doc_context, is_tier2=False)
            verified_list.append(badged_c)
        return verified_list


citation_checker = CitationChecker()
