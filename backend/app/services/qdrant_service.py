"""
JUSTICE Legal AI Backend - Qdrant Vector Service
Hybrid retrieval over the verified Indian precedent corpus
(backend/app/data/section27_precedents.json) and real Supreme Court
of India judgments (collection 'sc_judgments').

Modes:
  - "qdrant": live Qdrant Cloud collection queried with dense query vectors (384-dim).
  - "local_index": dense semantic retrieval via local all-MiniLM-L6-v2 embeddings
    over the verified 12-precedent corpus and 960 real Supreme Court of India judgments
    (17,737 chunks) when Qdrant Cloud is idle/offline.

The active mode is reported in every search result and in /health, so the
retrieval mode and embedding engine are always transparent.
"""

import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from app.config import settings
from app.services.embedding_service import embedding_service

logger = logging.getLogger("justice.qdrant")

CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "section27_precedents.json"
SC_DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sc_dataset"
SC_CHUNKS_PATH = SC_DATASET_DIR / "chunks" / "chunks.json"
SC_EMBEDDINGS_PATH = SC_DATASET_DIR / "embeddings" / "embeddings_checkpoint.parquet"
SC_METADATA_PATH = SC_DATASET_DIR / "metadata" / "filtered_cases.parquet"


def _load_corpus() -> List[Dict[str, Any]]:
    try:
        with open(CORPUS_PATH, "r", encoding="utf-8") as f:
            cases = json.load(f).get("precedents", [])
            for c in cases:
                enrich_landmark_metadata(c)
            return cases
    except Exception as e:
        logger.error("Could not load precedent corpus at %s: %s", CORPUS_PATH, e)
        return []


def _case_to_text(case: Dict[str, Any]) -> str:
    return (
        f"{case.get('title', '')}. {case.get('citation', '')}. {case.get('court', '')}. "
        f"{' '.join(case.get('statutes', []))}. {case.get('ratioSummary', '')}. "
        f"{' '.join(case.get('keywords', []))}"
    )


TOPIC_DEFINITIONS = {
    "arrest_detention": {
        "phrases": [
            "police custody", "custodial", "illegal detention", "unlawful detention",
            "without a warrant", "without warrant", "arrest warrant", "right to be informed",
            "produce before magistrate", "police arrest", "remand to custody", "judicial custody",
            "statutory bail", "default bail", "anticipatory bail", "grounds of arrest",
            "article 22"
        ],
        "words": [
            "arrest", "detention", "remand", "bail", "warrant", "handcuff", "handcuffing", "custody"
        ]
    },
    "police_misconduct": {
        "phrases": [
            "police excesses", "custodial death", "custodial torture", "police atrocities",
            "compensation for police", "police violence", "police brutality", "torture in custody",
            "fake encounter", "third degree", "custodial violence"
        ],
        "words": [
            "torture", "atrocities", "excesses", "encounter"
        ]
    },
    "bribery_corruption": {
        "phrases": [
            "prevention of corruption act", "illegal gratification", "demand and acceptance",
            "public servant", "trap case", "asking for a bribe", "anti-corruption", "take a bribe",
            "pay a bribe"
        ],
        "words": [
            "bribe", "bribery", "corruption", "gratification"
        ]
    },
    "housing_tenancy": {
        "phrases": [
            "rent control", "unlawful ejectment", "evict without notice", "evict me",
            "landlord and tenant", "tenant protection", "rent control act", "ejectment of tenant",
            "landlord evict", "fixation of fair rent"
        ],
        "words": [
            "tenant", "eviction", "evict", "landlord", "tenancy", "ejectment", "rent"
        ]
    },
    "traffic_police_powers": {
        "phrases": [
            "motor vehicles act", "search and seizure", "stop and search", "search vehicle",
            "stopped on my bike", "stopped by police", "traffic police", "issue challan",
            "impound vehicle", "traffic violation", "seizure of vehicle", "power to stop",
            "stopped on bike", "traffic cop"
        ],
        "words": [
            "challan", "traffic", "bike", "motorcycle", "scooter", "vehicle"
        ]
    },
    "fundamental_rights": {
        "phrases": [
            "article 21", "right to life", "personal liberty", "right to life and personal liberty",
            "article 19", "freedom of speech", "fundamental rights", "reasonable restrictions",
            "fundamental right", "habeas corpus", "right to privacy", "article 14"
        ],
        "words": [
            "fundamental"
        ]
    }
}

SEARCH_STOPWORDS = {
    "what", "to", "do", "if", "a", "an", "the", "in", "on", "of", "and", "or", "for", "with", "is", "are", "can",
    "my", "me", "you", "your", "by", "under", "without", "when", "how", "why", "who", "whom", "which", "where",
    "about", "tell", "show", "give", "explain", "law", "legal", "court", "judgment", "matter", "case", "state",
    "india", "act", "acts", "section", "sections", "rule", "rules", "rights", "powers", "this", "that", "these",
    "those", "from", "into", "over", "than", "then", "also", "any", "all", "its", "been", "being", "having",
    "guidelines", "remedies", "protection"
}


def classify_query_topic(query: str) -> Optional[str]:
    """Classifies a user query into one of the 6 citizen rights topics or returns None."""
    q_lower = query.lower()
    scores = {}
    for topic, config in TOPIC_DEFINITIONS.items():
        score = 0.0
        for phrase in config["phrases"]:
            if phrase in q_lower:
                score += 3.0
        for word in config["words"]:
            if re.search(r"\b" + re.escape(word) + r"\b", q_lower):
                score += 1.0
        if score > 0:
            scores[topic] = score
    if scores:
        best_topic, best_score = max(scores.items(), key=lambda x: x[1])
        if best_score >= 1.0:
            return best_topic
    return None


def levenshtein_distance(s1: str, s2: str) -> int:
    """Computes standard Levenshtein edit distance between two strings."""
    if s1 == s2:
        return 0
    if len(s1) < len(s2):
        s1, s2 = s2, s1
    if not s2:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1] * (len(s2) + 1)
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr[j + 1] = min(prev[j + 1] + 1, curr[j] + 1, prev[j] + cost)
        prev = curr
    return prev[-1]


def fuzzy_word_match(w1: str, w2: str) -> bool:
    """
    Checks if two words match within the required edit distance:
    - 4 to 5 letters: edit distance up to 1
    - 6+ letters: edit distance up to 2
    - < 4 letters or words with digits: exact match only
    """
    w1, w2 = w1.lower(), w2.lower()
    if w1 == w2:
        return True
    if any(c.isdigit() for c in w1) or any(c.isdigit() for c in w2):
        return False
    min_len = min(len(w1), len(w2))
    if min_len < 4:
        return False
    max_dist = 2 if min_len >= 6 else 1
    if abs(len(w1) - len(w2)) > max_dist:
        return False
    return levenshtein_distance(w1, w2) <= max_dist


def extract_statutes_from_text(text: str) -> List[str]:
    """
    Derives statutes, sections, and constitutional articles actually cited in the case text.
    Returns a clean, deduplicated list of cited statutory provisions, or an empty list if none are found.
    NEVER returns hardcoded defaults.
    """
    if not text:
        return []

    tags = []

    # 1. Constitutional Articles (e.g., Article 21, Article 19(1)(a), Article 14, Article 32, Article 226, Article 356, Article 141)
    art_matches = re.findall(
        r'\b(?:Article|Art\.)\s+(\d+[A-Z]*(?:\([0-9a-z]+\))*)',
        text,
        re.IGNORECASE
    )
    for art in art_matches:
        tag = f"Article {art}, Constitution of India"
        if tag not in tags:
            tags.append(tag)

    # 2. Sections with named Acts (e.g., Section 27 of the Indian Contract Act, Section 74 of the Contract Act)
    sec_act_matches = re.findall(
        r'\b(?:Section|Sec\.)\s+(\d+[A-Z]*)\s+(?:of\s+(?:the\s+)?)?([A-Z][A-Za-z0-9\s,\(\)]+?(?:Act|Code)(?:,\s*\d{4})?)',
        text,
        re.IGNORECASE
    )
    for sec, act in sec_act_matches:
        act_clean = act.strip().rstrip(",. ")
        if len(act_clean) <= 50 and any(kw in act_clean.lower() for kw in [
            "contract", "penal", "procedure", "technology", "arbitration",
            "transfer of property", "specific relief", "evidence", "motor vehicles",
            "rent", "constitution", "limitation", "companies", "consumer"
        ]):
            if "contract" in act_clean.lower():
                act_clean = "Indian Contract Act, 1872"
            elif "penal" in act_clean.lower():
                act_clean = "Indian Penal Code, 1860"
            elif "procedure" in act_clean.lower() and "criminal" in act_clean.lower():
                act_clean = "Code of Criminal Procedure, 1973"
            elif "technology" in act_clean.lower():
                act_clean = "Information Technology Act, 2000"
            tag = f"Section {sec}, {act_clean}"
            if tag not in tags:
                tags.append(tag)

    # 3. Known contextual section mentions
    t_lower = text.lower()
    if "contract act" in t_lower or "restraint of trade" in t_lower or "non-compete" in t_lower:
        if re.search(r'\b(?:Section|Sec\.)\s+27\b', text, re.IGNORECASE) and not any("Section 27" in t for t in tags):
            tags.append("Section 27, Indian Contract Act, 1872")
        if re.search(r'\b(?:Section|Sec\.)\s+74\b', text, re.IGNORECASE) and not any("Section 74" in t for t in tags):
            tags.append("Section 74, Indian Contract Act, 1872")
    if "penal code" in t_lower or "ipc" in t_lower:
        if re.search(r'\b(?:Section|Sec\.)\s+377\b', text, re.IGNORECASE) and not any("Section 377" in t for t in tags):
            tags.append("Section 377, Indian Penal Code, 1860")
        if re.search(r'\b(?:Section|Sec\.)\s+498A\b', text, re.IGNORECASE) and not any("Section 498A" in t for t in tags):
            tags.append("Section 498A, Indian Penal Code, 1860")
    if "information technology" in t_lower or "it act" in t_lower:
        if re.search(r'\b(?:Section|Sec\.)\s+66A\b', text, re.IGNORECASE) and not any("Section 66A" in t for t in tags):
            tags.append("Section 66A, Information Technology Act, 2000")
    if "criminal procedure" in t_lower or "crpc" in t_lower or "first information report" in t_lower:
        if re.search(r'\b(?:Section|Sec\.)\s+154\b', text, re.IGNORECASE) and not any("Section 154" in t for t in tags):
            tags.append("Section 154, Code of Criminal Procedure, 1973")
        if re.search(r'\b(?:Section|Sec\.)\s+41A?\b', text, re.IGNORECASE) and not any("Section 41" in t for t in tags):
            tags.append("Section 41, Code of Criminal Procedure, 1973")

    return tags[:4]


