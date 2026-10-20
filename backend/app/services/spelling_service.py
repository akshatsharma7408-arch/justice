"""
JUSTICE Legal AI Backend — Spelling Tolerance & Query Correction Service
Builds vocabulary from:
- All landmark case titles, short names, and aliases
- All statutory provisions, acts, and procedural terms
- Comprehensive dictionary of 500+ common Indian legal words
Applies Damerau-Levenshtein distance (1 edit for <= 5 chars, 2 edits for longer)
plus phonetic Soundex checking for Indian names and legal terms.
Never alters valid words or case/section numbers.
"""

import json
from pathlib import Path
import re
from typing import Tuple, List, Set, Dict, Optional

# Standard Indian and Anglo-Indian Legal Vocabulary (500+ common terms)
LEGAL_COMMON_WORDS: Set[str] = {
    # Fundamental & Constitutional
    "constitution", "constitutional", "fundamental", "rights", "directive", "principles",
    "preamble", "citizenship", "equality", "discrimination", "untouchability", "liberty",
    "freedom", "speech", "expression", "assembly", "association", "movement", "residence",
    "profession", "occupation", "trade", "life", "privacy", "education", "religion",
    "worship", "conscience", "secular", "secularism", "minority", "remedies", "writs",
    "habeas", "corpus", "mandamus", "prohibition", "certiorari", "quo", "warranto",
    "parliament", "legislature", "president", "governor", "ordinance", "executive",
    "judiciary", "supreme", "high", "subordinate", "bench", "quorum", "constitutionbench",
    "divisionbench", "basic", "structure", "doctrine", "amendment", "statute", "enactment",
    "legislation", "delegated", "subordinate", "ultra", "vires", "intra", "severability",
    "eclipse", "waiver", "territorial", "nexus", "pith", "substance", "colorable",
    "harmonious", "construction", "interpretation", "precedent", "stare", "decisis",
    "ratio", "decidendi", "obiter", "dicta", "per", "incuriam", "res", "judicata",
    "sub", "judice", "locus", "standi", "suo", "motu", "public", "interest", "litigation",
    "proportionality", "natural", "justice", "audi", "alteram", "partem", "nemo", "judex",
    "bias", "reasoned", "speaking", "order", "arbitrary", "arbitrariness", "reasonableness",
    "fairness", "due", "process", "procedure", "established", "law",

    # Criminal Law & Procedure
    "arrest", "warrant", "custody", "police", "magistrate", "remand", "bail", "anticipatory",
    "regular", "interim", "surety", "bond", "recognizance", "investigation", "inquiry",
    "trial", "fir", "first", "information", "report", "complaint", "cognizable",
    "non-cognizable", "bailable", "non-bailable", "compoundable", "non-compoundable",
    "chargesheet", "charge", "accused", "victim", "complainant", "witness", "testimony",
    "evidence", "cross-examination", "prosecution", "defense", "acquittal", "conviction",
    "sentence", "fine", "imprisonment", "rigorous", "simple", "probation", "parole",
    "remission", "pardon", "mercy", "petition", "appeal", "revision", "reference",
    "quashing", "discharge", "search", "seizure", "confiscation", "forfeiture",
    "attachment", "proclamation", "absconder", "detention", "preventive", "confession",
    "dying", "declaration", "accomplice", "conspiracy", "abetment", "attempt", "homicide",
    "murder", "culpable", "manslaughter", "assault", "hurt", "grievous", "kidnapping",
    "abduction", "rape", "sexual", "harassment", "outraging", "modesty", "dowry", "cruelty",
    "domestic", "violence", "theft", "extortion", "robbery", "dacoity", "cheating", "fraud",
    "forgery", "fabrication", "perjury", "criminal", "breach", "trust", "misappropriation",
    "defamation", "sedition", "mischief", "trespass", "housebreaking", "contempt",

    # Civil, Contract & Commercial
    "contract", "agreement", "proposal", "acceptance", "promise", "promisor", "promisee",
    "consideration", "capacity", "minor", "unsound", "consent", "free", "coercion",
    "undue", "influence", "fraud", "misrepresentation", "mistake", "void", "voidable",
    "voidabinitio", "illegal", "immoral", "opposed", "public", "policy", "restraint",
    "trade", "marriage", "legal", "proceedings", "non-compete", "covenant", "negative",
    "employment", "confidentiality", "proprietary", "goodwill", "breach", "damages",
    "liquidated", "unliquidated", "penalty", "earnest", "money", "forfeiture",
    "compensation", "quantum", "meruit", "restitution", "specific", "performance",
    "injunction", "temporary", "permanent", "mandatory", "prohibitory", "ad-interim",
    "ex-parte", "status", "quo", "undertaking", "indemnity", "guarantee", "bailment",
    "pledge", "agency", "principal", "agent", "power", "attorney", "partnership",
    "firm", "partner", "dissolution", "company", "corporation", "director", "shareholder",
    "articles", "memorandum", "association", "winding", "liquidation", "insolvency",
    "bankruptcy", "resolution", "creditor", "debtor", "debt", "recovery", "tribunal",
    "arbitration", "conciliation", "mediator", "award", "seat", "venue", "arbitral",
    "negotiable", "instrument", "cheque", "dishonour", "drawer", "drawee", "payee",
    "holder", "due", "course", "endorsement", "banking", "loan", "mortgage", "charge",
    "hypothecation", "guarantor", "promissory", "note", "bill", "exchange",

    # Property, Tenancy & Everyday Citizen Rights
    "property", "immovable", "movable", "title", "ownership", "possession", "dispossession",
    "tenant", "landlord", "tenancy", "lease", "lessor", "lessee", "license", "licensor",
    "licensee", "rent", "fair", "standard", "arrears", "eviction", "grounds", "bona",
    "fide", "requirement", "controller", "premises", "rentcontrol", "trespass", "easement",
    "prescription", "nuisance", "adverse", "possession", "partition", "coparcenary",
    "ancestral", "succession", "inheritance", "testamentary", "intestate", "will",
    "codicil", "probate", "letters", "administration", "executor", "administrator",
    "trust", "trustee", "beneficiary", "settlor", "conveyance", "sale", "deed", "gift",
    "exchange", "registration", "stamp", "duty", "valuation",

    # Citizen Rights, Police, Traffic, Corruption
    "bribe", "bribery", "gratification", "illegal", "corruption", "prevention", "trap",
    "raid", "sanction", "disproportionate", "assets", "public", "servant", "vigilance",
    "traffic", "challan", "motor", "vehicles", "driving", "license", "registration",
    "permit", "fitness", "pollution", "speeding", "helmet", "seatbelt", "drink", "drive",
    "accident", "claim", "compensation", "tribunal", "insurer", "insured", "third-party",
    "liability", "no-fault", "hit", "run", "consumer", "dispute", "deficiency", "service",
    "unfair", "trade", "practice", "redressal", "commission", "forum", "district", "state",
    "national", "compensation", "product", "liability", "warranty", "guarantee",

    # Procedural & Judicial
    "plaintiff", "defendant", "appellant", "respondent", "petitioner", "applicant",
    "caveator", "plaint", "written", "statement", "rejoinder", "replication", "affidavit",
    "interlocutory", "application", "impleadment", "amendment", "pleadings", "issues",
    "framing", "evidence", "argument", "judgment", "decree", "order", "direction",
    "execution", "garnishee", "limitation", "condonation", "delay", "cause", "action",
    "jurisdiction", "pecuniary", "territorial", "subject", "matter", "appellate",
    "revisional", "review", "curative", "special", "leave", "slp", "civil", "criminal",
    "original", "writ", "petition", "appeal", "suit", "summary", "cost", "costs",
    "advocate", "counsel", "senior", "bar", "court", "registry", "registry", "clerk",

    # Common English Query & Structural Words (Never mutate these)
    "what", "is", "are", "am", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did",
    "the", "a", "an", "of", "in", "to", "for", "on", "with", "by", "from",
    "at", "about", "against", "without", "under", "between", "over", "after", "before",
    "during", "into", "through", "can", "could", "should", "would",
    "how", "why", "who", "whom", "whose", "when", "where",
    "i", "me", "my", "we", "us", "our", "you", "your", "he", "him", "his", "she", "her", "they", "them", "their",
    "it", "its", "any", "all", "some", "no", "not", "or", "and", "nor", "but", "if",
    "then", "else", "than", "which", "there", "here", "this", "that", "these", "those",
    "right", "rights", "arrest", "arrests", "officer", "officers", "police", "person", "persons",
    "valid", "validity", "illegal", "unlawful", "law", "laws", "case", "cases",
    "held", "court", "judge", "judges", "justice", "bench", "ruling", "decision",
    "landmark", "union", "india", "state", "delhi", "kerala", "bombay", "madras",
    "calcutta", "allahabad", "rajasthan", "punjab", "haryana", "bihar", "gujarat"
}

