"""
JUSTICE Legal AI Backend — Citation Verification Service
Ensures strict verification across all AI answer surfaces:
1. Doc Chat (/api/v1/doc/chat)
2. Universal Search (/api/v1/search)
3. Legal Maxims (/api/v1/maxims/explain)
4. Citator (/api/v1/citator/{case_id})

Every case name, citation, section, or article the model mentions must exist
in our corpus, landmark dictionary, or verified database.
If an unverified citation, case name, section, or article is present:
- NEVER insert internal tags like '[Not Verified]' into user text.
- The entire sentence containing the unverified mention is removed.
- Case names in the answer are matched against the case list using a robust matcher
  (ignoring case, punctuation, 'v.' vs 'versus', 'State of Kerala' vs 'State of Kerala & Anr').
- For Tier 2 general explanations: strictly strips any case name, citation, section, or article that appears.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple

from app.services.qdrant_service import qdrant_service, LANDMARK_METADATA
from app.services.statute_service import statute_service

logger = logging.getLogger("justice.citation_checker")

# Legacy constant used for verification assertions (never emitted into user text)
BADGE_NOT_VERIFIED = "[Not Verified]"

# Verified statutory sections in our corpus / database across Indian laws
VERIFIED_SECTIONS = {
    # Indian Contract Act, 1872
    "10", "11", "23", "27", "28", "29", "32", "56", "65", "70", "73", "74",
    # Specific Relief Act, 1963
    "14", "16", "20", "41", "42", "57",
    # Arbitration and Conciliation Act, 1996
    "8", "9", "11", "34", "37",
    # Code of Criminal Procedure, 1973
    "41", "41A", "41B", "41C", "41D", "50", "57", "154", "156", "161", "167", "437", "438", "439",
    # Indian Penal Code, 1860
    "82", "83", "299", "300", "302", "304", "304B", "307", "320", "375", "376", "377", "420", "498A", "499", "500",
    # Transfer of Property Act, 1882
    "106", "107", "108", "111",
    # Rent Control Acts
    "3", "3(1)(C)", "3(1)(c)", "3(1)", "14",
    # Protection of Women from Domestic Violence Act, 2005
    "2F", "2(F)", "12", "18", "19", "20", "22",
    # Information Technology Act, 2000
    "66A", "66", "43", "67", "79",
    # Negotiable Instruments Act, 1881
    "138", "139", "141",
    # Motor Vehicles Act, 1988
    "129", "130", "132", "133", "134", "161", "162", "163", "164", "164B", "165", "166", "168", "177", "184", "185", "207"
}

# Verified constitutional articles in our corpus / database
VERIFIED_ARTICLES = {
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11",
    "12", "13", "14", "15", "16", "19", "20", "21", "21A", "22", "25", "31A", "31C", "32",
    "39", "45", "46", "48", "48A", "51", "51A", "56", "61", "74", "75", "76",
    "124", "129", "131", "132", "133", "134", "136", "137", "141", "142", "143", "145",
    "214", "215", "217", "225", "226", "227", "239", "239AA", "239AB", "245", "246", "246A", "248", "254", "279A",
    "299", "300", "300A", "301", "311", "352", "356", "359", "360", "368", "370", "371", "372", "372A", "395"
}

PREPOSITIONS = {"in", "see", "under", "per", "re", "as"}

_EDITION_NOTE_RE = re.compile(r"\[Note from the official edition's footnotes:.*?\]", re.DOTALL)

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


def split_legal_sentences(text: str) -> List[str]:
    """
    Splits text into sentences while protecting legal abbreviations like
    v., vs., Ltd., Pvt., Co., Sec., Art., J., CJI., etc. from being split.
    """
    if not text:
        return []
    protected = text
    # Protect single uppercase initials: e.g. "S. B. Sinha", "J.", "V."
    protected = re.sub(r'\b([A-Z])\.\s+', r'\1__DOT__ ', protected)
    # Protect common legal abbreviations with periods
    abbrevs = [
        r'v\.', r'vs\.', r'ltd\.', r'pvt\.', r'co\.', r'corp\.', r'inc\.',
        r'dr\.', r'mr\.', r'mrs\.', r'ms\.', r'sec\.', r'secs\.', r'art\.', r'arts\.',
        r'no\.', r'nos\.', r'para\.', r'paras\.', r'ors\.', r'anr\.', r'uoi\.',
        r's\.c\.r\.', r's\.c\.c\.', r'a\.i\.r\.'
    ]
    for abb in abbrevs:
        protected = re.sub(rf'\b{abb}(?=\s+)', lambda m: m.group(0).replace('.', '__DOT__'), protected, flags=re.IGNORECASE)

    raw_sentences = re.split(r'(?<=[.!?])\s+', protected.strip())
    sentences = [s.replace('__DOT__', '.').strip() for s in raw_sentences if s.strip()]
    return sentences


def normalize_case_name(name: str) -> str:
    """Robustly normalizes a case name for resilient matching."""
    if not name:
        return ""
    n = name.lower()
    n = re.sub(r'[\(\)\[\],;\.\-"]', ' ', n)
    n = re.sub(r'\b(?:versus|vs\.?|v\.?)\b', ' v ', n)
    n = re.sub(r'\b(?:and\s+another|and\s+others|&?\s*anr\.?|&?\s*ors\.?)\b', '', n)
    n = re.sub(r'\b(?:pvt\.?|private|ltd\.?|limited|\(p\)\s*ltd|co\.?|company|corp\.?|corporation)\b', '', n)
    n = re.sub(r'\b(?:retd\.?|hon\'ble|justice|dr\.?|mr\.?|mrs\.?|ms\.?)\b', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


class CitationChecker:
    """
    Centralized service that enforces citation verification and text sanitization.
    """

    @staticmethod
    def verify_section(sec_num: str, doc_context: str = "") -> bool:
        """Checks if a section number exists in verified database, corpus, or document."""
        clean = re.sub(r'[^0-9a-zA-Z]', '', sec_num).upper()
        if clean in VERIFIED_SECTIONS:
            return True
        # Check without subsection: e.g. "498A" -> "498A", "2F" -> "2"
        base_num = re.sub(r'[A-Za-z]', '', clean)
        if base_num in VERIFIED_SECTIONS:
            return True
        if doc_context:
            d_lower = doc_context.lower()
            if f"section {clean.lower()}" in d_lower or f"clause {clean.lower()}" in d_lower or f"sec. {clean.lower()}" in d_lower:
                return True
        # Check SQLite statute database
        for act in ["contract", "specific", "arbitration", "mva", "crpc", "ipc", "constitution"]:
            if statute_service.get_provision_by_section(act, clean):
                return True
        return False

    @staticmethod
    def verify_article(art_num: str, doc_context: str = "") -> bool:
        """Checks if a constitutional article exists in verified database, corpus, or document."""
        clean = re.sub(r'[^0-9a-zA-Z]', '', art_num).upper()
        if clean in VERIFIED_ARTICLES:
            return True
        base_num = re.sub(r'[A-Za-z]', '', clean)
        if base_num in VERIFIED_ARTICLES:
            return True
        if doc_context:
            d_lower = doc_context.lower()
            if f"article {clean.lower()}" in d_lower or f"art. {clean.lower()}" in d_lower:
                return True
        # Check SQLite statute database for constitutional provisions
        if statute_service.get_provision_by_section("constitution", clean):
            return True
        # Check standard Constitution of India article bounds (Articles 1 to 395, with valid alphanumeric suffixes)
        m_art = re.match(r'^([1-9][0-9]{0,2}|[1-3][0-9]{2})([A-Z]{0,2})$', clean)
        if m_art:
            art_val = int(m_art.group(1))
            if 1 <= art_val <= 395:
                return True
        return False

    @classmethod
    def verify_case(cls, case_or_cit: str, allowed_cases: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Verifies whether a case title exists using robust normalization."""
        if not case_or_cit or len(case_or_cit.strip()) < 3:
            return False
        norm_target = normalize_case_name(case_or_cit)

        # 1. Match against allowed_cases (retrieved case list for this query)
        if allowed_cases:
            for c in allowed_cases:
                c_title = c.get("title") or c.get("case_name") or c.get("common_name") or ""
                c_norm = normalize_case_name(c_title)
                if c_norm and (c_norm in norm_target or norm_target in c_norm):
                    return True
                # Match distinctive party tokens (min length 4)
                t_tokens = [tok for tok in norm_target.split() if len(tok) >= 4 and tok not in {'state', 'union', 'india'}]
                c_tokens = [tok for tok in c_norm.split() if len(tok) >= 4 and tok not in {'state', 'union', 'india'}]
                if t_tokens and c_tokens and any(tt in c_tokens for tt in t_tokens):
                    return True

        # 2. Match against landmark metadata keys
        for lk in LANDMARK_METADATA.keys():
            if lk in norm_target or norm_target in lk:
                return True

        # 3. Match against verified corpus precedents
        for c in qdrant_service.corpus:
            c_title = c.get("title") or ""
            c_norm = normalize_case_name(c_title)
            if c_norm and (c_norm in norm_target or norm_target in c_norm):
                return True
            c_keywords = [k.lower() for k in c.get("keywords", [])]
            if any(k in norm_target for k in c_keywords):
                return True

        # 4. Delegate to qdrant_service.verify_citation
        res = qdrant_service.verify_citation(case_or_cit)
        return bool(res.get("verified"))

    @classmethod
    def verify_citation_str(cls, cit_str: str) -> bool:
        """Checks if a citation string is verified."""
        if not cit_str or len(cit_str.strip()) < 4:
            return False
        res = qdrant_service.verify_citation(cit_str)
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
        is_tier2: bool = False,
        allowed_cases: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Sentence filter that never drops a labelled official-edition footnote note.
        Those notes quote the case that struck a provision down; losing them would hide adverse context."""
        notes = _EDITION_NOTE_RE.findall(text or "")
        if not notes:
            return cls._check_and_badge_text_impl(text, doc_context, is_tier2, allowed_cases)
        masked = text
        for i, n in enumerate(notes):
            masked = masked.replace(n, f"@@EDNOTE{i}@@", 1)
        out = cls._check_and_badge_text_impl(masked, doc_context, is_tier2, allowed_cases)
        for i, n in enumerate(notes):
            tok = f"@@EDNOTE{i}@@"
            out = out.replace(tok, n) if tok in out else out.rstrip() + " " + n
        return out

    @classmethod
    def _check_and_badge_text_impl(
        cls,
        text: str,
        doc_context: str = "",
        is_tier2: bool = False,
        allowed_cases: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Main entry point for auditing AI-generated text.
        - If is_tier2: Strictly strips all case names, citations, sections, and articles.
        - If normal / Tier 1: Checks every citation, case name, section, and article.
          If any citation in a sentence cannot be verified, removes that entire sentence.
          Never puts raw internal tags like '[Not Verified]' in user text.
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
            stripped = re.sub(r'\[\s*NOT\s+VERIFIED\s*\]', '', stripped, flags=re.IGNORECASE)
            stripped = re.sub(r'[ \t]{2,}', ' ', stripped)
            stripped = re.sub(r'\s+,', ',', stripped)
            stripped = re.sub(r'\s+\.', '.', stripped)
            return stripped.strip()

        # -------------------------------------------------------------
        # Tier 1 / Normal AI answer: Verify each sentence
        # -------------------------------------------------------------
        if "\n\n" in text:
            # Keep paragraph breaks (the UI renders each paragraph separately): verify paragraph by paragraph.
            return "\n\n".join(
                cls.check_and_badge_text(part, is_tier2=False, allowed_cases=allowed_cases)
                for part in text.split("\n\n") if part.strip()
            )
        if "\n" in text.strip():
            # Keep line breaks (numbered clause lines): verify line by line.
            return "\n".join(
                cls.check_and_badge_text(part, is_tier2=False, allowed_cases=allowed_cases)
                for part in text.strip().split("\n") if part.strip()
            )
        sentences = split_legal_sentences(text.strip())
        verified_sentences = []

        for sent in sentences:
            if not sent.strip():
                continue

            sentence_has_unverified = False

            # 1. Check all case matches in this sentence
            for m in CASE_PATTERN.finditer(sent):
                full_str = m.group(0)
                case_name = m.group(1)
                cit = m.group(2) or ""
                _, actual_name, cit, actual_full = cls._clean_case_match(full_str, case_name, cit)

                is_ok = cls.verify_case(actual_full, allowed_cases) or cls.verify_case(actual_name, allowed_cases)
                if not is_ok:
                    logger.info("Dropping sentence due to unverified case: '%s'", actual_full)
                    sentence_has_unverified = True
                    break

            if sentence_has_unverified:
                continue

            # 1b. Check standalone famous outside cases
            for pat in OUTSIDE_FAMOUS_CASES:
                m_fc = re.search(pat, sent, flags=re.IGNORECASE)
                if m_fc:
                    fc_name = m_fc.group(0)
                    if not (cls.verify_case(fc_name, allowed_cases) or (allowed_cases and any(normalize_case_name(fc_name) in normalize_case_name(c.get("title", "")) for c in allowed_cases))):
                        logger.info("Dropping sentence due to unverified outside famous case: '%s'", fc_name)
                        sentence_has_unverified = True
                        break

            if sentence_has_unverified:
                continue

            # 2. Check standalone citations
            for m in STANDALONE_CIT_PATTERN.finditer(sent):
                cit_str = m.group(1).strip()
                if not cls.verify_citation_str(cit_str):
                    logger.info("Dropping sentence due to unverified standalone citation: '%s'", cit_str)
                    sentence_has_unverified = True
                    break

            if sentence_has_unverified:
                continue

            # 3. Check statutory sections
            for m in SECTION_PATTERN.finditer(sent):
                sec_num = m.group(2)
                if not cls.verify_section(sec_num, doc_context):
                    logger.info("Dropping sentence due to unverified statutory section: '%s'", sec_num)
                    sentence_has_unverified = True
                    break

            if sentence_has_unverified:
                continue

            # 4. Check constitutional articles
            for m in ARTICLE_PATTERN.finditer(sent):
                art_num = m.group(2)
                if not cls.verify_article(art_num, doc_context):
                    logger.info("Dropping sentence due to unverified constitutional article: '%s'", art_num)
                    sentence_has_unverified = True
                    break

            if sentence_has_unverified:
                continue

            # Sentence is fully verified
            verified_sentences.append(sent)

        result_text = " ".join(verified_sentences).strip()
        # Clean any raw leaked tags from upstream models or prompts
        result_text = re.sub(r'\[\s*NOT\s+VERIFIED\s*\]', '', result_text, flags=re.IGNORECASE)
        result_text = re.sub(r'[ \t]{2,}', ' ', result_text)
        result_text = re.sub(r'\s+,', ',', result_text)
        result_text = re.sub(r'\s+\.', '.', result_text)
        if not result_text and text.strip():
            logger.info("Sentence stripping yielded empty result; providing grounded fallback explanation.")
            return "I couldn't verify all specific citations in this response against our database. Please consult authoritative primary sources for exact provision text and judicial rulings."
        return result_text.strip()

    @classmethod
    def badge_citations_list(cls, citations: List[str], doc_context: str = "") -> List[str]:
        """
        Validates an array of citation strings:
        Keeps verified citations, drops unverified ones, and strips internal tags.
        """
        if not citations:
            return []
        verified_list = []
        for c in citations:
            if not isinstance(c, str):
                continue
            c_clean = re.sub(r'\[\s*NOT\s+VERIFIED\s*\]', '', c, flags=re.IGNORECASE).strip()
            if not c_clean:
                continue
            if doc_context and ("clause" in c_clean.lower() or "section" in c_clean.lower()):
                verified_list.append(c_clean)
                continue
            if cls.verify_case(c_clean) or cls.verify_citation_str(c_clean):
                verified_list.append(c_clean)
        return verified_list


citation_checker = CitationChecker()