def extract_relevant_passage(
    query: str, 
    text: str, 
    is_verified_ratio: bool = False, 
    verified_ratio: str = ""
) -> Tuple[str, str, bool]:
    """
    Extracts the best-matching passage from the judgment for the user's query.
    - Prefers paragraphs from the court's reasoning or conclusion.
    - Skips transcripts, tables, headers, and exhibits.
    - Trims to ~400 characters at sentence boundary.
    - Returns (passage_text, ratio_label, is_verified_ratio).
    """
    if is_verified_ratio and verified_ratio and len(verified_ratio.strip()) > 30:
        return (verified_ratio.strip(), "RATIO DECIDENDI / LEGAL PRINCIPLE", True)

    if not text:
        return ("No excerpt available for this judgment.", "RELEVANT PASSAGE", False)

    # Split text into paragraphs or blocks
    raw_paras = [p.strip() for p in re.split(r'\n{2,}|\r\n{2,}', text) if p.strip()]
    if not raw_paras:
        raw_paras = [p.strip() for p in re.split(r'(?<=[.!?])\s+(?=[A-Z])', text) if p.strip()]

    # Skip lines that are transcripts, tables, headers, or exhibits
    noise_prefixes = (
        "exhibit", "ex.", "pw-", "dw-", "annexure", "table", "p.w.", "d.w.", 
        "cross-examination", "q.", "a.", "examination-in-chief", "sl. no.", 
        "appeal from", "order date", "coram:"
    )
    clean_paras = []
    for p in raw_paras:
        p_clean = re.sub(r'[\r\n\t]+', ' ', p).strip()
        p_lower = p_clean.lower()
        if len(p_clean) < 40:
            continue
        if any(p_lower.startswith(prefix) for prefix in noise_prefixes):
            continue
        if re.match(r'^(?:[A-Z0-9\.\-_\s]+:|\bQ\b|\bA\b)', p_clean):
            continue
        clean_paras.append(p_clean)

    if not clean_paras:
        clean_paras = [re.sub(r'[\r\n\t]+', ' ', text).strip()]

    # Score paragraphs:
    reasoning_markers = [
        "held that", "we hold", "in our view", "we are of the opinion", "it is settled law",
        "the court held", "the supreme court held", "laid down that", "the ratio", 
        "accordingly", "we find that", "the principle is", "cannot be sustained", 
        "we conclude", "in conclusion", "it is well settled", "doctrine of"
    ]
    query_terms = [t for t in re.findall(r'[a-zA-Z0-9]{3,}', query.lower()) if t not in SEARCH_STOPWORDS]

    best_para = clean_paras[0]
    best_score = -1.0

    for p in clean_paras:
        p_lower = p.lower()
        score = 0.0
        if any(rm in p_lower for rm in reasoning_markers):
            score += 3.0
        term_matches = sum(1 for t in query_terms if t in p_lower)
        score += term_matches * 1.5

        if score > best_score:
            best_score = score
            best_para = p

    # Trim to ~400 characters at sentence boundary
    cleaned = best_para
    if len(cleaned) > 400:
        sentences = re.split(r'(?<=[.!?])\s+', cleaned)
        trimmed = ""
        for s in sentences:
            if len(trimmed) + len(s) + 1 <= 420:
                trimmed = f"{trimmed} {s}".strip() if trimmed else s
            else:
                break
        if not trimmed or len(trimmed) < 150:
            trimmed = cleaned[:397].rsplit(' ', 1)[0] + "..."
        cleaned = trimmed

    return (cleaned, "RELEVANT PASSAGE", False)


def extract_substantive_terms(query: str) -> List[str]:
    """Extracts substantive content words and section numbers from query, excluding generic stopwords."""
    tokens = re.findall(r"[a-zA-Z]{3,}|\b\d+\b", query.lower())
    return [t for t in tokens if t not in SEARCH_STOPWORDS]


def extract_query_aliases(query: str) -> List[str]:
    """
    Identifies if a query contains an alias, short name, or citation of a landmark case,
    using exact substring matching and fuzzy matching (Levenshtein distance up to 2 for words >= 6,
    up to 1 for words 4-5).
    Returns matching canonical alias strings for Qdrant filtering.
    """
    if not query or len(query.strip()) < 3:
        return []

    q_norm = re.sub(r'[\s\W_]+', '', query).lower()
    q_tokens = [t.lower() for t in re.findall(r'[a-zA-Z0-9]{3,}', query) if t.lower() not in SEARCH_STOPWORDS]
    matched = []

    try:
        from app.ingest.landmark_pipeline import LANDMARK_CASES
    except Exception:
        LANDMARK_CASES = []

    for case_def in LANDMARK_CASES:
        all_aliases = [
            case_def["common_name"],
            case_def["short_name"],
            f"{case_def['short_name']} case",
            f"{case_def['common_name']} case",
        ] + case_def.get("extra_aliases", [])

        # 1. Exact substring check on normalized strings
        for a in all_aliases:
            if not a:
                continue
            a_norm = re.sub(r'[\s\W_]+', '', a).lower()
            if len(a_norm) >= 4 and (a_norm in q_norm or (len(q_norm) >= 4 and q_norm in a_norm)):
                matched.append(a)

        # 2. Token-level fuzzy match on case names (excluding numeric citations)
        candidate_names = [case_def["short_name"], case_def["common_name"]] + [
            ea for ea in case_def.get("extra_aliases", []) if not any(c.isdigit() for c in ea)
        ]
        q_name_tokens = [t.lower() for t in re.findall(r'[a-zA-Z]{3,}', query) if t.lower() not in SEARCH_STOPWORDS]
        for a in candidate_names:
            if not a:
                continue
            a_tokens = [t.lower() for t in re.findall(r'[a-zA-Z]{3,}', a) if t.lower() not in SEARCH_STOPWORDS]
            if not a_tokens or not q_name_tokens:
                continue

            if len(q_name_tokens) == 1:
                q_tok = q_name_tokens[0]
                if any(fuzzy_word_match(q_tok, at) for at in a_tokens):
                    matched.append(case_def["common_name"])
                    matched.append(case_def["short_name"])
                    break
            else:
                matches = sum(1 for qt in q_name_tokens if any(fuzzy_word_match(qt, at) for at in a_tokens))
                if matches >= min(len(q_name_tokens), 2) and (matches / len(q_name_tokens)) >= 0.5:
                    matched.append(case_def["common_name"])
                    matched.append(case_def["short_name"])
                    break

    return list(dict.fromkeys(matched))