# Landmark names and canonical party/case words
LANDMARK_VOCABULARY: Set[str] = {
    "kesavananda", "bharati", "sripadagalavaru", "kerala",
    "maneka", "gandhi",
    "puttaswamy",
    "vishaka", "rajasthan",
    "navtej", "singh", "johar",
    "minerva", "mills",
    "golaknath",
    "bommai",
    "olga", "tellis", "bombay", "municipal", "corporation",
    "arnesh", "kumar", "bihar",
    "basu", "west", "bengal",
    "shreya", "singhal",
    "kailash", "nath", "associates",
    "percept", "dmark", "zaheer", "khan",
    "gujarat", "bottling", "coca", "cola",
    "niranjan", "shankar", "golikari",
    "superintendence", "krishan", "murgai",
    "arvind", "kejriwal",
    "lalita", "kumari",
    "satender", "antil",
    "shah", "bano",
    "indira", "nehru",
    "mohori", "bibee",
    "bhim", "singh",
    "aruna", "shanbaug"
}

# Statutory Names & Terms
STATUTE_VOCABULARY: Set[str] = {
    "constitution", "crpc", "ipc", "bns", "bnss", "cpc", "it",
    "article", "articles", "section", "sections", "clause", "sub-section",
    "schedule", "rule", "rules", "order", "code", "act"
}

# Complete Master Vocabulary
MASTER_VOCABULARY: Set[str] = set()

def _init_master_vocabulary():
    global MASTER_VOCABULARY
    if MASTER_VOCABULARY:
        return MASTER_VOCABULARY
    
    vocab = set()
    vocab.update(LEGAL_COMMON_WORDS)
    vocab.update(LANDMARK_VOCABULARY)
    vocab.update(STATUTE_VOCABULARY)

    # Ingest words from landmark definitions if available
    try:
        from app.ingest.landmark_pipeline import LANDMARK_CASES
        for c in LANDMARK_CASES:
            for field in [c.get("common_name", ""), c.get("short_name", "")] + c.get("extra_aliases", []):
                for w in re.findall(r'[a-zA-Z]{3,}', field.lower()):
                    vocab.add(w)
    except Exception:
        pass

    MASTER_VOCABULARY = vocab
    return MASTER_VOCABULARY


def damerau_levenshtein_distance(s1: str, s2: str) -> int:
    """
    Computes Damerau-Levenshtein distance between two strings,
    allowing insertion, deletion, substitution, and transposition of adjacent characters.
    """
    if s1 == s2:
        return 0
    len1 = len(s1)
    len2 = len(s2)
    d = {}
    for i in range(-1, len1 + 1):
        d[(i, -1)] = i + 1
    for j in range(-1, len2 + 1):
        d[(-1, j)] = j + 1

    for i in range(len1):
        for j in range(len2):
            cost = 0 if s1[i] == s2[j] else 1
            d[(i, j)] = min(
                d[(i - 1, j)] + 1,       # deletion
                d[(i, j - 1)] + 1,       # insertion
                d[(i - 1, j - 1)] + cost # substitution
            )
            if i > 0 and j > 0 and s1[i] == s2[j - 1] and s1[i - 1] == s2[j]:
                d[(i, j)] = min(d[(i, j)], d[(i - 2, j - 2)] + cost) # transposition
    return d[(len1 - 1, len2 - 1)]