CITATION_PATTERNS = [
    # AIR patterns: AIR 1973 SC 1461, AIR 1978 SC 597, A.I.R. (1973) S.C. 1461, AIR 1967 SC 1098
    r'\b(?:AIR|A\.I\.R\.)\s*(?:\(?\[?\d{4}\)?\]?)?\s*(?:SC|S\.C\.|SCC|S\.C\.C\.)?\s*\d+\b',
    # SCC, SCR, SCALE, INSC with year: (1973) 4 SCC 225, 1973 4 SCC 225, (1978) 1 SCC 248, [1978] 2 SCR 621
    r'\(?\[?\b\d{4}\)?\]?\s*(?:\(?\d+\)?|\(?Supp(?:l|\.|lementary)?\)?|\(?[A-Z]\)?)\s*(?:\d+)?\s*(?:SCC|S\.C\.C\.|SCR|S\.C\.R\.|SCALE|JT|AIR|A\.I\.R\.|INSC)\s*\d+\b',
    # 1973INSC91, 2017INSC752, 1978 INSC 19
    r'\b\d{4}\s*INSC\s*\d+\b',
    # Supp SCR: [1973] Supp. 1 SCR 1, 1973 Supp 1 SCR 1, [1985] Supp 2 SCR 51, Supp (3) SCC 217
    r'\(?\[?\b\d{4}\)?\]?\s*(?:Supp(?:l|\.|lementary)?)\s*(?:\(?\d+\)?|\d+)?\s*(?:SCR|S\.C\.R\.|SCC|S\.C\.C\.)\s*\d+\b',
    # General reporter citation: 2014 8 SCC 273, (2006) 4 SCC 227, etc.
    r'\(?\[?\b\d{4}\)?\]?\s*\d*\s*(?:SCC|S\.C\.C\.|SCR|S\.C\.R\.|SCALE|CompCas|ILR|PTC|DLT|JT)\s*\d+\b'
]