def soundex(word: str) -> str:
    """
    Computes standard Soundex code for phonetic matching,
    matching Indian names and variants (e.g. jauhar/johar, singal/singhal, ghandi/gandhi).
    """
    if not word:
        return ""
    clean = re.sub(r'[^a-zA-Z]', '', word).upper()
    if not clean:
        return ""

    first = clean[0]
    mapping = {
        'B': '1', 'F': '1', 'P': '1', 'V': '1',
        'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
        'D': '3', 'T': '3',
        'L': '4',
        'M': '5', 'N': '5',
        'R': '6'
    }

    digits = [first]
    prev_code = mapping.get(first, '0')

    for ch in clean[1:]:
        code = mapping.get(ch, '0')
        if code != '0':
            if code != prev_code:
                digits.append(code)
            prev_code = code
        else:
            if ch not in ('H', 'W'):
                prev_code = '0'

    res = "".join(digits)
    return (res + "0000")[:4]


# Targeted phonetic/alias canonical corrections for Supreme Court landmarks and common typos
SPECIAL_PHONETIC_CORRECTIONS: Dict[str, str] = {
    "jauhar": "johar",
    "johar": "johar",
    "singal": "singhal",
    "ghandi": "gandhi",
    "bharti": "bharati",
    "kesavnanda": "kesavananda",
    "kesavanand": "kesavananda",
    "puttuswamy": "puttaswamy",
    "puttasami": "puttaswamy",
    "golaknaath": "golaknath",
    "structre": "structure",
    "privcy": "privacy",
    "arest": "arrest",
    "warant": "warrant",
    "evictn": "eviction",
    "tenent": "tenant",
}


CITATION_TOKENS: Set[str] = {
    "air", "scc", "scr", "scale", "insc", "jt", "supp", "online", "sc",
    "del", "bom", "cal", "mad", "all", "raj", "sec", "section", "art", "article",
    "para", "paras", "order", "rule", "clause", "manu", "ilr", "dlt", "ptc",
    "compcas", "scconline", "suppl", "vs", "versus"
}

ENGLISH_DICTIONARY: Set[str] = set()

def _init_english_dictionary() -> Set[str]:
    global ENGLISH_DICTIONARY
    if ENGLISH_DICTIONARY:
        return ENGLISH_DICTIONARY
    dict_path = Path(__file__).resolve().parent.parent / "data" / "english_dictionary.json"
    if dict_path.exists():
        try:
            with open(dict_path, "r", encoding="utf-8") as f:
                ENGLISH_DICTIONARY = set(json.load(f))
        except Exception:
            pass
    # Always include essential common words
    ENGLISH_DICTIONARY.update({
        "world", "cup", "cricket", "notice", "police", "stop", "live", "living",
        "relationship", "clause", "clauses", "valid", "legal", "illegal", "tenant",
        "landlord", "eviction", "murder", "homicide", "culpable", "bail", "anticipatory"
    })
    return ENGLISH_DICTIONARY

CORRECTION_TARGET_VOCABULARY: Set[str] = set()

def _init_correction_targets() -> Set[str]:
    global CORRECTION_TARGET_VOCABULARY
    if CORRECTION_TARGET_VOCABULARY:
        return CORRECTION_TARGET_VOCABULARY
    targets = set()
    targets.update(LANDMARK_VOCABULARY)
    targets.update(STATUTE_VOCABULARY)
    targets.update(SPECIAL_PHONETIC_CORRECTIONS.values())
    targets.update({
        "arrest", "warrant", "structure", "privacy", "eviction", "tenant",
        "homicide", "culpable", "anticipatory", "bail"
    })
    try:
        from app.ingest.landmark_pipeline import LANDMARK_CASES
        for c in LANDMARK_CASES:
            for field in [c.get("common_name", ""), c.get("short_name", "")] + c.get("extra_aliases", []):
                for w in re.findall(r'[a-zA-Z]{3,}', field.lower()):
                    if w not in CITATION_TOKENS:
                        targets.add(w)
    except Exception:
        pass
    CORRECTION_TARGET_VOCABULARY = targets
    return CORRECTION_TARGET_VOCABULARY


def find_closest_vocabulary_word(word: str, targets: Optional[Set[str]] = None) -> Optional[str]:
    """
    Finds the closest word in the vocabulary for a misspelled word:
    - Checks special phonetic/alias lookup first
    - Allows 1 edit for words up to 5 letters
    - Allows 2 edits for longer words
    - Applies Soundex phonetic verification
    Returns corrected word or None if no acceptable match is found.
    """
    w_low = word.lower()

    # Direct special dictionary check
    if w_low in SPECIAL_PHONETIC_CORRECTIONS:
        return SPECIAL_PHONETIC_CORRECTIONS[w_low]

    if targets is None:
        targets = _init_correction_targets()

    w_len = len(w_low)
    max_edit = 1 if w_len <= 5 else 2
    w_soundex = soundex(w_low)

    best_match = None
    best_dist = 999
    best_is_soundex = False

    for v in targets:
        v_len = len(v)
        if abs(w_len - v_len) > max_edit + 1:
            continue

        v_soundex = soundex(v)
        is_same_soundex = (w_soundex and v_soundex and w_soundex == v_soundex)

        dist = damerau_levenshtein_distance(w_low, v)

        # Allow match if distance <= max_edit or if soundex matches with dist <= max_edit + 1
        if dist <= max_edit or (is_same_soundex and dist <= max_edit + 1):
            if is_same_soundex and not best_is_soundex and dist <= best_dist + 1:
                best_match = v
                best_dist = dist
                best_is_soundex = True
            elif dist < best_dist:
                best_match = v
                best_dist = dist
                best_is_soundex = is_same_soundex

    return best_match


def correct_query(query: str) -> Tuple[str, bool]:
    """
    Corrects misspelled words in a user query before search.
    Strict rules:
    - Never spell-correct words that are in a legal or English dictionary.
    - Never touch tokens that look like citations (AIR, SCC, SCR, INSC, SCC OnLine, years, numbers, "Section 41", "Article 21").
    - Only correct a word when no dictionary word matches and a close match exists in the case-name and statute vocabulary.
    Returns:
    (corrected_query_string, has_corrections_bool)
    """
    if not query or not query.strip():
        return query, False

    eng_dict = _init_english_dictionary()
    legal_vocab = _init_master_vocabulary()
    targets = _init_correction_targets()

    # Split into words while retaining delimiters/whitespace
    tokens = re.split(r'(\s+|[^\w\s])', query)
    corrected_tokens = []
    has_changes = False

    prev_token_low = ""

    for tok in tokens:
        if not tok or tok.isspace() or re.match(r'^[^\w\s]+$', tok):
            corrected_tokens.append(tok)
            continue

        tok_low = tok.lower()

        # 1. Skip numbers or alphanumeric identifiers (e.g., 498A, 1973, 41, 66A, INSC)
        if any(c.isdigit() for c in tok) or len(tok) < 3:
            corrected_tokens.append(tok)
            prev_token_low = tok_low
            continue

        # 2. Never touch citation tokens (AIR, SCC, SCR, INSC, etc.)
        if tok_low in CITATION_TOKENS:
            corrected_tokens.append(tok)
            prev_token_low = tok_low
            continue

        # 3. Never touch numbers/sections immediately following "section", "article", "sec", "art", "clause", "rule"
        if prev_token_low in {"section", "sections", "sec", "sec.", "article", "articles", "art", "art.", "clause", "rule", "order"}:
            corrected_tokens.append(tok)
            prev_token_low = tok_low
            continue

        # 4. Never touch all-uppercase acronyms (e.g. AIR, SCC, SCR, INSC, IPC, CRPC, BNS, IT, PUCL, UOI)
        if tok.isupper() and len(tok) <= 5:
            corrected_tokens.append(tok)
            prev_token_low = tok_low
            continue

        # 5. Never spell-correct words that are in a legal or English dictionary
        if tok_low in eng_dict or tok_low in legal_vocab or tok_low in LEGAL_COMMON_WORDS:
            corrected_tokens.append(tok)
            prev_token_low = tok_low
            continue

        # 6. Only correct when no dictionary word matches and a close match exists in case-name & statute targets
        closest = find_closest_vocabulary_word(tok_low, targets)
        if closest and closest != tok_low:
            # Match capitalization of original token
            if tok.isupper():
                rep = closest.upper()
            elif tok.istitle():
                rep = closest.title()
            else:
                rep = closest
            corrected_tokens.append(rep)
            has_changes = True
            prev_token_low = closest
        else:
            corrected_tokens.append(tok)
            prev_token_low = tok_low

    corrected_text = "".join(corrected_tokens)
    return corrected_text, has_changes