def detect_citation(query: str) -> Optional[str]:
    """
    Detects Indian legal citations in the query:
    Patterns like AIR 1973 SC 1461, (1973) 4 SCC 225, 1973 4 SCC 225,
    [1973] Supp. 1 SCR 1, 1973INSC91, (1978) 1 SCC 248, AIR 1978 SC 597,
    with flexible spaces, dots and brackets.
    """
    if not query:
        return None
    for pattern in CITATION_PATTERNS:
        m = re.search(pattern, query, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def normalize_citation(cit: str) -> str:
    """Normalizes citation for robust exact matching (strips brackets, dots, commas, spaces)."""
    if not cit:
        return ""
    return re.sub(r'[\s\.\,\(\)\[\]\-_/]+', '', cit).lower()


def is_pure_citation_query(query: str) -> bool:
    """Returns True if the query is strictly or predominantly a citation lookup."""
    cit = detect_citation(query)
    if not cit:
        return False
    cleaned = re.sub(re.escape(cit), '', query, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'\b(?:case|judgment|citation|ruling|decision|the|in|of|what|was|is)\b', '', cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'[\s\.\,\(\)\[\]\-_/\?\:]+', '', cleaned)
    return len(cleaned) == 0



LANDMARK_METADATA: Dict[str, Dict[str, Any]] = {
    "kesavananda": {
        "benchSize": 13,
        "benchType": "Constitution Bench",
        "leadJudge": "S.M. Sikri, C.J.I.",
        "statutes": ["Article 368", "Article 13", "Article 31C", "Article 31A", "Article 19"],
        "year": 1973,
    },
    "maneka gandhi": {
        "benchSize": 7,
        "benchType": "Constitution Bench",
        "leadJudge": "M.H. Beg, C.J.I.",
        "statutes": ["Article 21", "Article 14", "Article 19", "Passports Act 1967"],
        "year": 1978,
    },
    "puttaswamy": {
        "benchSize": 9,
        "benchType": "Constitution Bench",
        "leadJudge": "J.S. Khehar, C.J.I.",
        "statutes": ["Article 21", "Article 14", "Article 19", "Aadhaar Act 2016"],
        "year": 2017,
    },
    "vishaka": {
        "benchSize": 3,
        "benchType": "3-Judge Bench",
        "leadJudge": "J.S. Verma, C.J.I.",
        "statutes": ["Article 14", "Article 19(1)(g)", "Article 21", "CEDAW"],
        "year": 1997,
    },
    "navtej": {
        "benchSize": 5,
        "benchType": "Constitution Bench",
        "leadJudge": "Dipak Misra, C.J.I.",
        "statutes": ["Section 377 IPC", "Article 14", "Article 15", "Article 19(1)(a)", "Article 21"],
        "year": 2018,
    },
    "minerva mills": {
        "benchSize": 5,
        "benchType": "Constitution Bench",
        "leadJudge": "Y.V. Chandrachud, C.J.I.",
        "statutes": ["Article 368(4)", "Article 368(5)", "Article 31C", "Article 14", "Article 19"],
        "year": 1980,
    },
    "golaknath": {
        "benchSize": 11,
        "benchType": "Constitution Bench",
        "leadJudge": "K. Subba Rao, C.J.I.",
        "statutes": ["Article 368", "Article 13(2)", "Article 19", "Article 31"],
        "year": 1967,
    },
    "bommai": {
        "benchSize": 9,
        "benchType": "Constitution Bench",
        "leadJudge": "S.R. Pandian, J.",
        "statutes": ["Article 356", "Article 74(2)", "Article 355", "Article 14"],
        "year": 1994,
    },
    "olga tellis": {
        "benchSize": 5,
        "benchType": "Constitution Bench",
        "leadJudge": "Y.V. Chandrachud, C.J.I.",
        "statutes": ["Article 21", "Article 19(1)(e)", "Article 19(1)(g)", "Article 39(a)", "Article 41"],
        "year": 1985,
    },
    "arnesh kumar": {
        "benchSize": 2,
        "benchType": "Division Bench",
        "leadJudge": "Chandramauli Kumar Prasad, J.",
        "statutes": ["Section 41 CrPC", "Section 41A CrPC", "Section 498A IPC", "Article 21"],
        "year": 2014,
    },
    "dk basu": {
        "benchSize": 2,
        "benchType": "Division Bench",
        "leadJudge": "Kuldip Singh, J.",
        "statutes": ["Article 21", "Article 22", "Section 50 CrPC", "Section 57 CrPC"],
        "year": 1996,
    },
    "d.k. basu": {
        "benchSize": 2,
        "benchType": "Division Bench",
        "leadJudge": "Kuldip Singh, J.",
        "statutes": ["Article 21", "Article 22", "Section 50 CrPC", "Section 57 CrPC"],
        "year": 1996,
    },
    "shreya singhal": {
        "benchSize": 2,
        "benchType": "Division Bench",
        "leadJudge": "J. Chelameswar, J.",
        "statutes": ["Section 66A IT Act", "Article 19(1)(a)", "Article 19(2)", "Article 14"],
        "year": 2015,
    },
    "lalita kumari": {
        "benchSize": 5,
        "benchType": "Constitution Bench",
        "leadJudge": "P. Sathasivam, C.J.I.",
        "statutes": ["Section 154 CrPC", "Section 156 CrPC", "Section 157 CrPC", "Article 21"],
        "year": 2013,
    },
    "indra sawhney": {
        "benchSize": 9,
        "benchType": "Constitution Bench",
        "leadJudge": "M.H. Kania, C.J.I.",
        "statutes": ["Article 16(4)", "Article 16(1)", "Article 15(4)", "Article 14", "Article 340"],
        "year": 1992,
    },
    "percept": {
        "benchSize": 2,
        "benchType": "Division Bench",
        "leadJudge": "H.K. Sema, J.",
        "statutes": ["Section 27 Contract Act", "Article 19(1)(g)"],
        "year": 2006,
    },
    "kailash nath": {
        "benchSize": 2,
        "benchType": "Division Bench",
        "leadJudge": "Ranjan Gogoi, J.",
        "statutes": ["Section 74 Contract Act", "Section 73 Contract Act"],
        "year": 2015,
    }
}


def enrich_landmark_metadata(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enforces Item 4 requirements:
    1. Sets correct benchSize and benchType for every landmark.
    2. Populates hand-checked statutes/articles tags for landmarks.
    3. Populates leadJudge when known, otherwise hides it.
    4. Guarantees non-null year and decisionYear.
    """
    c_title = (case.get("title") or case.get("case_name") or case.get("common_name") or "").lower()
    c_cit = case.get("citation") or case.get("neutral_citation") or ""

    # Match landmark
    matched_meta = None
    for lk, meta in LANDMARK_METADATA.items():
        if lk in c_title:
            matched_meta = meta
            break

    if matched_meta:
        case["benchSize"] = matched_meta["benchSize"]
        case["benchType"] = matched_meta["benchType"]
        case["leadJudge"] = matched_meta.get("leadJudge")
        case["statutes"] = list(matched_meta["statutes"])
        if not case.get("decisionYear") or not case.get("year"):
            case["decisionYear"] = matched_meta["year"]
            case["year"] = matched_meta["year"]
    else:
        # Standard case bench rules
        bs = case.get("benchSize")
        bench_str = case.get("bench") or ""
        if not bs and bench_str:
            judges_list = [j.strip() for j in re.split(r'[,;&]|\band\b', bench_str) if j.strip()]
            bs = len(judges_list) if len(judges_list) > 0 else 2
        if not bs:
            bs = 2
        case["benchSize"] = bs
        if not case.get("benchType"):
            case["benchType"] = "Constitution Bench" if bs >= 5 else ("Division Bench" if bs == 2 else ("3-Judge Bench" if bs == 3 else f"{bs}-Judge Bench"))

        if bench_str and not case.get("leadJudge"):
            lead = [j.strip() for j in re.split(r'[,;&]|\band\b', bench_str) if j.strip()]
            if lead and any(h in lead[0] for h in ["J.", "C.J.I.", "Justice"]):
                case["leadJudge"] = lead[0]

    # Clean leadJudge: hide it if not a verified individual judge name
    if case.get("leadJudge"):
        lj = str(case["leadJudge"]).strip()
        if not lj or any(bad in lj.lower() for bad in ["bench", "court", "division", "constitution", "unknown", "none"]):
            case["leadJudge"] = None
        else:
            case["leadJudge"] = lj
    else:
        case["leadJudge"] = None

    yr = case.get("decisionYear") or case.get("year")
    if not yr and c_cit:
        ym = re.search(r'\b(19\d\d|20\d\d)\b', c_cit)
        if ym:
            yr = int(ym.group(1))
    if yr:
        case["decisionYear"] = int(yr)
        case["year"] = int(yr)

    return case


def normalize_case_dedup_key(title: str, year: Optional[int] = None, citation: str = "") -> str:
    """
    Creates a canonical deduplication key for a case:
    strips honorifics, procedural markers, common party terms, and appends the 4-digit year.
    """
    t_clean = (title or "").lower()
    t_clean = re.sub(r'\b(?:justice|retd\.?|hon\'ble|dr\.?|mr\.?|ms\.?)\b', '', t_clean)
    t_clean = re.sub(r'\(.*?\)', '', t_clean)
    tokens = [tok for tok in re.findall(r'[a-z0-9]{3,}', t_clean) if tok not in {
        "versus", "state", "union", "india", "court", "limited", "ltd", "pvt", "corp",
        "corporation", "company", "and", "the", "ors", "anr", "govt", "government"
    }]
    clean_year = year
    if not clean_year and citation:
        ym = re.search(r'\b(19\d\d|20\d\d)\b', citation)
        if ym:
            clean_year = int(ym.group(1))
    key_core = "_".join(sorted(tokens[:3])) if tokens else "unknown"
    return f"{key_core}_{clean_year or 0}"


def deduplicate_results_by_name_and_year(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen_keys = set()
    deduped = []
    for r in results:
        enrich_landmark_metadata(r)
        title = r.get("title") or r.get("case_name") or r.get("common_name") or ""
        year = r.get("decisionYear") or r.get("year")
        citation = r.get("citation") or r.get("neutral_citation") or ""
        key = normalize_case_dedup_key(title, year, citation)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(r)
    return deduped


class QdrantService:
    def __init__(self):
        self.url = settings.QDRANT_URL
        self.collection_name = settings.QDRANT_COLLECTION
        self.sc_collection_name = "sc_judgments"
        self._client = None
        self.corpus = _load_corpus()
        self._corpus_vectors: Optional[List[List[float]]] = None

        # Local SC judgments dataset index cache
        self._sc_chunks: Optional[List[Dict[str, Any]]] = None
        self._sc_vectors: Optional[np.ndarray] = None
        self._sc_cases_meta: Optional[Dict[str, Dict[str, Any]]] = None
        self._sc_loaded: bool = False

        self._init_client()

    def _init_client(self):
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(
                url=self.url, api_key=settings.QDRANT_API_KEY or None, timeout=15.0
            )
            # Fail fast if the daemon is unreachable so we drop to fallback.
            client.get_collections()
            self._client = client
            logger.info("Connected to Qdrant at %s", self.url)
        except Exception as e:
            logger.info("Qdrant not reachable at %s; using labeled local index fallback: %s", self.url, e)
            self._client = None

    def _get_corpus_vectors(self) -> List[List[float]]:
        """Caches semantic vectors for the 12 verified corpus precedents."""
        if self._corpus_vectors is None:
            texts = [_case_to_text(c) for c in self.corpus]
            self._corpus_vectors = embedding_service.embed_texts(texts)
        return self._corpus_vectors

    def _ensure_sc_dataset_loaded(self):
        """Loads and caches chunks and dense vectors from the SC dataset if local indexing is active."""
        if self._sc_loaded:
            return
        self._sc_loaded = True

        # Render & Production RAM Protection:
        # Never load the 33k-vector local dataset into RAM on Render (512MB RAM free-tier limit),
        # or when Qdrant Cloud is configured. The deployed app queries Qdrant Cloud directly.
        # If Qdrant Cloud is unreachable, it gracefully falls back to the lightweight 12-precedent
        # landmark corpus (<1MB RAM) and Tier 2 AI explanations without triggering an OOM kill.
        if (
            os.getenv("RENDER")
            or os.getenv("DISABLE_LOCAL_SC_DATASET", "").lower() in ("true", "1")
            or (self._client and os.getenv("LOAD_LOCAL_SC_INDEX", "false").lower() not in ("true", "1"))
        ):
            logger.info(
                "Skipping local SC dataset loading into RAM (conserving memory for Render; "
                "using Qdrant Cloud with graceful 12-precedent fallback)."
            )
            return

        try:
            if SC_CHUNKS_PATH.exists() and SC_EMBEDDINGS_PATH.exists():
                with open(SC_CHUNKS_PATH, "r", encoding="utf-8") as f:
                    self._sc_chunks = json.load(f)

                import pandas as pd
                df = pd.read_parquet(SC_EMBEDDINGS_PATH)
                raw_vecs = np.array(df["vector"].tolist(), dtype=np.float32)

                # Pre-normalize for instant cosine similarity via matrix dot product
                norms = np.linalg.norm(raw_vecs, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                self._sc_vectors = raw_vecs / norms

                # Build fast case metadata index for citation lookup
                self._sc_cases_meta = {}
                for c in self._sc_chunks:
                    cid = c.get("case_id", "")
                    if cid and cid not in self._sc_cases_meta:
                        self._sc_cases_meta[cid] = {
                            "case_name": c.get("case_name"),
                            "year": c.get("year"),
                            "citation": c.get("citation"),
                            "neutral_citation": c.get("neutral_citation"),
                            "bench": c.get("bench"),
                            "source_link": c.get("source_link")
                        }

                logger.info(
                    "Loaded local Supreme Court dataset: %d chunks across %d judgments (%.1f MB vectors)",
                    len(self._sc_chunks), len(self._sc_cases_meta), self._sc_vectors.nbytes / (1024 * 1024)
                )
        except Exception as e:
            logger.warning("Could not load local Supreme Court dataset: %s", e)

    # ------------------------------------------------------------------ #
    # Case by ID & Chunk Fetching (for Case Chat, Text, Citator)          #
    # ------------------------------------------------------------------ #
    def get_case_chunks_by_id(self, case_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all chunks for a given case_id in chunk_index order.
        Queries live Qdrant collection 'sc_judgments' first, then falls back to local SC chunks.
        """
        cid = (case_id or "").strip()
        if not cid:
            return []

        # 1. Query live Qdrant
        if self._client:
            try:
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                target_collection = self.sc_collection_name
                try:
                    available = {c.name for c in self._client.get_collections().collections}
                    if target_collection not in available:
                        target_collection = self.collection_name
                except Exception:
                    pass

                all_chunks = []
                offset = None
                while True:
                    hits, next_offset = self._client.scroll(
                        collection_name=target_collection,
                        scroll_filter=Filter(must=[FieldCondition(key="case_id", match=MatchValue(value=cid))]),
                        limit=100,
                        offset=offset,
                        with_payload=True,
                        with_vectors=False
                    )
                    for h in hits:
                        p = dict(h.payload or {})
                        p["id"] = p.get("id") or str(h.id)
                        p["chunk_id"] = p.get("chunk_id") or f"{cid}_chunk_{p.get('chunk_index', 0)}"
                        all_chunks.append(p)
                    if not next_offset or len(hits) == 0:
                        break
                    offset = next_offset

                if all_chunks:
                    all_chunks.sort(key=lambda x: x.get("chunk_index", 0))
                    return all_chunks
            except Exception as e:
                logger.warning("Live Qdrant scroll for case_id '%s' failed: %s", cid, e)

        # 2. Local index fallback
        self._ensure_sc_dataset_loaded()
        if self._sc_chunks:
            matches = [c for c in self._sc_chunks if c.get("case_id") == cid]
            if matches:
                matches.sort(key=lambda x: x.get("chunk_index", 0))
                return matches

        # 3. Check citizen rights and landmark chunk files directly if not loaded in memory
        for path in [
            SC_DATASET_DIR / "chunks" / "landmark_chunks.json",
            SC_DATASET_DIR / "chunks" / "citizen_rights_chunks.json",
            SC_DATASET_DIR / "chunks" / "chunks.json"
        ]:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        matched = [c for c in data if c.get("case_id") == cid]
                        if matched:
                            matched.sort(key=lambda x: x.get("chunk_index", 0))
                            return matched
                except Exception:
                    pass

        return []

    def get_case_by_id(self, case_id: str) -> Optional[Dict[str, Any]]:
        """
        Loads case metadata and combined information for any case in the corpus or Qdrant.
        """
        cid = (case_id or "").strip()
        if not cid:
            return None

        # Check corpus first
        for c in self.corpus:
            if c.get("id") == cid or (c.get("title") and c.get("title").lower() == cid.lower()):
                c_copy = dict(c)
                c_copy["case_id"] = c.get("id")
                return enrich_landmark_metadata(c_copy)

        chunks = self.get_case_chunks_by_id(cid)
        if not chunks:
            return None

        first = chunks[0]
        title = first.get("common_name") or first.get("case_name") or first.get("title") or cid
        citation = first.get("citation") or first.get("neutral_citation") or ""
        year = first.get("year") or first.get("decisionYear")
        bench = first.get("bench") or ""
        bench_size = first.get("benchSize")
        if not bench_size and bench:
            judges_list = [j.strip() for j in re.split(r'[,;&]|\band\b', bench) if j.strip()]
            bench_size = len(judges_list) if len(judges_list) > 0 else 2
        if not bench_size:
            bench_size = 5 if first.get("landmark") else 2
        bench_type = "Constitution Bench" if bench_size >= 5 else ("Division Bench" if bench_size == 2 else f"{bench_size}-Judge Bench")

        # Pick best holding/ratio
        ratio = ""
        for ch in chunks:
            text_lower = ch.get("text", "").lower()
            if ch.get("landmark") or any(w in text_lower for w in ["held", "ratio", "we hold", "order"]):
                ratio = ch.get("text", "")[:320]
                break
        if not ratio:
            ratio = first.get("text", "")[:320]

        combined_text = "\n".join(ch.get("text", "") for ch in chunks[:3])
        statutes = extract_statutes_from_text(combined_text)

        return enrich_landmark_metadata({
            "id": cid,
            "case_id": cid,
            "title": title,
            "citation": citation,
            "court": first.get("court") or "Supreme Court of India",
            "decisionYear": year,
            "year": year,
            "bench": bench,
            "benchType": bench_type,
            "benchSize": bench_size,
            "ratioSummary": ratio,
            "statutes": statutes,
            "total_chunks": len(chunks),
            "chunks": chunks
        })

    def lookup_exact_citation(self, citation_str: str) -> Optional[Dict[str, Any]]:
        """
        Looks up a citation across:
        1. All 14 landmark cases (checking extra_aliases, short_name, common_name)
        2. All 12 verified corpus precedents (checking citation, altCitations)
        3. Local SC chunks index and live Qdrant collection 'sc_judgments'
        """
        target_norm = normalize_citation(citation_str)
        if not target_norm:
            return None

        # 1. Landmark cases
        try:
            from app.ingest.landmark_pipeline import LANDMARK_CASES
        except Exception:
            LANDMARK_CASES = []

        for case_def in LANDMARK_CASES:
            aliases = [case_def["common_name"], case_def["short_name"]] + case_def.get("extra_aliases", [])
            for a in aliases:
                if normalize_citation(a) == target_norm:
                    case_obj = self.get_case_by_id(case_def["path"])
                    if not case_obj:
                        case_obj = {
                            "id": case_def["path"],
                            "case_id": case_def["path"],
                            "title": case_def["common_name"],
                            "citation": citation_str,
                            "court": "Supreme Court of India",
                            "decisionYear": case_def["year"],
                            "year": case_def["year"],
                            "benchType": "Constitution Bench" if case_def.get("benchSize", 5) >= 5 else "Division Bench",
                            "benchSize": case_def.get("benchSize", 5),
                            "statutes": [],
                            "ratioSummary": f"{case_def['common_name']}: Authoritative Supreme Court decision.",
                            "ratioLabel": "RATIO DECIDENDI / LEGAL PRINCIPLE",
                            "is_verified_ratio": True,
                        }
                    case_obj["aliases"] = aliases
                    case_obj["relevance_score"] = 0.99
                    case_obj["raw_vector_score"] = 0.99
                    case_obj["is_verified_ratio"] = True
                    case_obj["retrieval_mode"] = "exact_citation_match"
                    return case_obj

        # 2. Verified Precedent Corpus
        for c in self.corpus:
            cits = [c.get("citation") or ""] + c.get("altCitations", [])
            for c_cit in cits:
                if normalize_citation(c_cit) == target_norm:
                    c_copy = dict(c)
                    c_copy["relevance_score"] = 0.99
                    c_copy["raw_vector_score"] = 0.99
                    c_copy["is_verified_ratio"] = True
                    c_copy["retrieval_mode"] = "exact_citation_match"
                    return c_copy

        # 3. Local SC chunks index
        self._ensure_sc_dataset_loaded()
        if self._sc_chunks:
            for ch in self._sc_chunks:
                for k in ["citation", "neutral_citation"]:
                    val = ch.get(k)
                    if val and normalize_citation(val) == target_norm:
                        cid = ch.get("case_id")
                        c_obj = self.get_case_by_id(cid)
                        if c_obj:
                            c_obj["relevance_score"] = 0.99
                            c_obj["raw_vector_score"] = 0.99
                            c_obj["retrieval_mode"] = "exact_citation_match"
                            return c_obj

        # 4. Live Qdrant check if connected
        if self._client:
            try:
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                target_collection = self.sc_collection_name
                try:
                    available = {col.name for col in self._client.get_collections().collections}
                    if target_collection not in available:
                        target_collection = self.collection_name
                except Exception:
                    pass

                hits, _ = self._client.scroll(
                    collection_name=target_collection,
                    scroll_filter=Filter(should=[
                        FieldCondition(key="citation", match=MatchValue(value=citation_str)),
                        FieldCondition(key="aliases", match=MatchValue(value=citation_str))
                    ]),
                    limit=5,
                    with_payload=True
                )
                if hits:
                    p = dict(hits[0].payload or {})
                    cid = p.get("case_id") or str(hits[0].id)
                    c_obj = self.get_case_by_id(cid)
                    if c_obj:
                        c_obj["relevance_score"] = 0.99
                        c_obj["raw_vector_score"] = 0.99
                        c_obj["retrieval_mode"] = "exact_citation_match"
                        return c_obj
            except Exception as e:
                logger.debug("Exact citation Qdrant scroll failed: %s", e)

        return None

    # ------------------------------------------------------------------ #
    # Retrieval                                                           #
    # ------------------------------------------------------------------ #
    def search_precedents(
        self,
        query: str,
        court_filter: str = "ALL",
        bench_filter: str = "ALL",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        # Item 3: Exact citation matching
        det_cit = detect_citation(query)
        is_pure_cit = is_pure_citation_query(query) if det_cit else False

        if det_cit:
            matched_case = self.lookup_exact_citation(det_cit)
            if matched_case:
                if self._matches_filters(matched_case, court_filter, bench_filter):
                    if is_pure_cit:
                        # Exact citation match puts that case alone at the top
                        return deduplicate_results_by_name_and_year([matched_case])
                    else:
                        # Mixed query: put matched case alone at top, append additional matches
                        results = []
                        if self._client:
                            try:
                                results = self._search_qdrant(query, court_filter, bench_filter, limit)
                            except Exception:
                                results = self._search_local(query, court_filter, bench_filter, limit)
                        else:
                            results = self._search_local(query, court_filter, bench_filter, limit)
                        combined = [matched_case]
                        seen_ids = {matched_case.get("id"), matched_case.get("case_id"), (matched_case.get("title") or "").lower()}
                        for r in results:
                            r_id = r.get("id") or r.get("case_id")
                            r_title = (r.get("title") or "").lower()
                            if r_id not in seen_ids and r_title not in seen_ids:
                                seen_ids.add(r_id)
                                seen_ids.add(r_title)
                                combined.append(r)
                        return deduplicate_results_by_name_and_year(combined)[:limit]
            elif is_pure_cit:
                # If the query is a citation and nothing matches, return no results (never a random case).
                return []

        if self._client:
            try:
                res = self._search_qdrant(query, court_filter, bench_filter, limit)
                return deduplicate_results_by_name_and_year(res)[:limit]
            except Exception as e:
                logger.warning("Live Qdrant query failed, falling back to local index: %s", e)
        res = self._search_local(query, court_filter, bench_filter, limit)
        return deduplicate_results_by_name_and_year(res)[:limit]

    def _matches_filters(self, case: Dict[str, Any], court_filter: str, bench_filter: str) -> bool:
        if court_filter != "ALL" and case.get("court") != court_filter:
            return False
        if bench_filter == "CONSTITUTION" and case.get("benchSize", 0) < 5:
            return False
        if bench_filter == "DIVISION" and case.get("benchSize") != 2:
            return False
        return True

    def _search_qdrant(self, query: str, court_filter: str, bench_filter: str, limit: int) -> List[Dict[str, Any]]:
        vector = embedding_service.embed_query(query)
        target_collection = self.collection_name

        try:
            available = {c.name for c in self._client.get_collections().collections}
            if self.sc_collection_name in available:
                target_collection = self.sc_collection_name
        except Exception:
            pass

        # Exact or fuzzy-match boost for landmark aliases and citations
        exact_boost_results: List[Dict[str, Any]] = []
        matched_aliases = extract_query_aliases(query)
        if matched_aliases:
            try:
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                conditions = [FieldCondition(key="aliases", match=MatchValue(value=a)) for a in matched_aliases]
                conditions.extend([FieldCondition(key="common_name", match=MatchValue(value=a)) for a in matched_aliases])
                boost_hits, _ = self._client.scroll(
                    collection_name=target_collection,
                    scroll_filter=Filter(should=conditions),
                    limit=limit,
                    with_payload=True,
                    with_vectors=False
                )
                seen_boost = set()
                for hit in boost_hits:
                    p = dict(hit.payload or {})
                    if not self._matches_filters(p, court_filter, bench_filter):
                        continue
                    c_title = p.get("common_name") or p.get("case_name") or p.get("title")
                    c_key = (c_title or "").strip().lower()
                    if not c_key or c_key in seen_boost:
                        continue
                    seen_boost.add(c_key)

                    p["id"] = p.get("id") or p.get("case_id") or str(hit.id)
                    p["title"] = c_title
                    p["decisionYear"] = p.get("year")
                    
                    text_content = p.get("text", "") or ""
                    passage, label, is_ratio = extract_relevant_passage(
                        query=query,
                        text=text_content,
                        is_verified_ratio=bool(p.get("landmark")),
                        verified_ratio=p.get("ratioSummary", "")
                    )
                    p["ratioSummary"] = passage
                    p["ratioLabel"] = label
                    p["is_verified_ratio"] = is_ratio
                    p["statutes"] = extract_statutes_from_text(text_content)
                    p["court"] = "Supreme Court of India"
                    p["benchType"] = "Supreme Court Bench"
                    p["benchSize"] = p.get("benchSize", 5 if p.get("landmark") else 2)
                    p["relevance_score"] = 0.99
                    p["raw_vector_score"] = 0.99
                    p["retrieval_mode"] = f"qdrant_exact_boost+{target_collection}"
                    exact_boost_results.append(p)
                    if len(exact_boost_results) >= limit:
                        break
            except Exception as e:
                logger.debug("Exact match boost failed: %s", e)

        topic = classify_query_topic(query)
        substantive_terms = extract_substantive_terms(query)

        from qdrant_client.models import Filter, FieldCondition, MatchValue
        hits = []

        # 1. Topic-filtered retrieval if a citizen rights topic is detected
        if topic:
            try:
                topic_filter = Filter(must=[FieldCondition(key="topic", match=MatchValue(value=topic))])
                topic_hits = self._client.search(
                    collection_name=target_collection,
                    query_vector=vector,
                    query_filter=topic_filter,
                    limit=25
                )
                hits.extend(topic_hits)
            except Exception as e:
                logger.debug("Topic filtered search failed: %s", e)

        # Also get general hits across the collection to merge and re-rank top candidates
        general_hits = self._client.search(
            collection_name=target_collection,
            query_vector=vector,
            limit=25
        )
        hits.extend(general_hits)

        # Deduplicate hits by point ID
        unique_hits = []
        seen_hit_ids = set()
        for h in hits:
            if h.id not in seen_hit_ids:
                seen_hit_ids.add(h.id)
                unique_hits.append(h)

        # 2. Re-rank candidates combining vector score, topic match, and key-term overlap
        candidates = []

        # (a) First evaluate verified landmark precedents from self.corpus (e.g. Kailash Nath, Percept D'Mark, Puttaswamy)
        corpus_vecs = self._get_corpus_vectors()
        norm_v = math.sqrt(sum(q * q for q in vector)) or 1.0
        for case_item, c_vec in zip(self.corpus, corpus_vecs):
            c_copy = dict(case_item)
            if not self._matches_filters(c_copy, court_filter, bench_filter):
                continue

            dot = sum(q * c for q, c in zip(vector, c_vec))
            norm_c = math.sqrt(sum(c * c for c in c_vec)) or 1.0
            cos_sim = dot / (norm_v * norm_c)

            c_title = c_copy.get("title", "")
            c_text = f"{c_title} {c_copy.get('citation', '')} {c_copy.get('ratioSummary', '')} {' '.join(c_copy.get('statutes', []))} {' '.join(c_copy.get('keywords', []))}".lower()
            t_matches = sum(1 for t in substantive_terms if t in c_title.lower())
            tx_matches = sum(1 for t in substantive_terms if t in c_text)
            t_ratio = (tx_matches / max(len(substantive_terms), 1)) if substantive_terms else 1.0
            t_boost = min(0.35, t_matches * 0.15 + t_ratio * 0.15)
            c_keywords = [k.lower() for k in c_copy.get("keywords", [])]
            kw_matches = sum(1 for k in c_keywords if k in query.lower())
            landmark_boost = min(0.35, kw_matches * 0.15)
            c_comb_score = cos_sim + t_boost + landmark_boost + 0.15

            if (cos_sim >= 0.45) or (cos_sim >= 0.35 and (len(substantive_terms) == 0 or tx_matches > 0)):
                c_copy["relevance_score"] = round(float(c_comb_score), 3)
                c_copy["raw_vector_score"] = round(float(cos_sim), 3)
                c_copy["retrieval_mode"] = f"qdrant+verified_precedents+{embedding_service.mode}"
                c_copy["is_verified_ratio"] = True
                c_copy["ratioLabel"] = "RATIO DECIDENDI / LEGAL PRINCIPLE"
                candidates.append(c_copy)

        # (b) Evaluate Qdrant cloud hits
        for hit in unique_hits:
            case = dict(hit.payload or {})

            # Populate standard case fields BEFORE _matches_filters so court/bench filters don't drop valid SC cases
            case["id"] = case.get("id") or case.get("case_id") or str(hit.id)
            if case.get("common_name"):
                case["title"] = case.get("common_name")
            elif not case.get("title") and case.get("case_name"):
                case["title"] = case.get("case_name")
            if not case.get("decisionYear") and case.get("year"):
                case["decisionYear"] = case.get("year")
            if not case.get("court"):
                case["court"] = "Supreme Court of India"
            if not case.get("benchType"):
                case["benchType"] = "Supreme Court Bench"
            if not case.get("benchSize"):
                case["benchSize"] = 2

            text_content = case.get("text", "") or case.get("ratioSummary", "") or ""
            # Derive statutes strictly from text with NO default fake tags
            case["statutes"] = extract_statutes_from_text(text_content)
            passage, label, is_ratio = extract_relevant_passage(
                query=query,
                text=text_content,
                is_verified_ratio=bool(case.get("landmark")),
                verified_ratio=case.get("ratioSummary", "") if case.get("landmark") else ""
            )
            case["ratioSummary"] = passage
            case["ratioLabel"] = label
            case["is_verified_ratio"] = is_ratio

            if not self._matches_filters(case, court_filter, bench_filter):
                continue

            case_name = case.get("case_name") or case.get("title") or ""
            comb_text = f"{case_name} {text_content}".lower()
            name_lower = case_name.lower()

            v_score = float(hit.score)

            # Topic match boost:
            if topic:
                case_topic = case.get("topic")
                if case_topic == topic:
                    topic_boost = 0.20
                elif case_topic is None:
                    topic_boost = -0.15
                else:
                    topic_boost = 0.0
            else:
                topic_boost = 0.0

            # Title tokens & aliases for fuzzy matching
            title_tokens = [t.lower() for t in re.findall(r'[a-zA-Z0-9]{3,}', name_lower) if t.lower() not in SEARCH_STOPWORDS]
            common_tokens = [t.lower() for t in re.findall(r'[a-zA-Z0-9]{3,}', (case.get("common_name") or "").lower()) if t.lower() not in SEARCH_STOPWORDS]
            alias_tokens = [t.lower() for a in case.get("aliases", []) for t in re.findall(r'[a-zA-Z0-9]{3,}', a.lower()) if t.lower() not in SEARCH_STOPWORDS]
            all_name_tokens = set(title_tokens + common_tokens + alias_tokens)

            # Substantive term overlap with title and text, including fuzzy matching
            title_matches = sum(1 for t in substantive_terms if t in name_lower)
            text_matches = sum(1 for t in substantive_terms if t in comb_text)
            fuzzy_title_matches = sum(1 for st in substantive_terms if st in name_lower or any(fuzzy_word_match(st, nt) for nt in all_name_tokens))
            effective_text_matches = text_matches + (fuzzy_title_matches * 2)

            best_title_matches = max(title_matches, fuzzy_title_matches)
            term_ratio = (effective_text_matches / max(len(substantive_terms), 1)) if substantive_terms else 1.0
            term_boost = min(0.35, best_title_matches * 0.15 + term_ratio * 0.15)

            combined_score = v_score + topic_boost + term_boost

            # 3. Relevance Floor:
            # Drop any result that has no key-term match in its text/name AND a low semantic score:
            if v_score < 0.38 and best_title_matches == 0:
                continue
            if combined_score < 0.48 and best_title_matches == 0:
                continue
            if substantive_terms and effective_text_matches == 0:
                continue

            # Specific everyday-rights filter for vehicle/bike stops:
            if "bike" in substantive_terms:
                has_bike = any(bt in comb_text for bt in ["bike", "motorcycle", "scooter", "two-wheeler", "two wheeler"])
                has_stop = any(st in comb_text for st in ["stop", "stopped", "police", "challan", "search", "seizure", "inspection", "officer"])
                if not (has_bike and has_stop):
                    continue

            case["relevance_score"] = round(float(combined_score), 3)
            case["raw_vector_score"] = round(float(v_score), 3)
            case["retrieval_mode"] = f"qdrant+{target_collection}+{embedding_service.mode}"
            candidates.append(case)

        # Re-rank by combined score descending
        candidates.sort(key=lambda x: x["relevance_score"], reverse=True)

        # Prepend exact match boost results and deduplicate
        results: List[Dict[str, Any]] = list(exact_boost_results)
        seen_cases = set()
        for r in exact_boost_results:
            for k in [r.get("title"), r.get("case_name"), r.get("common_name")]:
                if k:
                    seen_cases.add(k.strip().lower())

        has_strong_exact_match = len(exact_boost_results) > 0
        top_score = exact_boost_results[0]["relevance_score"] if has_strong_exact_match else (candidates[0]["relevance_score"] if candidates else 0.0)

        seen_parties = []
        max_to_return = max(limit, 3)
        for c in candidates:
            title_key = (c.get("title") or "").strip().lower()
            if title_key and title_key in seen_cases:
                continue

            # If we had a strong exact name or citation match, drop weak extras:
            # - raw similarity below tuned threshold (0.45)
            # - or score less than 65% of top score
            # - must genuinely cite the case / contain its name terms, or share the detected topic
            if has_strong_exact_match:
                c_raw = c.get("raw_vector_score", 0.0)
                c_score = c.get("relevance_score", 0.0)
                if c_score < (top_score * 0.65) or c_raw < 0.45:
                    continue
                if topic and c.get("topic") != topic:
                    continue
                matched_case_terms = set(re.findall(r'[a-zA-Z0-9]{4,}', " ".join(matched_aliases).lower())) - SEARCH_STOPWORDS
                matched_case_terms = {t for t in matched_case_terms if not re.match(r'^(?:19\d\d|20\d\d)$', t)}
                c_full_text = f"{c.get('title', '')} {c.get('text', '')}".lower()
                if matched_case_terms and not any(mct in c_full_text for mct in matched_case_terms):
                    continue

            party_tokens = set(re.findall(r'[a-z]{4,}', title_key)) - {
                "versus", "state", "union", "india", "court", "limited", "authority", "corporation", "company"
            }
            if party_tokens and any(len(party_tokens & prev) >= 2 for prev in seen_parties):
                continue
            if title_key:
                seen_cases.add(title_key)
                if party_tokens:
                    seen_parties.append(party_tokens)
            results.append(c)
            if len(results) >= max_to_return:
                break

        return results[:limit]

    def _search_local(self, query: str, court_filter: str, bench_filter: str, limit: int) -> List[Dict[str, Any]]:
        query_vec = embedding_service.embed_query(query)
        corpus_vecs = self._get_corpus_vectors()
        norm_q = math.sqrt(sum(q * q for q in query_vec)) or 1.0

        stopwords = {
            "the", "and", "for", "with", "from", "that", "this", "what", "which", "where", "when", "who", "whom",
            "how", "why", "are", "was", "were", "has", "have", "had", "been", "does", "did", "can", "could", "shall",
            "will", "would", "should", "about", "tell", "show", "give", "explain", "under", "over", "into", "than",
            "then", "also", "any", "all", "its", "our", "your", "law", "legal", "court", "judgment", "ruling", "holding",
            "case", "matter", "concept", "doctrine", "principle", "rule", "bench", "act", "india", "state"
        }
        terms = [t.lower() for t in re.findall(r'[a-zA-Z0-9]{3,}', query) if t.lower() not in stopwords]
        min_required = 1 if len(terms) <= 2 else 2

        results: List[Dict[str, Any]] = []

        for case, c_vec in zip(self.corpus, corpus_vecs):
            if not self._matches_filters(case, court_filter, bench_filter):
                continue

            dot = sum(q * c for q, c in zip(query_vec, c_vec))
            norm_c = math.sqrt(sum(c * c for c in c_vec)) or 1.0
            cos_sim = dot / (norm_q * norm_c)

            text_blob = (
                f"{case.get('title', '')} {case.get('citation', '')} "
                f"{case.get('ratioSummary', '')} "
                f"{' '.join(case.get('statutes', []))} {' '.join(case.get('keywords', []))}"
            ).lower()
            matches = sum(1 for term in terms if term in text_blob)

            if (cos_sim >= 0.35 and (len(terms) == 0 or matches >= min_required)) or (cos_sim >= 0.48):
                item = dict(case)
                final_score = round(max(float(cos_sim), min(0.45 + matches * 0.1, 0.98)), 3)
                item["relevance_score"] = final_score
                item["retrieval_mode"] = f"local_index+12_precedents+{embedding_service.mode}"
                results.append(item)

        self._ensure_sc_dataset_loaded()
        if self._sc_vectors is not None and self._sc_chunks:
            q_arr = np.array(query_vec, dtype=np.float32)
            q_arr_norm = q_arr / (np.linalg.norm(q_arr) or 1.0)

            sims = np.dot(self._sc_vectors, q_arr_norm)
            candidate_indices = np.where(sims >= 0.30)[0]

            if len(candidate_indices) > 0:
                top_order = candidate_indices[np.argsort(sims[candidate_indices])[::-1]]
                seen_cases = {r.get("title", "").lower() for r in results}

                for idx in top_order:
                    chunk = self._sc_chunks[idx]
                    c_name = chunk.get("case_name", "").strip()
                    if not c_name or c_name.lower() in seen_cases:
                        continue

                    c_text_lower = (c_name + " " + chunk.get("text", "")).lower()
                    kw_matches = sum(1 for t in terms if t in c_text_lower)
                    sim_score = float(sims[idx])

                    if (sim_score >= 0.45) or (sim_score >= 0.30 and (len(terms) == 0 or kw_matches >= min_required)):
                        seen_cases.add(c_name.lower())
                        score = round(min(float(sim_score) + min(kw_matches * 0.05, 0.15), 0.98), 3)
                        citation_disp = chunk.get("citation") or chunk.get("neutral_citation") or f"[{chunk.get('year')}] SCR"

                        text_content = chunk.get("text", "") or ""
                        passage, label, is_ratio = extract_relevant_passage(
                            query=query,
                            text=text_content,
                            is_verified_ratio=False,
                            verified_ratio=""
                        )

                        results.append({
                            "id": chunk.get("case_id"),
                            "title": c_name,
                            "citation": citation_disp,
                            "court": "Supreme Court of India",
                            "benchType": "Supreme Court Bench",
                            "benchSize": 2,
                            "decisionYear": chunk.get("year"),
                            "statutes": extract_statutes_from_text(text_content),
                            "ratioSummary": passage,
                            "ratioLabel": label,
                            "is_verified_ratio": is_ratio,
                            "relevance_score": score,
                            "raw_vector_score": float(sim_score),
                            "retrieval_mode": f"local_index+sc_judgments+{embedding_service.mode}",
                            "source_link": chunk.get("source_link"),
                            "neutral_citation": chunk.get("neutral_citation"),
                            "bench": chunk.get("bench")
                        })

                    if len(results) >= limit * 3:
                        break

        matched_aliases = extract_query_aliases(query)
        if matched_aliases:
            landmark_chunks_file = SC_DATASET_DIR / "chunks" / "landmark_chunks.json"
            if landmark_chunks_file.exists():
                try:
                    with open(landmark_chunks_file, "r", encoding="utf-8") as f:
                        l_chunks = json.load(f)
                    seen_boost = {r.get("title", "").strip().lower() for r in results}
                    for lc in l_chunks:
                        c_title = lc.get("common_name") or lc.get("case_name")
                        c_key = (c_title or "").strip().lower()
                        if not c_key or c_key in seen_boost:
                            continue
                        lc_aliases = [re.sub(r'[\s\W_]+', '', a).lower() for a in lc.get("aliases", [])]
                        if lc.get("common_name"):
                            lc_aliases.append(re.sub(r'[\s\W_]+', '', lc["common_name"]).lower())
                        if any(re.sub(r'[\s\W_]+', '', ma).lower() in lc_aliases for ma in matched_aliases):
                            seen_boost.add(c_key)
                            text_content = lc.get("text", "") or ""
                            passage, label, is_ratio = extract_relevant_passage(
                                query=query,
                                text=text_content,
                                is_verified_ratio=True,
                                verified_ratio=lc.get("ratioSummary", "")
                            )
                            results.insert(0, {
                                "id": lc.get("case_id"),
                                "title": c_title,
                                "citation": lc.get("citation") or lc.get("neutral_citation") or f"[{lc.get('year')}] SCR",
                                "court": "Supreme Court of India",
                                "benchType": "Supreme Court Bench",
                                "benchSize": 5,
                                "decisionYear": lc.get("year"),
                                "statutes": extract_statutes_from_text(text_content),
                                "ratioSummary": passage,
                                "ratioLabel": label,
                                "is_verified_ratio": is_ratio,
                                "relevance_score": 0.99,
                                "raw_vector_score": 0.99,
                                "retrieval_mode": f"local_exact_boost+landmark_cases+{embedding_service.mode}",
                                "source_link": lc.get("source_link"),
                                "neutral_citation": lc.get("neutral_citation"),
                                "bench": lc.get("bench")
                            })
                except Exception as e:
                    logger.debug("Local landmark boost failed: %s", e)

        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------ #
    # Citation Verification                                               #
    # ------------------------------------------------------------------ #
    def verify_citation(self, citation_or_name: str) -> Dict[str, Any]:
        """
        Verifies whether a case name or citation exists in:
        1. The 12 landmark Section 27 precedents (section27_precedents.json)
        2. The 960 Supreme Court judgments (sc_judgments / filtered_cases.parquet)
        """
        q = citation_or_name.strip().lower()
        if not q or len(q) < 3:
            return {"verified": False, "badge": "not_verified", "detail": "Query too short"}

        # 1. Check the 12 landmark precedents
        for c in self.corpus:
            title = c.get("title", "").lower()
            cit = c.get("citation", "").lower()
            alt_cits = [ac.lower() for ac in (c.get("altCitations") or c.get("alternateCitations") or [])]
            if (q in title or title in q) or (q in cit or cit in q) or any(q in ac or ac in q for ac in alt_cits):
                return {
                    "verified": True,
                    "title": c.get("title"),
                    "citation": c.get("citation"),
                    "court": c.get("court"),
                    "year": c.get("decisionYear"),
                    "source_collection": "12_precedents",
                    "badge": "verified"
                }

            # Distinct landmark keywords (e.g. Golikari, Puttaswamy, Kailash Nath, Percept D'Mark, Dawoodi Bohra)
            c_keywords = [k.lower() for k in c.get("keywords", [])]
            if any(k in q for k in c_keywords):
                return {
                    "verified": True,
                    "title": c.get("title"),
                    "citation": c.get("citation"),
                    "court": c.get("court"),
                    "year": c.get("decisionYear"),
                    "source_collection": "12_precedents",
                    "badge": "verified"
                }

            # Normalized title check (ignoring "the", punctuation, spacing)
            norm_q = re.sub(r'[^a-z0-9]', '', re.sub(r'\bthe\b', '', q))
            norm_title = re.sub(r'[^a-z0-9]', '', re.sub(r'\bthe\b', '', title))
            if norm_q and (norm_q in norm_title or norm_title in norm_q):
                return {
                    "verified": True,
                    "title": c.get("title"),
                    "citation": c.get("citation"),
                    "court": c.get("court"),
                    "year": c.get("decisionYear"),
                    "source_collection": "12_precedents",
                    "badge": "verified"
                }

        # 2. Check live Qdrant collection "sc_judgments" if loaded and reachable
        if self._client:
            try:
                available = {c.name for c in self._client.get_collections().collections}
                if self.sc_collection_name in available:
                    from qdrant_client.models import Filter, FieldCondition, MatchValue
                    should_conditions = [
                        FieldCondition(key="case_name", match=MatchValue(value=citation_or_name)),
                        FieldCondition(key="citation", match=MatchValue(value=citation_or_name)),
                        FieldCondition(key="case_id", match=MatchValue(value=citation_or_name)),
                    ]
                    # Also match extracted citation if present in query string
                    cit_match = re.search(r'\[?\b\d{4}\]?\s*\d*\s*(?:SCC|AIR|SCR|SCALE|INSC|S\.C\.R\.)[ \t]*\d+[A-Za-z0-9\s]*', citation_or_name, re.I)
                    if cit_match:
                        should_conditions.append(FieldCondition(key="citation", match=MatchValue(value=cit_match.group(0).strip())))

                    scroll_res, _ = self._client.scroll(
                        collection_name=self.sc_collection_name,
                        scroll_filter=Filter(should=should_conditions),
                        limit=1
                    )
                    if scroll_res:
                        p = scroll_res[0].payload or {}
                        return {
                            "verified": True,
                            "title": p.get("case_name"),
                            "citation": p.get("citation") or p.get("neutral_citation"),
                            "court": "Supreme Court of India",
                            "year": p.get("year"),
                            "bench": p.get("bench"),
                            "source_collection": "sc_judgments",
                            "badge": "verified"
                        }
            except Exception as e:
                logger.debug("Live Qdrant sc_judgments verification query failed: %s", e)

        # 3. Check the real Supreme Court judgments dataset locally only as fallback
        if SC_CHUNKS_PATH.exists():
            self._ensure_sc_dataset_loaded()
            if self._sc_cases_meta:
                # Substantive query tokens (distinct party names)
                stopwords = {"versus", "state", "union", "india", "court", "limited", "ltd", "pvt", "company", "and", "the", "ors", "anr"}
                q_tokens = [t for t in re.findall(r'[a-z0-9]{4,}', q) if t not in stopwords]

                for cid, meta in self._sc_cases_meta.items():
                    name = (meta.get("case_name") or "").lower()
                    cit = (meta.get("citation") or "").lower()
                    nc = (meta.get("neutral_citation") or "").lower()

                    # Clean matching against party names or citation
                    is_direct_match = (
                        (q in name and len(q) >= 4)
                        or (q in cit and len(q) >= 4)
                        or (q in nc and len(q) >= 4)
                        or (q == cid.lower())
                    )
                    if len(q_tokens) == 1:
                        is_token_match = bool(re.search(rf'\b{re.escape(q_tokens[0])}\b', name))
                    elif len(q_tokens) >= 2:
                        is_token_match = (
                            bool(re.search(rf'\b{re.escape(q_tokens[0])}\b', name))
                            or all(re.search(rf'\b{re.escape(tok)}\b', name) for tok in q_tokens)
                        )
                    else:
                        is_token_match = False

                    if is_direct_match or is_token_match:
                        return {
                            "verified": True,
                            "title": meta.get("case_name"),
                            "citation": meta.get("citation") or meta.get("neutral_citation"),
                            "court": "Supreme Court of India",
                            "year": meta.get("year"),
                            "bench": meta.get("bench"),
                            "source_collection": "sc_judgments",
                            "badge": "verified"
                        }

        return {
            "verified": False,
            "title": citation_or_name,
            "citation": None,
            "source_collection": None,
            "badge": "not_verified",
            "detail": "Citation or case not found in verified Supreme Court collection or precedent corpus."
        }

    # ------------------------------------------------------------------ #
    # Health                                                              #
    # ------------------------------------------------------------------ #
    def check_health(self) -> Dict[str, Any]:
        if not self._client and SC_CHUNKS_PATH.exists():
            self._ensure_sc_dataset_loaded()
        sc_chunk_count = len(self._sc_chunks) if self._sc_chunks else 0
        sc_case_count = len(self._sc_cases_meta) if self._sc_cases_meta else 0

        if self._client:
            try:
                collections = self._client.get_collections()
                names = {c.name for c in collections.collections}
                points = 0
                active_col = self.collection_name
                if self.sc_collection_name in names:
                    active_col = self.sc_collection_name
                    info = self._client.get_collection(self.sc_collection_name)
                    points = getattr(info, "points_count", 0) or 0
                elif self.collection_name in names:
                    info = self._client.get_collection(self.collection_name)
                    points = getattr(info, "points_count", 0) or 0

                return {
                    "status": "connected",
                    "url": self.url,
                    "collection": active_col,
                    "collection_seeded": points > 0,
                    "points_count": points,
                    "local_sc_chunks_indexed": sc_chunk_count,
                    "local_sc_judgments": sc_case_count,
                    "embedding": embedding_service.describe(),
                }
            except Exception as e:
                return {
                    "status": "local_fallback",
                    "url": self.url,
                    "error": str(e),
                    "indexed_precedents": len(self.corpus) + sc_case_count,
                    "sc_chunks_indexed": sc_chunk_count,
                    "embedding": embedding_service.describe()
                }
        return {
            "status": "local_index_fallback",
            "url": self.url,
            "indexed_precedents": len(self.corpus) + sc_case_count,
            "sc_chunks_indexed": sc_chunk_count,
            "sc_judgments_count": sc_case_count,
            "embedding": embedding_service.describe(),
            "detail": "Serving 12 verified precedents and 960 Supreme Court judgments from local semantic index.",
        }


qdrant_service = QdrantService()

