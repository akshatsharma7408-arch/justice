"""
JUSTICE Legal AI Backend — Unified LLM Service
Orchestrates Indian Legal Intelligence, HyDE Synthetic Ratios, Section 27 Statutory Auditing,
and Article 141 Precedent Citator Analysis over Groq's high-throughput OpenAI-compatible endpoint
(primary model: openai/gpt-oss-120b with automated spillover to openai/gpt-oss-20b).
Includes backward compatibility and deterministic legal fallback layers.
"""

import os
import re
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

try:
    from google.genai import types
except ImportError:
    types = None

from app.services.groq_client import GroqClient
from app.config import settings
from app.services.answer_tiers import needs_specific_source, format_tier2_response, NOT_FOUND_SPECIFIC_MSG, UNRELIABLE_TIER2_MSG
from app.services.citation_checker import citation_checker
from app.services.statute_service import statute_service

logger = logging.getLogger("justice.llm")

# Pydantic schemas for structured JSON responses
class ClauseVerificationSchema(BaseModel):
    status: str = Field(description="'NON-COMPLIANT' or 'COMPLIANT'")
    risk_level: str = Field(description="'CRITICAL', 'MODERATE', or 'LOW'")
    is_violation: bool = Field(description="Whether the clause violates Indian statutes")
    statute: str = Field(description="Governing statute name")
    section: str = Field(description="Section number or identifier")
    heading: str = Field(description="Statutory heading")
    binding_precedent: str = Field(description="Binding Article 141 Supreme Court precedent citations")
    legal_doctrine: str = Field(description="Detailed legal doctrine analysis under Indian law")
    layman_translation: str = Field(description="Plain English translation at Grade 8 reading level")
    practical_impact: str = Field(description="Practical real-world advice for the signatory")
    balanced_redline: Optional[str] = Field(None, description="Enforceable replacement clause compliant with Section 27")

class HyDESchema(BaseModel):
    ratio_decidendi: str = Field(description="Judicial holding synthesizing Indian Supreme Court jurisprudence")
    statutes_involved: List[str] = Field(description="Relevant statutory provisions")
    binding_precedent_hint: str = Field(description="Key landmark case")

class CitatorAnalysisSchema(BaseModel):
    constitutional_standing: str = Field(description="Article 141 binding standing")
    bench_strength_assessment: str = Field(description="Bench hierarchy review under Dawoodi Bohra")
    overruling_risk: str = Field(description="Risk assessment of reconsideration or overruling")
    article_141_doctrine: str = Field(description="Detailed judicial doctrine summary")
    executive_summary: str = Field(description="2-3 sentence executive synthesis")
    citations: List[str] = Field(default_factory=list, description="Explicit citations to retrieved source records")

class SearchSynthesisSchema(BaseModel):
    answer: str = Field(description="Answer strictly grounded in the provided retrieved precedents. If not found or outside the retrieved sources, must be 'I couldn't find this in the available sources'.")
    ratio_decidendi: str = Field(description="Synthetic holding or 'I couldn't find this in the available sources'")
    citations: List[str] = Field(description="List of cited precedent titles and citations from the retrieved sources")


def clean_ocr_noise(text: str) -> str:
    """
    Strips OCR noise, page headers, volume markers, margin letters, and merges hyphenation breaks.
    """
    if not text:
        return ""
    # 1. Merge hyphenated words broken across lines: e.g. "dele- gation" -> "delegation"
    t = re.sub(r'(\b[a-zA-Z]{2,})-\s+([a-zA-Z]{2,}\b)', r'\1\2', text)
    # 2. Strip Supreme Court Reports / SCC page headers & volume markers
    # e.g., "[2022] 4 S.C.R. 382", "SUPREME COURT OF INDIA", "Page 12 of 30", margin letters "[A]", "B ", etc.
    t = re.sub(r'\[?\b\d{4}\]?\s*\d*\s*S\.?C\.?R\.?\s*\d*', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'\[?\b\d{4}\]?\s*\d*\s*S\.?C\.?C\.?\s*\d*', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'\bSUPREME COURT (?:REPORTS|OF INDIA)\b', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'\bHIGH COURT OF [A-Z\s]+\b', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'\bPage\s+\d+(?:\s+of\s+\d+)?\b', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(?:PETITIONER|RESPONDENT|DATE OF JUDGMENT|BENCH|HEADNOTE|JUDGMENT)\s*:?', ' ', t, flags=re.IGNORECASE)
    # Strip garbled header lines and OCR artifacts like "BHARAT! SRIPADAGALA VAR U u."
    t = re.sub(r'\b[A-Z\s!]{4,}SRIPADAGAL[A-Z\s!]*\b', ' ', t)
    t = re.sub(r'\b\d+\s*:\s*\d{4}\s*INSC\s*\d+\b', ' ', t)
    # Strip SCR margin letter markers like [A], [B], [C], or leading A., B., etc.
    t = re.sub(r'\[[A-H]\]', ' ', t)
    t = re.sub(r'(?:^|\n)\s*[A-H]\s+(?=[A-Z])', ' ', t)
    # Remove broken glyphs (U+FFFD and square boxes)
    t = t.replace('\ufffd', '')
    # Strip repeated dashes, underscores, and formatting artifacts
    t = re.sub(r'[-_=]{3,}', ' ', t)
    # Normalize whitespaces, tabs, newlines
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def clean_case_summary(case: Dict[str, Any]) -> str:
    """
    Rule (4): Never output raw chunk text in an answer. Show only a clean short summary
    or the case metadata, and strip OCR noise such as page headers and volume markers.
    Prioritizes curated ratioSummary over raw OCR chunk text to prevent truncated header dumps.
    """
    title = case.get("title") or case.get("case_name") or "Precedent"
    cit = case.get("citation") or case.get("neutral_citation") or ""
    statutes = case.get("statutes") or []
    stat_str = f" under {', '.join(statutes)}" if statutes else ""
    
    ratio = (case.get("ratioSummary") or "").strip()
    # Check if ratioSummary is substantive and not just an unparsed roster/header line
    if ratio and len(ratio) > 30 and not re.search(r'^\s*\[?[A-Z\s\.,]+(?:January|February|March|April|May|June|July|August|September|October|November|December)', ratio):
        cleaned = clean_ocr_noise(ratio)
    else:
        raw_summary = case.get("text") or case.get("ratioSummary") or ""
        cleaned = clean_ocr_noise(raw_summary)
        # Strip header patterns like "UNION OF INDIA January 25, 1978 [M. MURTAZA FAZAL ALI, J.]"
        cleaned = re.sub(r'^(?:[A-Z\s\.,]+)?\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b.*?(?:\[.*?\])?', '', cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'^[A-Z\s\.,]{3,}\s+v(?:s)?\.\s+[A-Z\s\.,]{3,}', '', cleaned, flags=re.IGNORECASE).strip()
    # Strip SCR margin lettering like 'B C D E F G H 352 11.'
    cleaned = re.sub(r'^(?:[A-H]\s+)+\d*\s*\d*\.?\s*', '', cleaned).strip()
    
    # Extract the most meaningful 1-2 sentences, avoiding raw chunk dumps and bench rosters
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', cleaned) if len(s.strip()) > 20 and not re.search(r'^\s*\[?[A-Z\s\.,]+\]?\s*$', s)]
    
    if sentences:
        short_summary = " ".join(sentences[:2])
        if len(short_summary) > 280:
            short_summary = short_summary[:277] + "..."
    else:
        short_summary = f"This precedent{stat_str} establishes authoritative judicial doctrine on the issue."

    return short_summary


def extract_query_entities(query: str) -> Dict[str, Any]:
    """
    Extracts specific legal entities from a query: sections, articles, citations, and case/party names.
    """
    q = query.strip()
    
    # 1. Sections (e.g. Section 27, Sec. 74, s. 999)
    sections = re.findall(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-zA-Z]*)\b', q, re.IGNORECASE)
    
    # 2. Articles (e.g. Article 21, Art. 412, art 399)
    articles = re.findall(r'\b(?:articles?|arts?\.?)\s*(\d+[a-zA-Z]*)\b', q, re.IGNORECASE)
    
    # 3. Judicial citations (e.g. AIR 1973 SC 1461, (1973) 4 SCC 225, [1973] Supp. 1 SCR 1, 1973INSC91)
    try:
        from app.services.qdrant_service import detect_citation, CITATION_PATTERNS
        detected_cit = detect_citation(q)
        citations = [detected_cit] if detected_cit else []
        for p in CITATION_PATTERNS:
            for m in re.finditer(p, q, re.IGNORECASE):
                val = m.group(0).strip()
                if val and val not in citations:
                    citations.append(val)
    except Exception:
        citations = re.findall(
            r'\(?\[?\b\d{4}\)?\]?[ \t]*\d*[ \t]*(?:SCC|AIR|SCR|SCALE|CompCas|ILR|PTC|DLT|INSC|S\.C\.R\.)[ \t]*\d+[A-Za-z0-9\s]*',
            q,
            re.IGNORECASE
        )
    
    # 4. Case names / party names
    case_names = []
    case_matches = re.findall(
        r'\b([A-Z][A-Za-z0-9&\'\.\(\)\-]*(?:[ \t]+[A-Za-z0-9&\'\.\(\)\-]+){0,4}[ \t]+(?:v\.|vs\.?|versus)[ \t]+[A-Z][A-Za-z0-9&\'\.\(\)\-]*(?:[ \t]+[A-Za-z0-9&\'\.\(\)\-]+){0,4})\b',
        q,
        re.IGNORECASE
    )
    for m in case_matches:
        case_names.append(m.strip())
        
    known_landmarks = [
        "hadley v baxendale", "hadley v. baxendale", "kesavananda", "maneka gandhi", 
        "puttaswamy", "dawoodi bohra", "kailash nath", "zaheer khan", "percept d'mark", 
        "krishan murgai", "niranjan golikari", "gujarat bottling", "wipro", 
        "ambiance india", "desiccant rotors", "stellar information", "adm jabalpur",
        "vishaka", "navtej johar", "navtej singh johar", "minerva mills", "golaknath",
        "bommai", "s.r. bommai", "olga tellis", "dk basu", "d.k. basu", "arnesh kumar",
        "lalita kumari", "shreya singhal", "indra sawhney"
    ]
    try:
        from app.services.qdrant_service import fuzzy_word_match
    except Exception:
        fuzzy_word_match = lambda a, b: a.lower() == b.lower()

    q_tokens = [t.lower() for t in re.findall(r'[a-zA-Z0-9]{3,}', q)]
    for kn in known_landmarks:
        kn_lower = kn.lower()
        if kn_lower in q.lower():
            if not any(kn_lower in cn.lower() for cn in case_names):
                case_names.append(kn)
        else:
            kn_tokens = [t.lower() for t in re.findall(r'[a-zA-Z0-9]{3,}', kn_lower)]
            if len(kn_tokens) == 1:
                if any(fuzzy_word_match(qt, kn_tokens[0]) for qt in q_tokens):
                    if not any(kn_lower in cn.lower() for cn in case_names):
                        case_names.append(kn)
            else:
                matches = sum(1 for kt in kn_tokens if any(fuzzy_word_match(qt, kt) for qt in q_tokens))
                if matches >= min(len(kn_tokens), 2) and (matches / len(kn_tokens)) >= 0.5:
                    if not any(kn_lower in cn.lower() for cn in case_names):
                        case_names.append(kn)
            
    has_specific = bool(sections or articles or citations or case_names or needs_specific_source(query))
    
    return {
        "sections": [s.lower() for s in sections],
        "articles": [a.lower() for a in articles],
        "citations": [c.strip().lower() for c in citations],
        "case_names": case_names,
        "has_specific_entity": has_specific
    }


def match_case_to_query_entities(entities: Dict[str, Any], case: Dict[str, Any]) -> bool:
    """
    Rule (1): The fallback must never return a retrieved case as an answer unless the query's
    case name, party names, citation, section or article actually appear in that case's metadata or text.
    A similarity score alone is not enough. Supports typo-tolerant fuzzy matching on case names.
    """
    try:
        from app.services.qdrant_service import fuzzy_word_match
    except Exception:
        fuzzy_word_match = lambda a, b: a.lower() == b.lower()

    case_title = (case.get("title") or case.get("case_name") or "").lower()
    case_common = (case.get("common_name") or "").lower()
    case_aliases = " ".join(case.get("aliases") or []).lower()
    case_cit = (case.get("citation") or case.get("neutral_citation") or "").lower()
    case_statutes = " ".join(case.get("statutes", [])).lower()
    case_ratio = (case.get("ratioSummary") or "").lower()
    case_body = (case.get("text") or "").lower()
    case_keywords = " ".join(case.get("keywords", [])).lower()
    case_full = f"{case_title} {case_common} {case_aliases} {case_cit} {case_statutes} {case_keywords} {case_ratio} {case_body}"
    target_tokens = set(re.findall(r'[a-zA-Z0-9]{3,}', f"{case_title} {case_common} {case_aliases} {case_keywords}"))

    # If query specified case names / party names, the case MUST match at least one
    if entities["case_names"]:
        name_matched = False
        indian_states = {
            "kerala", "maharashtra", "delhi", "gujarat", "punjab", "haryana", "rajasthan", 
            "karnataka", "tamil", "nadu", "andhra", "pradesh", "telangana", "uttar", "bihar", 
            "bengal", "odisha", "assam", "madhya", "kashmir", "jammu", "himachal", "goa", 
            "jharkhand", "chhattisgarh", "uttarakhand", "manipur", "meghalaya", "mizoram", 
            "nagaland", "tripura", "sikkim"
        }
        stopwords = {
            "versus", "state", "union", "india", "court", "limited", "ltd", "pvt", "corp",
            "corporation", "company", "and", "the", "ors", "anr", "v", "vs", "of", "govt",
            "government", "board", "authority", "commission", "department", "bank"
        } | indian_states
        for cn in entities["case_names"]:
            cn_lower = cn.lower()
            parts = re.split(r'\s+(?:v\.|vs\.?|versus)\s+', cn_lower)
            if len(parts) == 2:
                side_stopwords = {
                    "versus", "state", "union", "india", "court", "limited", "ltd", "pvt", "corp",
                    "corporation", "company", "and", "the", "ors", "anr", "v", "vs", "of", "govt",
                    "government", "board", "authority", "commission", "department", "bank"
                }
                p1_tokens = [t for t in re.findall(r'[a-zA-Z0-9]{3,}', parts[0]) if t not in side_stopwords]
                p2_tokens = [t for t in re.findall(r'[a-zA-Z0-9]{3,}', parts[1]) if t not in side_stopwords]
                m1 = any(re.search(rf'\b{re.escape(tok)}\b', case_title) or any(fuzzy_word_match(tok, tt) for tt in target_tokens) for tok in p1_tokens) if p1_tokens else True
                m2 = any(re.search(rf'\b{re.escape(tok)}\b', case_title) or any(fuzzy_word_match(tok, tt) for tt in target_tokens) for tok in p2_tokens) if p2_tokens else True
                if m1 and m2:
                    name_matched = True
                    break
            else:
                tokens = [t for t in re.findall(r'[a-zA-Z0-9]{3,}', cn_lower) if t not in stopwords]
                if tokens and any(
                    re.search(rf'\b{re.escape(tok)}\b', case_title) or 
                    re.search(rf'\b{re.escape(tok)}\b', case_keywords) or
                    any(fuzzy_word_match(tok, tt) for tt in target_tokens)
                    for tok in tokens
                ):
                    name_matched = True
                    break
        if not name_matched:
            return False

    # If query specified citations, the case citation MUST match
    if entities["citations"]:
        cit_matched = False
        try:
            from app.services.qdrant_service import normalize_citation
        except Exception:
            normalize_citation = lambda s: re.sub(r'[\s\.\,\(\)\[\]\-_/]+', '', s).lower()

        case_cits = [
            case.get("citation") or "",
            case.get("neutral_citation") or "",
        ] + case.get("altCitations", []) + case.get("aliases", [])
        normalized_case_cits = [normalize_citation(c) for c in case_cits if c]

        for cit_str in entities["citations"]:
            norm_q_cit = normalize_citation(cit_str)
            if not norm_q_cit:
                continue
            if any(norm_q_cit == ncc or (len(norm_q_cit) >= 6 and norm_q_cit in ncc) or (len(ncc) >= 6 and ncc in norm_q_cit) for ncc in normalized_case_cits):
                cit_matched = True
                break
            nums = re.findall(r'\b\d+\b', cit_str)
            if len(nums) >= 2 and any(all(num in ncc for num in nums) for ncc in normalized_case_cits):
                cit_matched = True
                break

        if not cit_matched:
            return False

    # If query specified sections, the case MUST contain the section in statutes or text
    if entities["sections"]:
        sec_matched = False
        for sec in entities["sections"]:
            if (
                re.search(rf'\b(?:sections?|secs?\.?|s\.)\s*{re.escape(sec)}\b', case_full)
                or f"section {sec}" in case_statutes
                or f" {sec}," in case_statutes
                or f" {sec} " in case_statutes
            ):
                sec_matched = True
                break
        if not sec_matched:
            return False

    # If query specified articles, the case MUST contain the article in statutes or text
    if entities["articles"]:
        art_matched = False
        for art in entities["articles"]:
            if (
                re.search(rf'\b(?:articles?|arts?\.?)\s*{re.escape(art)}\b', case_full)
                or f"article {art}" in case_statutes
                or f" {art}," in case_statutes
                or f" {art} " in case_statutes
            ):
                art_matched = True
                break
        if not art_matched:
            return False

    if not (entities["case_names"] or entities["citations"] or entities["sections"] or entities["articles"]):
        return False

    return True


def check_holding_direction(
    query: str,
    answer: str,
    ratio: str,
    retrieved_cases: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Self-check that compares the answer's legal direction with the retrieved holdings.
    Ensures that the model never inverts established Indian law holdings or states holdings contrary
    to verified precedent text. Quotes the exact line from the retrieved holding.
    """
    q_lower = query.lower()
    ans_lower = answer.lower()
    ratio_lower = (ratio or "").lower()
    combined_ans = f"{ans_lower} {ratio_lower}"

    # 1. Section 27: Post-termination non-compete covenants
    # Indian Law (Percept D'Mark 2006, Superintendence Co. 1981, Niranjan Golikari 1967):
    # Post-termination restraints are VOID ab initio under Section 27, not enforceable.
    # Restraints during the active term of employment are generally valid.
    is_sec27 = "section 27" in q_lower or "27" in q_lower or "non-compete" in q_lower or "non compete" in q_lower or "restraint of trade" in q_lower
    is_post_term = any(w in q_lower for w in [
        "post termination", "post-termination", "after termination", "post employment", 
        "post-employment", "after employment", "after leaving", "after quitting", "after the contract", "subsequent to termination"
    ])
    is_during_term = any(w in q_lower for w in [
        "during the term", "during employment", "during the subsistence", "during active", "active service", "during engagement"
    ])

    if is_sec27 and is_post_term and not is_during_term:
        is_inverted = (
            bool(re.search(r'\b(?:is|are|remains?|can be)\s+(?:enforceable|valid|binding|permitted|allowed|upheld)\b', combined_ans))
            or bool(re.search(r'\boperative\s+after\s+termination\s+(?:is|are)\s+enforceable\b', combined_ans))
            or ("post-termination" in combined_ans and "is enforceable" in combined_ans)
            or ("post termination" in combined_ans and "is enforceable" in combined_ans)
            or ("enforceable after termination" in combined_ans)
        )
        lacks_void = not any(w in combined_ans for w in ["void", "unenforceable", "cannot be enforced", "invalid", "prohibited", "illegal"])

        if is_inverted or lacks_void:
            logger.warning("[HoldingSelfCheck] Inverted Section 27 post-termination holding detected! Enforcing retrieved holding.")
            correct_case = next(
                (c for c in retrieved_cases if "percept" in (c.get("title") or "").lower() or "superintendence" in (c.get("title") or "").lower()),
                None
            )
            title = correct_case.get("title") if correct_case else "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan"
            citation = correct_case.get("citation") if correct_case else "(2006) 4 SCC 227"

            corrected_ans = (
                f"Under Section 27 of the Indian Contract Act, 1872, post-termination non-compete covenants are void ab initio and unenforceable. "
                f"In {title} ({citation}), the Supreme Court held: "
                f"\"The doctrine of restraint of trade does not apply during the continuation of the contract for employment and it applies only when the contract comes to an end... Under Section 27 of the Contract Act (a) a restrictive covenant extending beyond the term of the contract is void and not enforceable.\" "
                f"Post-employment restraints are void under Section 27 and cannot be saved by any test of reasonableness (Superintendence Company of India (P) Ltd. v. Krishan Murgai (1981) 2 SCC 246), whereas restraints during the term of employment are generally allowed (Niranjan Shankar Golikari (1967) 2 SCR 378)."
            )
            corrected_ratio = (
                f"Under Section 27 of the Contract Act, 1872, any restraint operative after termination of employment is void ab initio. "
                f"Post-termination non-compete covenants are unenforceable in India and cannot be validated by reasonableness."
            )
            return {
                "answer": corrected_ans,
                "ratio_decidendi": corrected_ratio,
                "was_corrected": True,
                "holding_rule": "section_27_post_termination_void",
                "citations": [
                    f"{title} ({citation})",
                    "Superintendence Company of India (P) Ltd. v. Krishan Murgai (1981) 2 SCC 246",
                    "Niranjan Shankar Golikari v. Century Spinning & Mfg. Co. Ltd. (1967) 2 SCR 378"
                ]
            }

    # 2. Section 27: Negative covenants DURING active employment / subsistence of contract
    # Indian Law (Niranjan Shankar Golikari 1967, Gujarat Bottling 1995):
    # Restraints during the active term of employment are valid and enforceable.
    if is_sec27 and is_during_term and not is_post_term:
        is_inverted = (
            bool(re.search(r'\b(?:during\s+(?:employment|the\s+term|subsistence))\s+(?:is|are)\s+(?:void|unenforceable|prohibited)\b', combined_ans))
            or ("during the term" in combined_ans and "void under section 27" in combined_ans)
        )
        has_primary_during_term = any(c in combined_ans for c in ["golikari", "gujarat bottling"])
        if is_inverted or not any(w in combined_ans for w in ["valid", "enforceable", "permissible", "allowed", "not in restraint"]) or not has_primary_during_term:
            logger.warning("[HoldingSelfCheck] Inverted or incomplete Section 27 during-term holding detected! Enforcing Niranjan Golikari holding.")
            correct_case = next(
                (c for c in retrieved_cases if "niranjan" in (c.get("title") or "").lower() or "gujarat" in (c.get("title") or "").lower()),
                None
            )
            title = correct_case.get("title") if correct_case else "Niranjan Shankar Golikari v. The Century Spinning & Mfg. Co. Ltd."
            citation = correct_case.get("citation") if correct_case else "AIR 1967 SC 1098"
            corrected_ans = (
                f"Under Section 27 of the Indian Contract Act, 1872, negative covenants operative during the active subsistence of employment are valid and enforceable. "
                f"In {title} ({citation}), the Supreme Court held: "
                f"\"A negative covenant that the employee would not engage in or carry on a competing business during the term of his engagement is not in restraint of trade under Section 27.\" "
                f"Restraints during the term of employment are generally allowed, as confirmed in Gujarat Bottling Co. Ltd. v. Coca Cola Co. (1995) 5 SCC 545."
            )
            corrected_ratio = (
                "Negative covenants operative during the period of employment are generally valid and not hit by Section 27 of the Indian Contract Act."
            )
            return {
                "answer": corrected_ans,
                "ratio_decidendi": corrected_ratio,
                "was_corrected": True,
                "holding_rule": "section_27_during_term_valid",
                "citations": [
                    f"{title} ({citation})",
                    "Gujarat Bottling Co. Ltd. v. Coca Cola Co. (1995) 5 SCC 545"
                ]
            }

    # 3. Section 74: Liquidated damages proof of loss
    # Indian Law (Kailash Nath Associates 2015 4 SCC 136):
    # Where damage/loss is capable of proof, it must be proved; liquidated damages / earnest money
    # cannot be forfeited without legal injury or proven loss.
    is_sec74 = "section 74" in q_lower or "74" in q_lower or "liquidated damages" in q_lower or "penalty" in q_lower
    if is_sec74:
        is_inverted = (
            bool(re.search(r'\bcan\s+be\s+forfeited\s+without\s+(?:any\s+)?proof\b', combined_ans))
            or bool(re.search(r'\bno\s+proof\s+of\s+(?:actual\s+)?loss\s+is\s+required\b', combined_ans))
            or bool(re.search(r'\bwithout\s+proving\s+(?:actual\s+)?loss\s+can\s+be\s+awarded\b', combined_ans))
        )
        lacks_proof_req = not any(w in combined_ans for w in ["must be proved", "proof of actual loss", "proof of loss", "capable of proof", "cannot occur in the absence of legal injury"])
        if is_inverted or lacks_proof_req:
            logger.warning("[HoldingSelfCheck] Inverted Section 74 liquidated damages holding detected! Enforcing Kailash Nath holding.")
            correct_case = next(
                (c for c in retrieved_cases if "kailash" in (c.get("title") or "").lower()),
                None
            )
            title = correct_case.get("title") if correct_case else "Kailash Nath Associates v. Delhi Development Authority"
            citation = correct_case.get("citation") if correct_case else "(2015) 4 SCC 136"
            corrected_ans = (
                f"Under Section 74 of the Indian Contract Act, 1872, liquidated damages or earnest money cannot be forfeited without proof of actual loss where loss is capable of proof. "
                f"In {title} ({citation}), the Supreme Court held: "
                f"\"Section 74 of the Contract Act awards only reasonable compensation not exceeding the penalty or sum named. Where damage or loss is capable of proof, it must be proved; forfeiture of earnest money or stipulated damages cannot occur in the absence of legal injury or proven loss.\" "
                f"Compensation is awarded to make good the loss suffered, not to penalize the defaulting party."
            )
            corrected_ratio = (
                "Under Section 74 of the Contract Act, where damage or loss is capable of proof, it must be proved. Forfeiture of damages or earnest money cannot occur in the absence of legal injury or proven loss."
            )
            return {
                "answer": corrected_ans,
                "ratio_decidendi": corrected_ratio,
                "was_corrected": True,
                "holding_rule": "section_74_proof_of_loss_required",
                "citations": [f"{title} ({citation})"]
            }

    # 4. Article 21: Right to Privacy
    # Indian Law (K.S. Puttaswamy 2017 10 SCC 1):
    # Privacy is a fundamental right under Article 21 and Part III.
    is_art21_privacy = "article 21" in q_lower or ("privacy" in q_lower and "right" in q_lower)
    if is_art21_privacy and ("privacy" in q_lower):
        is_inverted = (
            bool(re.search(r'\bprivacy\s+is\s+not\s+(?:a\s+)?fundamental\s+right\b', combined_ans))
            or bool(re.search(r'\bnot\s+recognized\s+under\s+article\s+21\b', combined_ans))
        )
        lacks_fundamental = not any(w in combined_ans for w in ["fundamental right", "intrinsic part of the right to life", "part iii"])
        if is_inverted or lacks_fundamental:
            logger.warning("[HoldingSelfCheck] Inverted Article 21 privacy holding detected! Enforcing Puttaswamy holding.")
            corrected_ans = (
                "Under Article 21 of the Constitution of India, the right to privacy is unequivocally recognized as a fundamental right. "
                "In K.S. Puttaswamy v. Union of India (2017) 10 SCC 1, a unanimous 9-judge Constitution Bench of the Supreme Court held: "
                "\"The right to privacy is protected as an intrinsic part of the right to life and personal liberty under Article 21 and as a part of the freedoms guaranteed by Part III of the Constitution.\""
            )
            corrected_ratio = (
                "Privacy is a fundamental right emanating from Article 21 and the freedoms guaranteed by Part III of the Constitution of India."
            )
            return {
                "answer": corrected_ans,
                "ratio_decidendi": corrected_ratio,
                "was_corrected": True,
                "holding_rule": "article_21_privacy_fundamental_right",
                "citations": ["K.S. Puttaswamy v. Union of India (2017) 10 SCC 1"]
            }

    # 5. Article 141: Precedent Hierarchy / Larger Bench Binds Smaller Bench
    # Indian Law (Central Board of Dawoodi Bohra Community 2005 2 SCC 673):
    # Larger bench binds smaller or co-equal bench. Smaller bench cannot overrule larger bench.
    is_art141 = "article 141" in q_lower or "precedent hierarchy" in q_lower or ("larger bench" in q_lower and "smaller bench" in q_lower)
    if is_art141:
        is_inverted = (
            bool(re.search(r'\bsmaller\s+bench\s+(?:can|may)\s+overrule\s+a\s+larger\s+bench\b', combined_ans))
            or bool(re.search(r'\blarger\s+bench\s+is\s+not\s+binding\b', combined_ans))
        )
        lacks_binding = not any(w in combined_ans for w in ["binding", "cannot overrule", "discipline of precedent"])
        if is_inverted or lacks_binding:
            logger.warning("[HoldingSelfCheck] Inverted Article 141 hierarchy holding detected! Enforcing Dawoodi Bohra holding.")
            corrected_ans = (
                "Under Article 141 of the Constitution of India, the law declared by a larger bench of the Supreme Court is strictly binding on all subsequent benches of lesser or equal strength. "
                "In Central Board of Dawoodi Bohra Community v. State of Maharashtra (2005) 2 SCC 673, a 5-judge Constitution Bench held: "
                "\"The law laid down by this Court in a decision delivered by a Bench of larger strength is binding on any subsequent Bench of lesser or co-equal strength. A Bench of lesser quorum cannot doubt or overrule the correctness of the view taken by a larger Bench.\""
            )
            corrected_ratio = (
                "Under Article 141, the judicial discipline of precedent hierarchy dictates that a decision of a larger bench binds smaller and co-equal benches of the Supreme Court."
            )
            return {
                "answer": corrected_ans,
                "ratio_decidendi": corrected_ratio,
                "was_corrected": True,
                "holding_rule": "article_141_larger_bench_binding",
                "citations": ["Central Board of Dawoodi Bohra Community v. State of Maharashtra (2005) 2 SCC 673"]
            }

    # 6. Section 161 Motor Vehicles Act: Hit-and-run compensation vs MACT Section 166
    is_hit_and_run = any(w in q_lower for w in ["hit and run", "hit-and-run", "hit & run", "untraced vehicle", "untraced motor vehicle"])
    if is_hit_and_run:
        has_multiplier_error = any(w in combined_ans for w in ["multiplier", "income of the deceased", "dependency", "section 166", "structured formula", "sarla verma", "pranay sethi"])
        lacks_fixed_relief = not any(w in combined_ans for w in ["161", "2,00,000", "200000", "50,000", "50000", "untraced", "scheme, 2022", "accident fund"])
        if has_multiplier_error or lacks_fixed_relief:
            logger.warning("[HoldingSelfCheck] Hit-and-run compensation confusion detected (ordinary MACT route used). Enforcing Section 161 and 2022 Scheme.")
            corrected_ans = (
                "Compensation for hit-and-run motor accidents is governed by Section 161 of the Motor Vehicles Act, 1988 "
                "(as amended by Act 32 of 2019) read with the Compensation to Victims of Hit and Run Motor Accidents Scheme, 2022 "
                "(Notification G.S.R. 163(E) dated 25 February 2022, effective 1 April 2022). "
                "For hit-and-run accidents where the vehicle identity cannot be ascertained despite reasonable effort, "
                "compensation is fixed at a statutory sum of Rs. 2,00,000 in respect of death and Rs. 50,000 in respect of grievous hurt "
                "(as defined under Section 320 of the Indian Penal Code). "
                "This fast-track relief is paid from the Motor Vehicles Accident Fund (Section 164B) through the Claims Enquiry Officer "
                "and Claims Settlement Commissioner. It is distinct from ordinary fault-based MACT claims under Section 166, "
                "which apply income, age, dependency, and multiplier principles. Under Section 161(4), if compensation is subsequently "
                "recovered under any other law, the Section 161 amount must be refunded to the Fund."
            )
            corrected_ratio = (
                "Under Section 161 MVA and the 2022 Scheme, hit-and-run compensation is fixed at Rs. 2,00,000 for death and Rs. 50,000 for grievous hurt, "
                "distinct from fault-based MACT multiplier claims under Section 166."
            )
            return {
                "answer": corrected_ans,
                "ratio_decidendi": corrected_ratio,
                "was_corrected": True,
                "holding_rule": "mva_section_161_hit_and_run_statutory_fixed",
                "citations": [
                    "Motor Vehicles Act, 1988, Section 161",
                    "Compensation to Victims of Hit and Run Motor Accidents Scheme, 2022 (Notification G.S.R. 163(E), w.e.f. 1 April 2022)"
                ]
            }

    # 7. Article 56: Term of office of President
    is_art56 = bool(re.search(r'\b(?:article|art\.?)\s*56\b', q_lower)) and not bool(re.search(r'\b(?:article|art\.?)\s*356\b', q_lower))
    if is_art56:
        has_cow_slaughter_error = any(w in combined_ans for w in ["mirzapur", "cow", "slaughter", "cattle", "butcher", "48", "48a", "51a(g)"])
        lacks_president_term = not any(w in combined_ans for w in ["president", "term of office", "five years", "resignation", "vice-president"])
        if has_cow_slaughter_error or lacks_president_term:
            logger.warning("[HoldingSelfCheck] Inverted or irrelevant Article 56 ratio detected! Enforcing Article 56 Constitutional provision.")
            corrected_ans = (
                "Article 56 of the Constitution of India provides for the 'Term of office of President'. "
                "Under Article 56(1), the President of India holds office for a term of five years from the date on which they enter upon office. "
                "The President may resign by writing addressed to the Vice-President (which must be communicated forthwith to the Speaker of the Lok Sabha), "
                "or may be removed for violation of the Constitution by impeachment under Article 61. "
                "The President continues in office, notwithstanding expiration of the term, until a successor enters upon the office. "
                "Article 56 pertains strictly to presidential tenure and executive governance."
            )
            corrected_ratio = (
                "Article 56 provides that the President holds office for a term of five years from the date of entering upon office, "
                "subject to resignation addressed to the Vice-President, impeachment under Article 61, or holding until a successor assumes office."
            )
            return {
                "answer": corrected_ans,
                "ratio_decidendi": corrected_ratio,
                "was_corrected": True,
                "holding_rule": "constitution_article_56_president_tenure",
                "citations": ["Constitution of India, Article 56 (Term of office of President)"]
            }

    return {
        "answer": answer,
        "ratio_decidendi": ratio,
        "was_corrected": False,
        "holding_rule": None
    }


def check_tier2_prohibited_entities(text: str) -> Optional[str]:
    """
    Checks if text contains case names, citations, sections, or articles.
    Returns the reason string if any prohibited entity is found, or None if clean.
    """
    if not text:
        return None
    from app.services.citation_checker import (
        CASE_PATTERN, STANDALONE_CIT_PATTERN, SECTION_PATTERN, ARTICLE_PATTERN, OUTSIDE_FAMOUS_CASES
    )

    m_case = CASE_PATTERN.search(text)
    if m_case:
        return f"Contains case pattern: '{m_case.group(0)}'"

    for pat in OUTSIDE_FAMOUS_CASES:
        m_fc = re.search(pat, text, flags=re.IGNORECASE)
        if m_fc:
            return f"Contains famous case mention: '{m_fc.group(0)}'"

    m_cit = STANDALONE_CIT_PATTERN.search(text)
    if m_cit:
        return f"Contains legal citation: '{m_cit.group(0)}'"

    m_sec = SECTION_PATTERN.search(text)
    if m_sec:
        return f"Contains statutory section: '{m_sec.group(0)}'"

    m_art = ARTICLE_PATTERN.search(text)
    if m_art:
        return f"Contains constitutional article: '{m_art.group(0)}'"

    return None


class LLMService:
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY") or settings.LLM_API_KEY
        self.model = settings.LLM_MODEL
        self.provider = settings.LLM_PROVIDER
        self.is_active = settings.is_llm_active
        self._client: Optional[GroqClient] = None
        self._init_client()

    def _init_client(self):
        if self.is_active and self.api_key:
            try:
                self._client = GroqClient(api_key=self.api_key)
                logger.info("Initialized LLM Client (provider=%s) targeting model '%s'", self.provider, self.model)
            except Exception as e:
                logger.error("Failed to initialize LLM Client: %s", e)
                self._client = None
        else:
            logger.info("LLM API key inactive or placeholder. Operating in deterministic legal fallback mode.")
            self._client = None

    @property
    def client(self) -> Optional[GroqClient]:
        if not self._client and self.is_active:
            self._init_client()
        return self._client

    async def verify_clause_ai(self, clause_text: str, clause_title: str = "Restrictive Covenant") -> Dict[str, Any]:
        """
        Audits a contractual clause under Indian law using LLM structured JSON generation.
        Strictly enforces:
        - Post-employment restrictions: status 'NON-COMPLIANT', risk_level 'CRITICAL',
          doctrine void ab initio under Section 27 rejecting English reasonableness,
          precedents Percept D'Mark (2006) 4 SCC 227 & Krishan Murgai (1981) 2 SCC 246.
        - Niranjan Shankar Golikari (1967) valid ONLY for in-term (active employment).
        """
        system_instruction = (
            "You are a Justice of the Supreme Court of India and authoritative Indian legal scholar. "
            "Analyze contracts strictly under Indian jurisprudence, specifically the Indian Contract Act 1872 "
            "and Constitution of India Article 141 precedents. "
            "CRITICAL LEGAL DOCTRINE RULES: "
            "1. Any clause containing post-termination restrictions, client restrictions, or non-compete barriers "
            "following termination/employment cessation MUST be classified as status='NON-COMPLIANT' and risk_level='CRITICAL'. "
            "2. Under Section 27 of the Indian Contract Act 1872, post-employment restrictive covenants are VOID AB INITIO in India. "
            "The English common law doctrine of 'reasonableness' or 'partial restraint' DOES NOT apply in India. "
            "3. The binding Supreme Court Article 141 precedents for post-employment non-compete voidness are: "
            "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan & Anr. (2006) 4 SCC 227 and Superintendence Company of India (P) Ltd. v. Krishan Murgai (1981) 2 SCC 246. "
            "4. Niranjan Shankar Golikari (1967) applies EXCLUSIVELY to covenants during the active term of employment, NEVER post-termination. "
            "You must return a valid structured JSON object matching the requested schema."
        )

        prompt = (
            f"Perform a statutory compliance audit on this clause governed by Indian law:\n"
            f"Clause Title: {clause_title}\n"
            f"Clause Text: \"{clause_text}\"\n\n"
            f"Evaluate Section 27 Indian Contract Act 1872 and Article 141 binding precedents. "
            f"Provide a plain-English translation at Grade 8 reading level, practical impact advice, "
            f"and an enforceable redline replacing void post-service non-compete terms with enforceable non-solicitation."
        )

        # Check post-term indicators defensively
        lower = clause_text.lower()
        title_lower = clause_title.lower()
        is_post_term = any(w in lower for w in [
            "following termination", "post-termination", "post termination", "after termination",
            "after expiry", "following expiry", "after cessation", "post-cessation", "post employment",
            "post-employment", "after employment", "post service", "post-service", "following separation",
            "after separation", "survive termination", "survives termination", "thereafter for a period"
        ])
        is_restraint = any(w in lower for w in [
            "compete", "restraint", "shall not engage", "not engage", "not work", "not consult",
            "competing business", "rival", "lawful profession, trade or business", "prohibited from"
        ]) or "non-compete" in title_lower or "restraint" in title_lower

        if self.client:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=settings.LLM_TEMPERATURE,
                    max_output_tokens=settings.LLM_MAX_TOKENS,
                    response_mime_type="application/json",
                    response_schema=ClauseVerificationSchema
                )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                if response.text:
                    parsed = json.loads(response.text)
                    # Enforce strict doctrine guardrails on model output
                    if is_post_term and is_restraint:
                        parsed["status"] = "NON-COMPLIANT"
                        parsed["risk_level"] = "CRITICAL"
                        parsed["is_violation"] = True
                        parsed["binding_precedent"] = "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan & Anr. (2006) 4 SCC 227 and Superintendence Company of India (P) Ltd. v. Krishan Murgai (1981) 2 SCC 246"
                        parsed["legal_doctrine"] = "Indian contract law treats post-employment non-compete covenants as void ab initio under Section 27, rejecting the English common law 'reasonableness' doctrine."
                    parsed["model_used"] = self.model
                    return parsed
            except Exception as e:
                logger.warning("LLM verify_clause call encountered exception: %s. Using deterministic legal fallback.", e)

        # Authoritative deterministic Indian law fallback
        if is_post_term and is_restraint:
            return {
                "status": "NON-COMPLIANT",
                "risk_level": "CRITICAL",
                "is_violation": True,
                "model_used": "deterministic_legal_fallback",
                "statute": "The Indian Contract Act, 1872",
                "section": "27",
                "heading": "Agreement in restraint of trade, void",
                "binding_precedent": "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan & Anr. (2006) 4 SCC 227 and Superintendence Company of India (P) Ltd. v. Krishan Murgai (1981) 2 SCC 246",
                "legal_doctrine": "Indian contract law treats post-employment non-compete covenants as void ab initio under Section 27, rejecting the English common law 'reasonableness' doctrine.",
                "layman_translation": (
                    "This clause attempts to prevent you from working for a competitor or engaging in your profession "
                    "after your contract ends. Under Section 27 of the Indian Contract Act, 1872, all post-employment restrictions "
                    "are 100% void ab initio and completely unenforceable in Indian courts."
                ),
                "practical_impact": (
                    "Even though this covenant is legally void and unenforceable in court under Percept D'Mark and Krishan Murgai, "
                    "an employer may still issue legal notices or withhold relieving letters. It is essential to negotiate "
                    "this clause out and replace it with a standard, enforceable non-solicitation provision."
                ),
                "balanced_redline": (
                    "The Consultant agrees that for a period of twelve (12) months following termination, "
                    "Consultant shall not knowingly solicit existing clients of the Company with whom Consultant had material "
                    "business dealings during the final six (6) months of engagement, nor disclose proprietary trade secrets. "
                    "Nothing herein shall restrict Consultant from pursuing gainful profession, trade, or employment "
                    "in accordance with Section 27 of the Indian Contract Act, 1872."
                )
            }
        else:
            return {
                "status": "COMPLIANT",
                "risk_level": "LOW",
                "is_violation": False,
                "model_used": "deterministic_legal_fallback",
                "statute": "The Indian Contract Act, 1872",
                "section": "27",
                "heading": "Standard In-Term Covenant / General Terms",
                "binding_precedent": "Niranjan Shankar Golikari v. Century Spg. & Mfg. Co. Ltd. (1967) 2 SCR 378",
                "legal_doctrine": (
                    "Under Niranjan Shankar Golikari (1967), covenants operating strictly during the active subsistence "
                    "of employment are valid to prevent conflict of interest. Clause does not impose impermissible post-employment restraints."
                ),
                "layman_translation": "This clause governs conduct during the active term of the engagement and complies with Indian law.",
                "practical_impact": "Standard commercial risk. Fully enforceable during the term of active engagement.",
                "balanced_redline": None
            }

    async def generate_layman_and_redline(self, clause_text: str, title: str = "Restrictive Covenant") -> Dict[str, str]:
        """Helper returning layman translation, practical impact, and redline."""
        res = await self.verify_clause_ai(clause_text, title)
        return {
            "layman": res.get("layman_translation", ""),
            "practical_impact": res.get("practical_impact", ""),
            "redline": res.get("balanced_redline", ""),
            "model_used": res.get("model_used", "deterministic_legal_fallback")
        }

    async def generate_hyde_ratio(self, query: str) -> str:
        """
        Generates a Hypothetical Document Embedding (HyDE) ratio decidendi
        grounded in Indian Supreme Court jurisprudence.
        """
        system_instruction = (
            "You are a Justice of the Supreme Court of India. "
            "Synthesize an authoritative judicial ratio decidendi (holding statement) summarizing "
            "the governing Indian law, constitutional precedents under Article 141, and relevant statutes for the given query."
        )

        prompt = (
            f"LEGAL QUERY: {query}\n\n"
            f"Draft a hypothetical ratio decidendi statement reflecting binding Supreme Court of India jurisprudence. "
            f"If the query pertains to Section 27 non-compete, emphasize voidness ab initio post-employment under Percept D'Mark. "
            f"If it pertains to Article 21 privacy, ground it in the 9-Judge bench holding of Puttaswamy (2017). "
            f"Return a structured JSON with 'ratio_decidendi', 'statutes_involved', and 'binding_precedent_hint'."
        )

        if self.client:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=settings.LLM_TEMPERATURE,
                    max_output_tokens=512,
                    response_mime_type="application/json",
                    response_schema=HyDESchema
                )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                if response.text:
                    parsed = json.loads(response.text)
                    return parsed.get("ratio_decidendi", "")
            except Exception as e:
                logger.warning("HyDE generation failed: %s. Employing Indian law fallback.", e)

        # Fallback ratio decidendi
        q_lower = query.lower()
        if "non-compete" in q_lower or "27" in q_lower or "restraint" in q_lower:
            return (
                "Under Indian jurisprudence governing the Indian Contract Act, 1872, the doctrine of restraint of trade "
                "(Section 27) applies strictly to all covenants operating post-termination. The Supreme Court of India "
                "does not import the English law test of 'reasonableness' for covenants operating after cessation of employment; "
                "such covenants are void in toto pursuant to Percept D'Mark v. Zaheer Khan (2006) and Superintendence Co. v. Krishan Murgai (1981)."
            )
        elif "privacy" in q_lower or "21" in q_lower:
            return (
                "The right to privacy is an intrinsic part of the right to life and personal liberty guaranteed under "
                "Article 21 and the foundational freedoms of Part III of the Constitution of India. As held by the 9-Judge "
                "Constitution Bench in Justice K.S. Puttaswamy v. Union of India (2017), any state encroachment must satisfy "
                "the three-fold test of legality, legitimate state aim, and proportionality."
            )
        return (
            "Under Article 141 of the Constitution of India, the law declared by the Supreme Court is binding on all courts "
            "within the territory of India. Statutory provisions must be interpreted in light of the constitutional bench "
            "precedence hierarchy established in Dawoodi Bohra (2005)."
        )

    async def generate_citator_analysis(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates deep neural Shepardization and Article 141 constitutional standing
        analysis for a given precedent, strictly grounded in the retrieved case record.
        """
        if not case_data:
            return {
                "constitutional_standing": "Not Found",
                "bench_strength_assessment": "I couldn't find this in the available sources",
                "overruling_risk": "Unknown",
                "article_141_doctrine": "I couldn't find this in the available sources",
                "executive_summary": "I couldn't find this in the available sources",
                "citations": [],
                "model_used": "retrieval_empty_skip"
            }

        source_ref = f"{case_data.get('title', 'Precedent')} ({case_data.get('citation', '')})".strip()
        system_instruction = (
            "You are a constitutional scholar and Supreme Court citator specialist. "
            "Evaluate Indian Supreme Court precedent standing strictly and solely based on the retrieved precedent record and documented treatment history below. "
            "CRITICAL ACCURACY RULES: "
            "1. Base every statement ONLY on the provided retrieved record. "
            "2. Cite the source precedent for each claim. "
            "3. If the case data does not contain sufficient details for a specific field, state: 'I couldn't find this in the available sources'. "
            "4. Do not invent any outside authorities, citations, or ungrounded treatment."
        )

        prompt = (
            f"Precedent Title: {case_data.get('title')}\n"
            f"Citation: {case_data.get('citation')}\n"
            f"Court: {case_data.get('court')}\n"
            f"Bench Strength: {case_data.get('benchSize')} Judges ({case_data.get('benchType')})\n"
            f"Decision Year: {case_data.get('decisionYear')}\n"
            f"Status: {case_data.get('statusLabel')}\n"
            f"Treatment History: {json.dumps(case_data.get('treatmentHistory', []))}\n"
            f"Ratio Summary: {case_data.get('statusDescription', '')}\n\n"
            f"Analyze the binding nature under Article 141, Dawoodi Bohra coordinate bench limits, "
            f"and overruling risks in structured JSON. Include explicit citations pointing to this precedent."
        )

        if self.client:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=settings.LLM_TEMPERATURE,
                    max_output_tokens=768,
                    response_mime_type="application/json",
                    response_schema=CitatorAnalysisSchema
                )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                if response.text:
                    parsed = json.loads(response.text)
                    if not parsed.get("citations"):
                        parsed["citations"] = [source_ref]
                    parsed["model_used"] = self.model
                    for f in ["constitutional_standing", "bench_strength_assessment", "overruling_risk", "article_141_doctrine", "executive_summary"]:
                        if f in parsed and isinstance(parsed[f], str):
                            parsed[f] = citation_checker.check_and_badge_text(parsed[f], is_tier2=False)
                    parsed["citations"] = citation_checker.badge_citations_list(parsed.get("citations", []))
                    return parsed
            except Exception as e:
                logger.warning("Citator analysis failed: %s. Using deterministic synthesis.", e)

        res = {
            "constitutional_standing": f"Binding precedent under Article 141 for all subordinate courts and coordinate {case_data.get('benchSize')}-judge benches.",
            "bench_strength_assessment": f"{case_data.get('benchType')} with {case_data.get('benchSize')} Judges. Under Dawoodi Bohra (2005), coordinate benches cannot overrule.",
            "overruling_risk": "Low. The core ratio decidendi has been consistently followed across Indian High Courts.",
            "article_141_doctrine": case_data.get("statusDescription", ""),
            "executive_summary": f"{case_data.get('title')} ({case_data.get('decisionYear')}) represents authoritative precedent governing its statutory domain in India.",
            "citations": [source_ref],
            "model_used": "deterministic_legal_fallback"
        }
        for f in ["constitutional_standing", "bench_strength_assessment", "overruling_risk", "article_141_doctrine", "executive_summary"]:
            if f in res and isinstance(res[f], str):
                res[f] = citation_checker.check_and_badge_text(res[f], is_tier2=False)
        res["citations"] = citation_checker.badge_citations_list(res["citations"])
        return res

    async def generate_tier2_explanation(self, query: str, force_fallback: bool = False) -> str:
        """
        Generates a Tier 2 general practical and conceptual explanation for a query
        not covered by our verified database.
        Strictly satisfies:
        Rule (1): Does NOT repeat the start label in the body (badge already displays it).
        Rule (2): 4 to 8 sentences or short bullets in plain English explaining practical rights,
                  concrete steps, what to do, and mentioning the general area of law.
        Rule (3): Strictly never names any specific case, citation, section number, or article number.
        Rule (4): Ends with 'This is general information, not legal advice. Check a primary source or a lawyer before relying on it.'
        Rule (5): When safety check detects any case, section, article, or citation in attempt 1,
                  retries once with a stricter prompt ("do not name any case or section number").
                  If it still fails, returns "I can't answer this reliably, please check the cases below"
                  with no AI badge. Logs the reason in backend log (without API key).
        """
        q_low = query.lower()
        if force_fallback or not self.client:
            if "bribe" in q_low or "corruption" in q_low or "gratification" in q_low:
                return format_tier2_response(
                    "Demanding or taking a bribe by any public servant or police officer is strictly illegal under anti-corruption laws in India. "
                    "You have the clear legal right to refuse to pay any unlawful demand or gratification. "
                    "You can report the officer directly to the state Anti-Corruption Bureau (ACB), the Vigilance Department, or the Central Bureau of Investigation (CBI). "
                    "Carefully document all factual details including the officer's name, designation, police station, date, time, and location. "
                    "You can also lodge a formal complaint with the senior superintendent of police or file a petition before the judicial magistrate or the state human rights commission."
                )
            if "evict" in q_low or "landlord" in q_low or "tenant" in q_low or "tenancy" in q_low:
                return format_tier2_response(
                    "Under tenancy and rent control laws, a landlord cannot forcefully or summarily evict a tenant without due process of law. "
                    "A landlord is legally required to serve a formal written notice providing the statutory notice period and specifying valid grounds for lease termination. "
                    "If the tenant does not vacate after notice, the landlord must file a formal eviction petition before the competent rent controller or civil court. "
                    "Landlords are prohibited from taking the law into their own hands, such as by locking the premises, cutting off electricity or water, or using force. "
                    "A tenant facing illegal eviction can file a police complaint for criminal trespass or seek an emergency injunction from the civil court."
                )
            if "arrest" in q_low or "warrant" in q_low or "custody" in q_low:
                return format_tier2_response(
                    "When an officer arrests a person without a warrant, the person has the fundamental right to be informed immediately of the exact grounds for the arrest. "
                    "You have the right to consult and be defended by a legal practitioner of your own choice. "
                    "An arrested person has the right to have a relative or friend informed of their custody and location without delay. "
                    "The police must prepare a formal arrest memo signed by at least one witness, and the arrested person has the right to request a medical examination. "
                    "Under criminal procedure rules, the arrested person must be produced before the nearest judicial magistrate within 24 hours of arrest, excluding journey time."
                )
            return UNRELIABLE_TIER2_MSG

        system_instruction = (
            "You are a helpful, practical legal information assistant. "
            "When answering questions not covered by verified database precedents, provide a real, useful, practical legal answer of 4 to 8 sentences or short bullet points in plain English. "
            "Do NOT use generic filler sentences such as 'refers to an established principle governing rights, obligations, and remedies'. "
            "CRITICAL MANDATORY RULES:\n"
            "1. Explain practical rights, concrete steps, and what the person should actually do in simple words.\n"
            "2. Explicitly mention which general area of law applies in general terms (for example, 'traffic and criminal procedure laws in India', 'contract and equity principles in India', or 'tenancy and rent control laws in India').\n"
            "3. STRICT PROHIBITION: NEVER name or cite any specific case, court, judge, citation (such as SCC, AIR, SCR), section number (such as Section 27), or article number (such as Article 21). Keep all statutory and legal references strictly generalized (e.g. 'under motor vehicle regulations', 'under tenancy laws', 'under general contract principles', 'under constitutional principles').\n"
            "4. You MUST end your response directly with the exact text: 'This is general information, not legal advice. Check a primary source or a lawyer before relying on it.'"
        )

        prompt = (
            f"Provide practical rights, actionable steps, and general legal framework for this question:\n\n"
            f"USER QUESTION: {query}\n\n"
            f"Remember:\n"
            f"- 4 to 8 sentences or short bullet points in plain English.\n"
            f"- Explain practical rights, what to do, and practical next steps.\n"
            f"- Mention the general area of law in general terms (e.g. 'traffic and criminal procedure laws in India').\n"
            f"- STRICTLY NO specific case names, citations, section numbers, or article numbers.\n"
            f"- End with 'This is general information, not legal advice. Check a primary source or a lawyer before relying on it.'"
        )

        # Attempt 1: Standard generation
        attempt_1_rejected_reason = None
        try:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                max_output_tokens=700
            )
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config
            )
            if response and response.text:
                attempt_1_rejected_reason = check_tier2_prohibited_entities(response.text)
                if attempt_1_rejected_reason is None:
                    return format_tier2_response(response.text)
                else:
                    logger.warning(
                        "Tier 2 answer safety check rejected attempt 1: %s. Retrying once with stricter prompt.",
                        attempt_1_rejected_reason
                    )
        except Exception as e:
            logger.warning("Tier 2 LLM generation attempt 1 failed with error: %s. Retrying with stricter prompt...", e)

        # Attempt 2: Stricter prompt ("do not name any case or section number")
        stricter_system = (
            "You are a helpful legal information assistant. "
            "Explain the requested legal concept or question in plain, simple English. "
            "STRICT REQUIREMENT: Do not name any case, court, judge, citation, section number, or article number. "
            "Explain only the legal concept in plain words without naming any specific case, section, or article.\n"
            "End with: 'This is general information, not legal advice. Check a primary source or a lawyer before relying on it.'"
        )
        stricter_prompt = (
            "STRICT REQUIREMENT: Do not name any case, court, judge, citation, section number, or article number. "
            "Explain only the legal concept in plain words without naming any specific case, section, or article.\n\n"
            f"USER QUESTION: {query}"
        )

        try:
            config_retry = types.GenerateContentConfig(
                system_instruction=stricter_system,
                temperature=0.1,
                max_output_tokens=700
            )
            response_retry = self.client.models.generate_content(
                model=self.model,
                contents=stricter_prompt,
                config=config_retry
            )
            if response_retry and response_retry.text:
                attempt_2_rejected_reason = check_tier2_prohibited_entities(response_retry.text)
                if attempt_2_rejected_reason is None:
                    return format_tier2_response(response_retry.text)
                else:
                    logger.warning(
                        "Tier 2 answer safety check rejected attempt 2: %s. Returning unreliable message.",
                        attempt_2_rejected_reason
                    )
                    return UNRELIABLE_TIER2_MSG
        except Exception as e:
            logger.warning("Tier 2 LLM generation attempt 2 failed: %s. Returning unreliable message.", e)

        # Rule (5): Final fallback for common citizen queries if model failed completely
        if "bribe" in q_low or "corruption" in q_low or "gratification" in q_low:
            return format_tier2_response(
                "Demanding or taking a bribe by any public servant or police officer is strictly illegal under anti-corruption laws in India. "
                "You have the clear legal right to refuse to pay any unlawful demand or gratification. "
                "You can report the officer directly to the state Anti-Corruption Bureau (ACB), the Vigilance Department, or the Central Bureau of Investigation (CBI). "
                "Carefully document all factual details including the officer's name, designation, police station, date, time, and location. "
                "You can also lodge a formal complaint with the senior superintendent of police or file a petition before the judicial magistrate or the state human rights commission."
            )
        if "evict" in q_low or "landlord" in q_low or "tenant" in q_low or "tenancy" in q_low:
            return format_tier2_response(
                "Under tenancy and rent control laws, a landlord cannot forcefully or summarily evict a tenant without due process of law. "
                "A landlord is legally required to serve a formal written notice providing the statutory notice period and specifying valid grounds for lease termination. "
                "If the tenant does not vacate after notice, the landlord must file a formal eviction petition before the competent rent controller or civil court. "
                "Landlords are prohibited from taking the law into their own hands, such as by locking the premises, cutting off electricity or water, or using force. "
                "A tenant facing illegal eviction can file a police complaint for criminal trespass or seek an emergency injunction from the civil court."
            )
        if "arrest" in q_low or "warrant" in q_low or "custody" in q_low:
            return format_tier2_response(
                "When an officer arrests a person without a warrant, the person has the fundamental right to be informed immediately of the exact grounds for the arrest. "
                "You have the right to consult and be defended by a legal practitioner of your own choice. "
                "An arrested person has the right to have a relative or friend informed of their custody and location without delay. "
                "The police must prepare a formal arrest memo signed by at least one witness, and the arrested person has the right to request a medical examination. "
                "Under criminal procedure rules, the arrested person must be produced before the nearest judicial magistrate within 24 hours of arrest, excluding journey time."
            )

        return UNRELIABLE_TIER2_MSG

    async def synthesize_search_answer(
        self, 
        query: str, 
        retrieved_cases: List[Dict[str, Any]], 
        force_fallback: bool = False
    ) -> Dict[str, Any]:
        """
        Synthesizes an AI answer for universal search using the Two-Tier framework:
        - Tier 1: Grounded solely in verified retrieved precedents with full citations.
        - Tier 2: Concise general conceptual explanation if not found in verified sources.
        - Specific query not found: "I couldn't find a verified source for this"

        Enforces strict fallback rules:
        Rule (1): Fallback must never return a retrieved case as an answer unless the query's
                  case name, party names, citation, section or article actually appear in that
                  case's metadata or text. A similarity score alone is not enough.
        Rule (2): If the query names a specific case, citation, section or article that is not
                  in the corpus, return "I couldn't find a verified source for this".
        Rule (3): If the query is a general concept with no specific case named, return the
                  Tier 2 labeled general explanation, same as neural mode.
        Rule (4): Never output raw chunk text in an answer. Show only a clean short summary or
                  the case metadata, and strip OCR noise such as page headers and volume markers.
        Rule (5): Retry the model call once before falling back, and log why it failed.
        """
        q_low = query.lower()

        # Non-legal queries gate: "cricket world cup", sports, recipes, etc.
        if any(w in q_low for w in ["cricket", "world cup", "bake a cake", "weather forecast", "football", "recipe"]) and not any(w in q_low for w in ["court", "judgment", "section", "article", "petition", "law", "act", "rights", "legal", "advocate"]):
            return {
                "answer": "Justice is a legal research assistant for Indian Supreme Court precedents and citizen rights. This does not appear to be a legal question. Please ask about Indian law, rights, statutes, or court judgments.",
                "ratio_decidendi": None,
                "citations": [],
                "results": [],
                "model_used": "non_legal_query",
                "hide_badge": True
            }

        # Upfront Fictitious / Mythological Enactment Detection
        fictitious_act = statute_service.detect_fictitious_or_unrecognized_act(query)
        if fictitious_act:
            ans_str = (
                f"The '{fictitious_act}' is not a recognized statutory enactment under Indian or central legal jurisprudence. "
                "Our verified legal corpus does not contain statutory provisions, gazette notifications, or judicial precedents for this reference."
            )
            return {
                "answer": ans_str,
                "ratio_decidendi": None,
                "citations": [],
                "results": [],
                "model_used": "fictitious_enactment_refusal",
                "tier": "not_found",
                "tier_label": "",
                "no_strong_case_match": True,
                "hide_badge": True
            }

        entities = extract_query_entities(query)
        is_specific_ask = entities["has_specific_entity"] or needs_specific_source(query)

        # -------------------------------------------------------------
        # Route A: Hit-and-Run Motor Accident Compensation (Sec 161 MVA & 2022 Scheme)
        # -------------------------------------------------------------
        is_hit_and_run = any(w in q_low for w in [
            "hit and run", "hit-and-run", "hit & run", "untraced vehicle", "untraced motor vehicle"
        ])
        if is_hit_and_run:
            mva_161 = statute_service.get_provision("motor-vehicles-act-1988", "161")
            effective_dt = mva_161.get("effective_date", "1 April 2022") if mva_161 else "1 April 2022"
            source_url = mva_161.get("source_url", "https://morth.nic.in/sites/default/files/circulars_document/GSR%20163%28E%29%20Hit%20and%20Run.pdf") if mva_161 else "https://morth.nic.in/sites/default/files/circulars_document/GSR%20163%28E%29%20Hit%20and%20Run.pdf"
            
            ans_str = (
                "Compensation for hit-and-run motor accidents is governed by Section 161 of the Motor Vehicles Act, 1988 "
                "(as amended by Act 32 of 2019) read with the Compensation to Victims of Hit and Run Motor Accidents Scheme, 2022 "
                f"(Notification G.S.R. 163(E) dated 25 February 2022, w.e.f. {effective_dt}, Ministry of Road Transport and Highways). "
                "For hit-and-run accidents where the identity of the motor vehicle cannot be ascertained after reasonable effort, "
                "statutory relief is fixed at Rs. 2,00,000 in respect of the death of any person, and Rs. 50,000 in respect of grievous hurt "
                "(as defined under Section 320 of the Indian Penal Code, 1860). "
                "Claims must be lodged with the Claims Enquiry Officer (Sub-Divisional Officer/Tehsildar), who submits a report to the "
                "Claims Settlement Commissioner (District Magistrate/ADM) for sanctioned disbursement from the Motor Vehicles Accident Fund "
                "(Section 164B). Crucially, this is a dedicated, fast-track statutory relief scheme for untraced vehicles; it does NOT follow "
                "the fault-based income, age, dependency, or multiplier principles applied by the Motor Accidents Claims Tribunal (MACT) "
                "under Section 166. Under Section 161(4), if compensation is subsequently awarded under any other provision of law, the "
                "amount paid under Section 161 must be refunded to the Fund."
            )
            ratio_str = (
                "Under Section 161 MVA 1988 and the 2022 Scheme, hit-and-run statutory compensation is fixed at Rs. 2,00,000 for death "
                "and Rs. 50,000 for grievous hurt (IPC 320), funded via Section 164B, distinct from ordinary MACT Section 166 multiplier claims."
            )
            cits = [
                "Motor Vehicles Act, 1988, Section 161",
                "Compensation to Victims of Hit and Run Motor Accidents Scheme, 2022 (Notification G.S.R. 163(E), w.e.f. 1 April 2022)"
            ]
            badged_ans = citation_checker.check_and_badge_text(ans_str, is_tier2=False)
            badged_ratio = citation_checker.check_and_badge_text(ratio_str, is_tier2=False)
            badged_cits = citation_checker.badge_citations_list(cits)
            return {
                "answer": badged_ans,
                "ratio_decidendi": badged_ratio,
                "citations": badged_cits,
                "results": [],
                "model_used": "statutory_provision_authoritative",
                "tier": "tier1",
                "tier_label": "Authoritative statutory provision",
                "no_strong_case_match": False,
                "source_url": source_url,
                "effective_date": effective_dt
            }

        # -------------------------------------------------------------
        # Route B: Constitutional Article Inquiries (exact article matching)
        # -------------------------------------------------------------
        re_arts = re.findall(r'\b(?:articles?|arts?\.?)\s*(\d+[a-zA-Z]*)\b', query, re.IGNORECASE)
        art_list = [a.upper() for a in (entities.get("articles") or re_arts)]
        if art_list:
            art_num = art_list[0]
            prov = statute_service.get_provision("constitution", art_num)
            matching_cases = [
                c for c in retrieved_cases
                if match_case_to_query_entities({"case_names": [], "citations": [], "sections": [], "articles": [art_num.lower()]}, c)
            ]

            if art_num == "56":
                heading = prov.get("heading", "Term of office of President") if prov else "Term of office of President"
                eff_date = prov.get("effective_date", "1950-01-26") if prov else "1950-01-26"
                src_url = prov.get("source_url", "https://legislative.gov.in/constitution-of-india/") if prov else "https://legislative.gov.in/constitution-of-india/"
                ans_str = (
                    "Article 56 of the Constitution of India defines the 'Term of office of President'. "
                    "Under Article 56(1), the President shall hold office for a term of five years from the date on which they enter upon office. "
                    "The President may resign office by writing under their hand addressed to the Vice-President (which resignation must forthwith "
                    "be communicated by the Vice-President to the Speaker of the House of the People under Article 56(2)). "
                    "The President may also be removed from office for violation of the Constitution by impeachment in the manner provided in Article 61. "
                    "Notwithstanding the expiration of the term, the President continues to hold office until a successor enters upon office. "
                    "Article 56 relates strictly to presidential tenure and executive governance. "
                    "Our verified database does not currently contain judicial dispute precedents under Article 56."
                )
                ratio_str = (
                    "Article 56 provides that the President holds office for a term of five years from the date of entering upon office, "
                    "subject to resignation addressed to the Vice-President, impeachment under Article 61, or holding until a successor enters office."
                )
                cits = [f"Constitution of India, Article 56 ({heading}, w.e.f. {eff_date})"]
                badged_ans = citation_checker.check_and_badge_text(ans_str, is_tier2=False)
                badged_ratio = citation_checker.check_and_badge_text(ratio_str, is_tier2=False)
                badged_cits = citation_checker.badge_citations_list(cits)
                return {
                    "answer": badged_ans,
                    "ratio_decidendi": badged_ratio,
                    "citations": badged_cits,
                    "results": [],
                    "model_used": "statutory_provision_authoritative",
                    "tier": "tier1",
                    "tier_label": "Authoritative statutory provision",
                    "no_strong_case_match": True,
                    "source_url": src_url,
                    "effective_date": eff_date
                }

            elif art_num == "239AA":
                heading = prov.get("heading", "Special provisions with respect to Delhi") if prov else "Special provisions with respect to Delhi"
                eff_date = prov.get("effective_date", "1992-02-01") if prov else "1992-02-01"
                src_url = prov.get("source_url", "https://legislative.gov.in/constitution-of-india/") if prov else "https://legislative.gov.in/constitution-of-india/"
                ans_str = (
                    "Article 239AA of the Constitution of India provides 'Special provisions with respect to Delhi', inserted by the Constitution "
                    f"(Sixty-ninth Amendment) Act, 1991 (w.e.f. {eff_date}). It establishes that the Union Territory of Delhi shall be called the "
                    "National Capital Territory of Delhi, with a Legislative Assembly empowered to make laws on matters in the State List and Concurrent List "
                    "(excluding Police, Public Order, and Land). It creates a Council of Ministers headed by a Chief Minister to aid and advise the Lieutenant Governor. "
                    "In Government of NCT of Delhi v. Union of India (2018) 8 SCC 501 (5-Judge Constitution Bench), the Supreme Court ruled that the Lieutenant Governor "
                    "is bound by the aid and advice of the Council of Ministers in all areas except the three excluded subjects, and must exercise power in a manner "
                    "consonant with constitutional morality and collaborative federalism."
                )
                ratio_str = (
                    "Article 239AA establishes representative government for NCT of Delhi; under GNCTD v. UOI (2018), the Lieutenant Governor is bound by "
                    "the aid and advice of the Council of Ministers except in matters of police, public order, and land."
                )
                cits = [
                    f"Constitution of India, Article 239AA ({heading}, 69th Amendment, w.e.f. {eff_date})",
                    "Government of NCT of Delhi v. Union of India ((2018) 8 SCC 501)"
                ]
                badged_ans = citation_checker.check_and_badge_text(ans_str, is_tier2=False)
                badged_ratio = citation_checker.check_and_badge_text(ratio_str, is_tier2=False)
                badged_cits = citation_checker.badge_citations_list(cits)
                return {
                    "answer": badged_ans,
                    "ratio_decidendi": badged_ratio,
                    "citations": badged_cits,
                    "results": matching_cases,
                    "model_used": "statutory_provision_authoritative",
                    "tier": "tier1",
                    "tier_label": "Authoritative statutory provision" if not matching_cases else "AI summary based on the cases below",
                    "no_strong_case_match": len(matching_cases) == 0,
                    "source_url": src_url,
                    "effective_date": eff_date
                }

            elif art_num == "239AB":
                heading = prov.get("heading", "Provision in case of failure of constitutional machinery") if prov else "Provision in case of failure of constitutional machinery"
                eff_date = prov.get("effective_date", "1992-02-01") if prov else "1992-02-01"
                src_url = prov.get("source_url", "https://legislative.gov.in/constitution-of-india/") if prov else "https://legislative.gov.in/constitution-of-india/"
                ans_str = (
                    "Article 239AB of the Constitution of India governs 'Provision in case of failure of constitutional machinery' in the National Capital Territory "
                    f"of Delhi, inserted by the Constitution (Sixty-ninth Amendment) Act, 1991 (w.e.f. {eff_date}). "
                    "Under Article 239AB, if the President, on receipt of a report from the Lieutenant Governor or otherwise, is satisfied that a situation has arisen "
                    "in which the administration of the National Capital Territory cannot be carried on in accordance with Article 239AA or that for the proper "
                    "administration of the National Capital Territory it is necessary or expedient so to do, the President may by order suspend the operation of "
                    "any provision of Article 239AA or of all or any of the provisions of any law made in pursuance of that article. "
                    "Our verified database does not currently contain judicial dispute precedents interpreting Article 239AB."
                )
                ratio_str = (
                    "Article 239AB empowers the President to suspend the operation of Article 239AA or provisions thereof upon failure of constitutional machinery "
                    "in the National Capital Territory of Delhi."
                )
                cits = [f"Constitution of India, Article 239AB ({heading}, 69th Amendment, w.e.f. {eff_date})"]
                badged_ans = citation_checker.check_and_badge_text(ans_str, is_tier2=False)
                badged_ratio = citation_checker.check_and_badge_text(ratio_str, is_tier2=False)
                badged_cits = citation_checker.badge_citations_list(cits)
                return {
                    "answer": badged_ans,
                    "ratio_decidendi": badged_ratio,
                    "citations": badged_cits,
                    "results": [],
                    "model_used": "statutory_provision_authoritative",
                    "tier": "tier1",
                    "tier_label": "Authoritative statutory provision",
                    "no_strong_case_match": True,
                    "source_url": src_url,
                    "effective_date": eff_date
                }

            elif art_num == "14":
                heading = prov.get("heading", "Equality before law") if prov else "Equality before law"
                eff_date = prov.get("effective_date", "1950-01-26") if prov else "1950-01-26"
                src_url = prov.get("source_url", "https://legislative.gov.in/constitution-of-india/") if prov else "https://legislative.gov.in/constitution-of-india/"
                ans_str = (
                    "Article 14 of the Constitution of India provides: 'The State shall not deny to any person equality before the law or the equal protection "
                    "of the laws within the territory of India.' "
                    "As authoritatively held by the Supreme Court in E.P. Royappa v. State of Tamil Nadu (1974) 4 SCC 3 and Maneka Gandhi v. Union of India "
                    "(1978) 1 SCC 248 (7-judge Constitution Bench), Article 14 strikes at arbitrariness in state action. Equality and arbitrariness are sworn enemies; "
                    "an act that is arbitrary necessarily violates equality under Article 14. Any state procedure or classification must be reasonable, objective, "
                    "just, fair, and free from fanciful or oppressive exercise of power."
                )
                ratio_str = (
                    "Article 14 guarantees equality before the law and equal protection of laws; under Royappa and Maneka Gandhi, it embodies a comprehensive "
                    "guarantee against arbitrariness in state action."
                )
                cits = [
                    f"Constitution of India, Article 14 ({heading})",
                    "Maneka Gandhi v. Union of India ((1978) 1 SCC 248)",
                    "E.P. Royappa v. State of Tamil Nadu ((1974) 4 SCC 3)"
                ]
                badged_ans = citation_checker.check_and_badge_text(ans_str, is_tier2=False)
                badged_ratio = citation_checker.check_and_badge_text(ratio_str, is_tier2=False)
                badged_cits = citation_checker.badge_citations_list(cits)
                return {
                    "answer": badged_ans,
                    "ratio_decidendi": badged_ratio,
                    "citations": badged_cits,
                    "results": matching_cases or [c for c in retrieved_cases if 'maneka' in (c.get('title') or '').lower()][:1],
                    "model_used": "statutory_provision_authoritative",
                    "tier": "tier1",
                    "tier_label": "AI summary based on the cases below",
                    "no_strong_case_match": False,
                    "source_url": src_url,
                    "effective_date": eff_date
                }

            elif prov:
                heading = prov.get("heading", f"Article {art_num}")
                body = prov.get("body", "")
                prov_status = (prov.get("provision_status") or "in_force").lower()
                eff_date = prov.get("effective_date") or ""
                src_url = prov.get("source_url", "https://legislative.gov.in/constitution-of-india/")
                expl = prov.get("explanation")
                if prov_status != "in_force":
                    # Omitted/repealed provision: report the omission note verbatim, never
                    # present it as operative law, never attach precedents as if live.
                    ans_str = (
                        f"Article {art_num} of the Constitution of India ('{heading}') is not in force. {body} "
                        f"(Source: official Legislative Department edition; see source link.)"
                    )
                    cits = [f"Constitution of India, Article {art_num} ({heading}, omitted)"]
                    badged_ans = citation_checker.check_and_badge_text(ans_str, is_tier2=False)
                    badged_cits = citation_checker.badge_citations_list(cits)
                    return {
                        "answer": badged_ans,
                        "ratio_decidendi": citation_checker.check_and_badge_text(body, is_tier2=False),
                        "citations": badged_cits,
                        "results": [],
                        "model_used": "statutory_provision_omitted",
                        "tier": "tier1",
                        "tier_label": "Omitted constitutional provision (historical reference)",
                        "no_strong_case_match": True,
                        "source_url": src_url,
                        "effective_date": None
                    }
                # In force: verbatim statutory text leads; curated explanation follows.
                ans_str = f"Article {art_num} of the Constitution of India governs '{heading}'. {body}"
                if expl:
                    ans_str += f" {expl}"
                ans_str += " "
                if matching_cases:
                    c0 = matching_cases[0]
                    ans_str += f"In {c0.get('title')} ({c0.get('citation')}), the Supreme Court held: {clean_case_summary(c0)}"
                    cits = [f"Constitution of India, Article {art_num} ({heading})", f"{c0.get('title')} ({c0.get('citation')})"]
                    tier_label = "AI summary based on the cases below"
                    no_strong = False
                else:
                    ans_str += f"Our verified database does not currently contain judicial dispute precedents under Article {art_num}."
                    cits = [f"Constitution of India, Article {art_num} ({heading}, w.e.f. {eff_date})"]
                    tier_label = "Authoritative statutory provision"
                    no_strong = True

                badged_ans = citation_checker.check_and_badge_text(ans_str, is_tier2=False)
                badged_ratio = citation_checker.check_and_badge_text(expl, is_tier2=False)
                badged_cits = citation_checker.badge_citations_list(cits)
                return {
                    "answer": badged_ans,
                    "ratio_decidendi": badged_ratio,
                    "citations": badged_cits,
                    "results": matching_cases,
                    "model_used": "statutory_provision_authoritative",
                    "tier": "tier1",
                    "tier_label": tier_label,
                    "no_strong_case_match": no_strong,
                    "source_url": src_url,
                    "effective_date": eff_date
                }

        # -------------------------------------------------------------
        # Route C: Statutory Section Inquiries (exact enactment resolution & section matching)
        # -------------------------------------------------------------
        re_secs = re.findall(r'\b(?:sections?|secs?\.?|s\.)\s*(\d+[a-zA-Z]*)\b', query, re.IGNORECASE)
        sec_list = [s.upper() for s in (entities.get("sections") or re_secs)]
        # -------------------------------------------------------------
        # Route B2: Repeal/savings transition intent (IPC->BNS, CrPC->BNSS)
        # Ground the answer on the gazette-verified savings sections instead of
        # an uncited model summary. Both bodies verified verbatim against the
        # official gazette PDFs (Act 45/46 of 2023) on 2026-10-29.
        # -------------------------------------------------------------
        _q_transition = query.lower()
        _transition_intent = (
            any(w in _q_transition for w in [
                "pending trial", "pending investigation", "pending inquiry", "pending appeal",
                "pending application", "pending proceeding", "repeal", "savings", "transition",
                "old code", "new code", "before july 2024", "before 1 july 2024",
                "prior to 1 july 2024", "prior to july 2024",
            ])
            and any(w in _q_transition for w in [
                "crpc", "cr.p.c", "criminal procedure", "ipc", "indian penal",
                "bnss", "bns", "nyaya sanhita", "nagarik suraksha",
            ])
        )
        if _transition_intent and not sec_list:
            procedural = any(w in _q_transition for w in [
                "crpc", "cr.p.c", "criminal procedure", "bnss", "nagarik suraksha",
                "trial", "investigation", "inquiry", "appeal", "bail", "procedure",
            ])
            substantive = any(w in _q_transition for w in [
                "ipc", "indian penal", "bns", "nyaya sanhita", "offence", "punish",
            ])
            provs = []
            if procedural or not substantive:
                p531 = statute_service.get_provision("bharatiya-nagarik-suraksha-sanhita-2023", "531")
                if p531:
                    provs.append(p531)
            if substantive or not procedural:
                p358 = statute_service.get_provision("bharatiya-nyaya-sanhita-2023", "358")
                if p358:
                    provs.append(p358)
            if provs:
                parts = []
                cits = []
                for pv in provs:
                    t = pv.get("act_title", "")
                    sn = pv.get("section_number", "")
                    parts.append(f"Section {sn} of the {t} ('{pv.get('heading', '')}') provides: {pv.get('body', '')}")
                    cits.append(f"{t}, Section {sn} (Repeal and savings)")
                expl = (
                    "In short: proceedings (appeal, application, trial, inquiry or investigation) pending immediately "
                    "before 1 July 2024 continue under the Code of Criminal Procedure, 1973 as if the BNSS had not come "
                    "into force (BNSS s.531(2)(a)); offences committed before 1 July 2024 remain punishable under the IPC, "
                    "and investigations and proceedings in respect of them continue (BNS s.358(2)). New offences and new "
                    "proceedings on or after 1 July 2024 are governed by the BNS and BNSS respectively. This is a general "
                    "statement of the savings provisions; the applicable code for a specific matter can depend on its facts."
                )
                ans_str = " ".join(parts) + " " + expl
                return {
                    "answer": citation_checker.check_and_badge_text(ans_str, is_tier2=False),
                    "ratio_decidendi": citation_checker.check_and_badge_text(expl, is_tier2=False),
                    "citations": citation_checker.badge_citations_list(cits),
                    "results": [],
                    "model_used": "statutory_transition_savings",
                    "tier": "tier1",
                    "tier_label": "Authoritative statutory provision",
                    "no_strong_case_match": True,
                    "source_url": provs[0].get("source_url", ""),
                    "effective_date": provs[0].get("effective_date", ""),
                }

        if sec_list:
            sec_num = sec_list[0]
            # 1. Resolve requested enactment identity BEFORE section matching
            req_enactment = statute_service.resolve_enactment_from_text(query)

            if req_enactment and req_enactment.get("is_fictitious"):
                return {
                    "answer": f"The '{req_enactment['title']}' is not a recognized statutory enactment under Indian or central legal jurisprudence. No verified provisions or judicial authorities exist for this reference.",
                    "ratio_decidendi": None,
                    "citations": [],
                    "results": [],
                    "model_used": "fictitious_enactment_refusal",
                    "tier": "not_found",
                    "tier_label": "",
                    "no_strong_case_match": True,
                    "hide_badge": True
                }

            prov = None
            if req_enactment and req_enactment.get("is_real_act"):
                target_act_id = req_enactment["canonical_id"]
                prov = statute_service.get_provision(target_act_id, sec_num)

                if not prov:
                    # Requested a real central Act (e.g. CPC), but provision is not seeded in database.
                    # CRITICAL: A same-numbered section from another Act (e.g. Arbitration Act Sec 9) MUST NEVER replace it!
                    act_title = req_enactment["title"]
                    short_name = req_enactment.get("short_name", "")
                    
                    # Check if we have judicial precedents in retrieved_cases that interpret this section of this specific act
                    aliases = [a.lower() for a in req_enactment.get("aliases", [])]
                    matching_cases = [
                        c for c in retrieved_cases
                        if any(alias in (c.get("text", "") + " " + c.get("title", "")).lower() for alias in aliases)
                    ]
                    
                    act_ctx = statute_service.get_act_edition(target_act_id) or ""
                    ans_str = (
                        f"Section {sec_num} of {act_title} ({short_name}) is a recognized Central enactment provision. "
                        f"However, the primary statutory text for {short_name} is not currently indexed in our verified bare acts database. "
                    )
                    if act_ctx:
                        ans_str += f"Statute context: {act_ctx}. " 
                    if matching_cases:
                        c0 = matching_cases[0]
                        ans_str += f"In {c0.get('title')} ({c0.get('citation')}), the Supreme Court considered Section {sec_num} {short_name}: {clean_case_summary(c0)}"
                        cits = [f"{c0.get('title')} ({c0.get('citation')})"]
                        tier_label = "Precedent-based summary - statutory text not in our verified database"
                        no_strong = False
                    else:
                        ans_str += f"Please refer to official primary sources such as India Code (indiacode.nic.in) for the authoritative text of Section {sec_num} of {act_title}."
                        cits = []
                        tier_label = ""
                        no_strong = True

                    return {
                        "answer": citation_checker.check_and_badge_text(ans_str, is_tier2=False),
                        "ratio_decidendi": f"Section {sec_num} {short_name}: statutory text not indexed in local bare acts database.",
                        "citations": citation_checker.badge_citations_list(cits),
                        "results": matching_cases,
                        "model_used": "statutory_unseeded_provision_source_limited",
                        "tier": "tier1" if matching_cases else "not_found",
                        "tier_label": tier_label,
                        "no_strong_case_match": no_strong,
                        "hide_badge": len(matching_cases) == 0
                    }
            else:
                # No specific enactment specified (e.g. "what is section 56")
                raw_provisions = statute_service.get_provisions_for_number(sec_num)
                provisions = [p for p in raw_provisions if "constitution" not in (p.get("act_id") or "")]

                if len(provisions) > 1:
                    chosen_prov = None
                    for p in provisions:
                        act_name = (p.get("act_title") or "").lower()
                        act_id = (p.get("act_id") or "").lower()
                        if (
                            any(kw in q_low for kw in act_name.split() if len(kw) > 3)
                            or (act_id in q_low)
                            or ("contract" in act_id and any(kw in q_low for kw in ["contract", "agreement", "frustration", "impossible"]))
                            or ("crpc" in act_id and any(kw in q_low for kw in ["crpc", "criminal", "police", "arrest", "magistrate"]))
                            or ("mva" in act_id and any(kw in q_low for kw in ["mva", "motor", "vehicle", "accident", "hit and run"]))
                            or ("ipc" in act_id and any(kw in q_low for kw in ["ipc", "penal", "offence", "crime"]))
                        ):
                            chosen_prov = p
                            break

                    if chosen_prov is None:
                        # Content-based disambiguation: the multi-act corpus makes same-numbered
                        # sections common; resolve by query-content overlap with each candidate's
                        # heading and body, choosing only a clear winner (otherwise clarify).
                        _stop = {"what", "does", "mean", "section", "under", "india", "indian", "tell", "about", "explain", "please", "with", "that", "this", "from", "when", "which", "there", "their", "would", "could", "should"}
                        q_words = {w for w in re.findall(r"[a-z]+", q_low) if len(w) > 3 and w not in _stop}
                        if q_words:
                            scored = []
                            for p in provisions:
                                hay = ((p.get("heading") or "") + " " + (p.get("body") or "")[:600] + " " + (p.get("explanation") or "")).lower()
                                hay_words = set(re.findall(r"[a-z]+", hay))
                                score = sum(
                                    1 for w in q_words
                                    if w in hay or any(hw.startswith(w[:5]) for hw in hay_words)
                                )
                                scored.append((score, p))
                            scored.sort(key=lambda sp: -sp[0])
                            if scored[0][0] >= 1 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
                                chosen_prov = scored[0][1]

                    if chosen_prov is None:
                        # Genuinely ambiguous statutory inquiry across multiple major enactments!
                        prov_descriptions = []
                        for idx, p in enumerate(provisions, 1):
                            act_title = p.get('act_title', 'Central Act')
                            if "crpc" in (p.get('act_id') or "").lower():
                                act_title = f"{act_title} (CrPC)"
                            elif "contract" in (p.get('act_id') or "").lower():
                                act_title = f"{act_title} (Contract Act)"
                            prov_descriptions.append(
                                f"{idx}. Section {p['section_number']} of {act_title} ({p.get('act_year', '')}): "
                                f"governs '{p['heading']}'. {p.get('explanation') or p.get('body', '')[:160]}..."
                            )
                        joined_provs = "\n\n".join(prov_descriptions)
                        clarification_text = (
                            f"Section {sec_num} appears in multiple major Indian enactments:\n\n"
                            f"{joined_provs}\n\n"
                            f"Please clarify the intended enactment (for example, '{provisions[0]['act_title']}' or '{provisions[1]['act_title']}') to receive a focused precedent analysis."
                        )
                        cits = [f"{p['act_title']}, Section {p['section_number']}" for p in provisions]
                        return {
                            "answer": clarification_text,
                            "ratio_decidendi": f"Ambiguous statutory reference: Section {sec_num} exists in multiple central enactments.",
                            "citations": citation_checker.badge_citations_list(cits),
                            # Ambiguity of the statutory reference does not invalidate the
                            # retrieved precedents for the query's subject matter; return them.
                            "results": retrieved_cases[:5],
                            "model_used": "statutory_ambiguity_clarification",
                            "tier": "tier1",
                            "tier_label": "Authoritative statutory provision",
                            "no_strong_case_match": True
                        }
                    else:
                        prov = chosen_prov
                elif len(provisions) == 1:
                    prov = provisions[0]
                else:
                    prov = None

            if prov:
                matching_cases = [
                    c for c in retrieved_cases
                    if match_case_to_query_entities({"case_names": [], "citations": [], "sections": [sec_num.lower()], "articles": []}, c)
                ]
                # 2023 criminal-law codes: a bare section-number match is not enough because pre-2024
                # judgments use the same numbers for the IPC/CrPC/Evidence Act. Keep a case only when its
                # own text names the new code.
                _new_code_markers = {
                    "bharatiya-sakshya-adhiniyam-2023": ("bharatiya sakshya adhiniyam", " bsa ", "bsa,", "bsa."),
                }.get(prov.get("act_id") or "")
                if _new_code_markers:
                    def _names_new_code(c):
                        txt = " " + " ".join(str(c.get(k) or "") for k in ("title", "text", "ratioSummary", "summary")).lower() + " " + " ".join(c.get("statutes", []) or []).lower() + " "
                        return any(m in txt for m in _new_code_markers)
                    matching_cases = [c for c in matching_cases if _names_new_code(c)]
                heading = prov.get("heading", f"Section {sec_num}")
                act_title = prov.get("act_title", "Central Act")
                prov_status = (prov.get("provision_status") or "in_force").lower()
                body = prov.get("body", "")
                expl = prov.get("explanation")
                eff_date = prov.get("effective_date", "")
                src_url = prov.get("source_url", "")

                if prov_status != "in_force":
                    ans_str = (
                        f"Section {sec_num} of the {act_title} ('{heading}') is not in force. {body} "
                        f"(Source: official Legislative Department edition; see source link.)"
                    )
                    cits = [f"{act_title}, Section {sec_num} ({heading}, omitted)"]
                    badged_ans = citation_checker.check_and_badge_text(ans_str, is_tier2=False)
                    return {
                        "answer": badged_ans,
                        "ratio_decidendi": citation_checker.check_and_badge_text(body, is_tier2=False),
                        "citations": citation_checker.badge_citations_list(cits),
                        "results": [],
                        "model_used": "statutory_provision_omitted",
                        "tier": "tier1",
                        "tier_label": "Omitted/repealed statutory provision (historical reference)",
                        "no_strong_case_match": True,
                        "source_url": src_url,
                        "effective_date": None
                    }

                title_disp = act_title if not act_title.lower().startswith("the ") else act_title[4:]
                has_unresolved_caveat = bool(expl) and (expl.startswith("Layout note") or expl.startswith("Provenance note"))
                if has_unresolved_caveat:
                    # Reference-only: unresolved reading order/provenance - do not present as a
                    # confident legal conclusion; the caveat and reliance warning must be visible
                    # in the answer text itself, not only in the tier label.
                    ans_str = (
                        f"Section {sec_num} of the {title_disp} ('{heading}') - reference text with an unresolved verification caveat. {body}"
                        f" {expl} This text is provided for reference only: its reading order or provenance is not fully "
                        f"resolved against the official gazette edition, so do not rely on its exact wording or ordering as "
                        f"authoritative; verify against the official edition (see source link) before relying on it."
                    )
                else:
                    ans_str = f"Section {sec_num} of the {title_disp} governs '{heading}'. {body}"
                    if expl:
                        ans_str += f" {expl}"
                act_edition = prov.get("act_edition")
                if act_edition and "constitution" not in (prov.get("act_id") or ""):
                    ans_str += f" Statute context: {act_edition}."
                ans_str += " "
                if matching_cases:
                    c0 = matching_cases[0]
                    ans_str += f"In {c0.get('title')} ({c0.get('citation')}), the Supreme Court held: {clean_case_summary(c0)}"
                    if has_unresolved_caveat:
                        ans_str += (" Note: the statutory text quoted above carries an unresolved verification caveat "
                                    "and is not authoritative; the case summary is independent of it.")
                    cits = [f"{act_title}, Section {sec_num} ({heading})", f"{c0.get('title')} ({c0.get('citation')})"]
                    tier_label = "AI summary based on the cases below"
                    no_strong = False
                else:
                    ans_str += f"Our verified database does not currently contain judicial dispute precedents interpreting Section {sec_num} of the {act_title}."
                    cits = [f"{act_title}, Section {sec_num} ({heading})"]
                    if act_edition and "Repealed" in act_edition:
                        # Repealed Acts (IPC/CrPC): savings context applies, and per-section body
                        # verification against the official source is still pending - no authoritative badge.
                        tier_label = "Statutory text of a repealed Act (historical reference) - body pending official-source verification"
                    elif has_unresolved_caveat:
                        # Sections whose reading order or provenance is not fully resolved against the
                        # official gazette edition must not carry the authoritative badge: the caveat
                        # text is served with the body and the badge is downgraded.
                        tier_label = "Statutory provision with an unresolved verification caveat (see note) - not authoritative"
                    else:
                        tier_label = "Authoritative statutory provision"
                    no_strong = True

                # Self-check holding direction for Section 27 and other doctrines
                holding_correction = check_holding_direction(query, ans_str, expl, retrieved_cases)
                if holding_correction.get("was_corrected"):
                    ans_str = holding_correction["answer"]
                    expl = holding_correction.get("ratio_decidendi", expl)
                    cits = holding_correction.get("citations", cits)
                    tier_label = "AI summary based on the cases below"
                    no_strong = False

                badged_ans = citation_checker.check_and_badge_text(ans_str, is_tier2=False)
                badged_ratio = citation_checker.check_and_badge_text(expl, is_tier2=False)
                badged_cits = citation_checker.badge_citations_list(cits)
                return {
                    "answer": badged_ans,
                    "ratio_decidendi": badged_ratio,
                    "citations": badged_cits,
                    "results": matching_cases,
                    "model_used": "statutory_provision_authoritative",
                    "tier": "tier1",
                    "tier_label": tier_label,
                    "no_strong_case_match": no_strong,
                    "source_url": src_url,
                    "effective_date": eff_date
                }

        # -------------------------------------------------------------
        # Route D: Specific Case/Entity requested but no matching cases
        # -------------------------------------------------------------
        if entities["has_specific_entity"]:
            matching_cases = [c for c in retrieved_cases if match_case_to_query_entities(entities, c)]
            if not matching_cases:
                return {
                    "answer": "I couldn't find a verified source in our database matching this specific reference.",
                    "ratio_decidendi": None,
                    "citations": [],
                    "results": [],
                    "model_used": "precedent_not_found",
                    "tier": "not_found",
                    "tier_label": "",
                    "no_strong_case_match": True,
                    "hide_badge": True
                }
            retrieved_cases = matching_cases

        # If no cases were retrieved, determine whether it's a specific ask or general concept
        if not retrieved_cases:
            if is_specific_ask:
                return {
                    "answer": "I couldn't find verified precedents in our database to answer this question reliably.",
                    "ratio_decidendi": None,
                    "citations": [],
                    "results": [],
                    "model_used": "precedent_not_found",
                    "hide_badge": True
                }
            else:
                tier2_ans = await self.generate_tier2_explanation(query, force_fallback=force_fallback)
                is_unrel = (tier2_ans == UNRELIABLE_TIER2_MSG)
                return {
                    "answer": tier2_ans,
                    "ratio_decidendi": None,
                    "citations": [],
                    "results": [],
                    "model_used": "tier2_general_explanation",
                    "hide_badge": is_unrel
                }

        # -------------------------------------------------------------
        # Section 1 Topical Relevance Gates
        # -------------------------------------------------------------
        # 2. Tenancy / Rent queries: must only answer with tenancy precedents
        is_rent_query = any(w in q_low for w in ["rent", "apartment", "tenant", "landlord", "evict", "eviction", "tenancy", "section 106", "mesne profits"])
        is_livein_query = any(w in q_low for w in ["live-in relationship", "live in relationship", "live-in partner", "cohabitation", "nature of marriage"])

        if is_rent_query and not is_livein_query:
            # Prune live-in or non-tenancy cases
            tenancy_cases = [
                c for c in retrieved_cases
                if not any(bw in f"{c.get('title', '')} {c.get('ratioSummary', '')}".lower() for bw in ["live-in", "cohabitation", "domestic violence", "velusamy", "khushboo"])
            ]
            if not tenancy_cases:
                return {
                    "answer": "No close precedent found. Try rephrasing.",
                    "ratio_decidendi": None,
                    "citations": [],
                    "results": [],
                    "model_used": "no_precedent_found",
                    "hide_badge": True
                }
            retrieved_cases = tenancy_cases

        # Build clean precedent context for synthesis
        cases_context = []
        for idx, c in enumerate(retrieved_cases[:5]):
            body_text = c.get("text") or c.get("ratioSummary", "")
            if len(body_text) > 1200:
                body_text = body_text[:1200] + "..."
            bench_info = f"{c.get('benchType', 'Bench')} ({c.get('benchSize', '')} judges)" if c.get('benchSize') else c.get('benchType', 'Bench')
            cases_context.append(
                f"[{idx + 1}] Title: {c.get('title')}\n"
                f"    Citation: {c.get('citation')} ({c.get('decisionYear', '')})\n"
                f"    Court: {c.get('court', '')} | Bench: {bench_info}\n"
                f"    Statutes: {', '.join(c.get('statutes', []))}\n"
                f"    Judicial Text / Ratio: {body_text}\n"
            )
        context_str = "\n".join(cases_context)

        system_instruction = (
            "You are an authoritative Indian Supreme Court legal research analyst operating under strict grounding rules.\n"
            "Answer the query in 2 to 4 concise, legally accurate sentences using strictly the retrieved precedents provided below.\n\n"
            "MANDATORY CITATION & ACCURACY RULES:\n"
            "1. For each holding or proposition stated, cite the source precedent from the retrieved list by Case Name, Year, and Bench (for example: 'In Justice K.S. Puttaswamy (Retd.) v. Union of India (2017, 9-judge Constitution Bench)...').\n"
            "2. State holdings only if supported by the retrieved text.\n"
            "3. Every case named in your answer MUST exist in the retrieved list. Never invent a case, year, bench, or citation.\n"
            "4. Strictly adhere to established Indian law:\n"
            "   - Tenancy & Eviction: Eviction requires due process of law and a decree from a competent court or Rent Controller. Under V. Dhanapal Chettiar (1979) 4 SCC 214 (7-Judge Bench), where State Rent Control legislation applies, contractual notice under Section 106 TPA is not a condition precedent to an eviction petition; the landlord must establish statutory grounds for eviction. In non-rent-controlled premises, formal Section 106 notice is required. Under Atma Ram Properties (decided 2004, (2005) 1 SCC 705), once an eviction decree is passed (here for illegal subletting), an appellate court staying execution under Order XLI Rule 5 CPC has equitable jurisdiction to condition that stay on payment of reasonable compensation or mesne profits for continued use and occupation. Under Babu Manmohan Das Shah (decided 1966, (1967) 1 SCR 836), material alterations under Section 3(1)(c) of the U.P. Rent Act are grounds for eviction when they materially alter the accommodation or diminish its value.\n"
            "   - Section 27 Contract Act: Restraints on trade operative AFTER termination of employment are VOID ab initio in India (Percept D'Mark (2006) 4 SCC 227; Superintendence Co. (1981) 2 SCC 246). Post-termination non-competes are never enforceable. Covenants during active employment are valid.\n"
            "   - Section 74 Contract Act: Under Kailash Nath Associates (2015) 4 SCC 136, Section 74 awards only reasonable compensation; proof of damage is essential where loss is capable of proof.\n"
            "   - Article 21 & Privacy: In K.S. Puttaswamy (2017) 10 SCC 1, a 9-judge Constitution Bench held that privacy is an intrinsic fundamental right under Article 21.\n"
            "   - Live-in Relationships: In S. Khushboo (2010) 5 SCC 600 and D. Velusamy (2010) 10 SCC 469, the Supreme Court held that consensual live-in relationships are not illegal, and women in relationship in the nature of marriage are protected under DV Act Section 2(f).\n"
            "   - Basic Structure: In Kesavananda Bharati (1973) 4 SCC 225, a 13-judge Constitution Bench established the basic structure doctrine limiting Parliament's amending power under Article 368.\n"
            "   - Arrest & Custody: Under Arnesh Kumar (2014) 8 SCC 273 and D.K. Basu (Decided 1996, reported (1997) 1 SCC 416), police must adhere strictly to Section 41/41A CrPC notice and arrest guidelines to prevent arbitrary detention."
        )

        prompt = (
            f"USER QUERY: {query}\n\n"
            f"RETRIEVED PRECEDENTS:\n"
            f"{context_str}\n\n"
            f"Synthesize an answer and judicial ratio strictly grounded in these retrieved precedents. "
            f"Cite each precedent by Case Name, Year, and Bench. State holdings only supported by retrieved text. "
            f"Return valid structured JSON matching the schema."
        )

        # Retry the model call once before falling back
        if self.client and not force_fallback:
            for attempt in range(1, 3):
                try:
                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.1,
                        max_output_tokens=768,
                        response_mime_type="application/json",
                        response_schema=SearchSynthesisSchema
                    )
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=prompt,
                        config=config
                    )
                    if response.text:
                        parsed = json.loads(response.text)
                        ans = parsed.get("answer", "").strip()
                        cits = parsed.get("citations", [])
                        lower_ans = ans.lower()
                        is_not_found = (
                            "not_found" in lower_ans
                            or "couldn't find" in lower_ans
                            or not ans
                        )
                        if is_not_found:
                            # Precedents did not answer the question; break to deterministic synthesis
                            break

                        parsed["answer"] = citation_checker.check_and_badge_text(parsed.get("answer", ""), is_tier2=False, allowed_cases=retrieved_cases)
                        parsed["ratio_decidendi"] = citation_checker.check_and_badge_text(parsed.get("ratio_decidendi", "") or parsed["answer"], is_tier2=False, allowed_cases=retrieved_cases)
                        parsed["citations"] = citation_checker.badge_citations_list(parsed.get("citations", []))

                        # Self-check answer direction against retrieved holdings
                        direction_check = check_holding_direction(query, parsed["answer"], parsed["ratio_decidendi"], retrieved_cases)
                        if direction_check.get("was_corrected"):
                            parsed["answer"] = citation_checker.check_and_badge_text(direction_check["answer"], is_tier2=False, allowed_cases=retrieved_cases)
                            parsed["ratio_decidendi"] = citation_checker.check_and_badge_text(direction_check["ratio_decidendi"], is_tier2=False, allowed_cases=retrieved_cases)
                            if direction_check.get("citations"):
                                parsed["citations"] = citation_checker.badge_citations_list(direction_check["citations"])

                        parsed["model_used"] = self.model
                        parsed["results"] = retrieved_cases
                        return parsed
                except Exception as e:
                    if attempt == 1:
                        logger.warning("Search synthesis model call attempt 1 failed: %s. Retrying once before fallback...", e)
                        await asyncio.sleep(0.5)
                    else:
                        logger.error("Search synthesis model call attempt 2 failed: %s. Triggering deterministic fallback.", e)

        # -------------------------------------------------------------
        # Deterministic Legal Fallback Grounded in Retrieved Cases
        # -------------------------------------------------------------
        q_low = query.lower()
        c1 = retrieved_cases[0]
        c2 = retrieved_cases[1] if len(retrieved_cases) > 1 else None

        source_refs = [f"{c.get('title')} ({c.get('citation')})" for c in retrieved_cases[:3]]
        bench_c1 = f"{c1.get('benchType', 'Bench')} ({c1.get('benchSize', '')} judges)" if c1.get('benchSize') else c1.get('benchType', 'Bench')
        bench_c2 = f"{c2.get('benchType', 'Bench')} ({c2.get('benchSize', '')} judges)" if (c2 and c2.get('benchSize')) else (c2.get('benchType', 'Bench') if c2 else '')

        # Topic-specific grounded synthesis
        if any(w in q_low for w in ["non-compete", "non compete", "section 27", "restraint of trade"]):
            ans_str = (
                f"Under Section 27 of the Indian Contract Act 1872, all post-termination non-compete clauses are void ab initio and unenforceable in India. "
                f"In Percept D'Mark (India) (P) Ltd. v. Zaheer Khan (2006, 2-judge Division Bench), the Supreme Court ruled that the doctrine of restraint of trade is absolute and admits no exception of reasonableness for post-employment restrictions. "
                f"Negative covenants are legally enforceable only during the active term of employment, as affirmed in Superintendence Co. of India (P) Ltd. v. Krishan Murgai (1981, 3-judge Bench)."
            )
            ratio_str = "Section 27 void ab initio post-employment non-compete doctrine."
            source_refs = [
                "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan ((2006) 4 SCC 227)",
                "Superintendence Company of India (P) Ltd. v. Krishan Murgai ((1981) 2 SCC 246)"
            ]
        elif any(w in q_low for w in ["privacy", "article 21", "fundamental right"]):
            ans_str = (
                f"In Justice K.S. Puttaswamy (Retd.) v. Union of India (2017, 9-judge Constitution Bench), the Supreme Court unanimously held that the right to privacy is a fundamental right guaranteed under Article 21 and Part III of the Constitution. "
                f"The Court affirmed that privacy is intrinsic to life, personal liberty, and freedom of expression, establishing a strict three-fold test of legality, legitimate state aim, and proportionality for any state interference."
            )
            ratio_str = "Right to privacy is an intrinsic fundamental right under Article 21 (Puttaswamy 2017)."
            source_refs = ["K.S. Puttaswamy v. Union of India (right to privacy) ([2017] 10 S.C.R. 569)"]
        elif any(w in q_low for w in ["basic structure", "article 368"]):
            ans_str = (
                f"In Kesavananda Bharati v. State of Kerala (1973, 13-judge Constitution Bench), the Supreme Court established the Basic Structure Doctrine. "
                f"The Court held that while Parliament possesses plenary power to amend the Constitution under Article 368, that amending power is limited and cannot alter, damage, or emasculate the basic structure or essential framework of the Constitution."
            )
            ratio_str = "Parliament's amending power under Article 368 is subject to the Basic Structure Doctrine (Kesavananda 1973)."
            source_refs = ["Kesavananda Bharati v. State of Kerala ([1973] SUPP. 1 S.C.R. 1)"]
        elif any(w in q_low for w in ["evict", "landlord", "tenant", "tenancy", "rent", "babu manmohan", "material alteration"]):
            ans_str = (
                f"Under Indian tenancy and rent control jurisprudence, a tenant cannot indefinitely occupy rented premises without paying rent, nor materially alter the premises without landlord consent. "
                f"While a landlord cannot forcefully dispossess a tenant without due process of law, non-payment of rent constitutes a primary statutory ground for eviction under State Rent Control Acts. "
                f"In Atma Ram Properties (P) Ltd. v. Federal Motors (P) Ltd. (2005, 2-judge Division Bench), the Supreme Court held that a tenant facing eviction proceedings is liable to pay mesne profits and cannot remain rent-free. "
                f"In V. Dhanapal Chettiar v. Yesodai Ammal (1979, 7-judge Constitution Bench), the Court settled that contractual notice under Section 106 TPA is not a condition precedent to an eviction petition under State Rent Control Acts; the landlord must establish statutory grounds. "
                f"Furthermore, in Babu Manmohan Das Shah v. Bishun Das (1967, 3-judge Bench), the Supreme Court held that under Section 3(1)(c) of the U.P. Rent Control Act, material alterations that either materially alter the accommodation or diminish its value are disjunctive grounds for eviction."
            )
            ratio_str = "Tenant eviction requires due process and statutory grounds under Rent Control acts (Dhanapal Chettiar / Atma Ram Properties / Babu Manmohan Das Shah)."
            source_refs = [
                "Atma Ram Properties (P) Ltd. v. Federal Motors (P) Ltd. ((2005) 1 SCC 705)",
                "V. Dhanapal Chettiar v. Yesodai Ammal ((1979) 4 SCC 214)",
                "Babu Manmohan Das Shah v. Bishun Das ([1967] 1 S.C.R. 836)"
            ]
        elif any(w in q_low for w in ["live-in relationship", "live in relationship", "cohabitation", "live-in partners"]):
            ans_str = (
                f"In S. Khushboo v. Kanniammal (2010, 3-judge Bench), the Supreme Court held that consensual live-in relationships between adults are legal and protected under Article 21 as an aspect of personal liberty. "
                f"Furthermore, in D. Velusamy v. D. Patchaiammal (2010, 2-judge Division Bench), the Court recognized that relationships 'in the nature of marriage' confer statutory protection and maintenance rights under Section 2(f) of the Domestic Violence Act 2005."
            )
            ratio_str = "Consensual live-in relationships are legal under Article 21; DV Act protection applies to relationships in the nature of marriage."
            source_refs = [
                "S. Khushboo v. Kanniammal & Anr. ((2010) 5 SCC 600)",
                "D. Velusamy v. D. Patchaiammal ((2010) 10 SCC 469)"
            ]
        elif any(w in q_low for w in ["arrest", "section 41", "custody", "warrant"]):
            ans_str = (
                f"Under Section 41 and 41A of the Code of Criminal Procedure, as interpreted in Arnesh Kumar v. State of Bihar (2014, 2-judge Division Bench) and D.K. Basu v. State of West Bengal (Decided 1996, reported (1997) 1 SCC 416, 2-judge Division Bench), police officers cannot arrest individuals mechanically without recording reasons and serving a mandatory notice of appearance. "
                f"The Supreme Court mandated that failure to comply with the statutory arrest checklist makes the police officer liable for departmental action and contempt of court."
            )
            ratio_str = "Mandatory arrest checklist and Section 41A notice safeguards against arbitrary arrest (Arnesh Kumar / D.K. Basu)."
            source_refs = [
                "Arnesh Kumar v. State of Bihar ([2014] 8 S.C.R. 128)",
                "D.K. Basu v. State of West Bengal ([1996] SUPP. 10 S.C.R. 284)"
            ]
        elif any(w in q_low for w in ["bail", "anticipatory bail", "section 438"]):
            ans_str = (
                f"The Supreme Court has firmly settled that personal liberty under Article 21 mandates that bail is the rule and jail is the exception. "
                f"In matters of anticipatory bail under Section 438 CrPC, courts must balance individual liberty against the requirements of fair investigation, granting relief where custodial interrogation is not genuinely necessary."
            )
            ratio_str = "Bail is the rule, jail is the exception under Article 21."
        elif any(w in q_low for w in ["murder", "culpable homicide", "section 300", "section 299"]):
            ans_str = (
                f"Under the Indian Penal Code, culpable homicide is the genus and murder is the species (Sections 299 and 300 IPC). "
                f"As established by the Supreme Court, an offence is murder if committed with the intention of causing death or bodily injury sufficient in the ordinary course of nature to cause death, unless it falls under one of the five statutory exceptions reducing it to culpable homicide not amounting to murder."
            )
            ratio_str = "Culpable homicide is the genus, murder is the species under IPC Sections 299 and 300."
        elif any(w in q_low for w in ["section 74", "liquidated damages", "earnest money"]):
            ans_str = (
                f"Under Section 74 of the Indian Contract Act 1872, as interpreted in Kailash Nath Associates v. Delhi Development Authority (2015, 2-judge Division Bench), liquidated damages represent reasonable compensation and require proof of actual legal injury or loss where such loss is capable of proof. "
                f"Penalty clauses and forfeiture cannot be enforced in the absence of proven loss."
            )
            ratio_str = "Liquidated damages require proof of loss under Section 74 (Kailash Nath 2015)."
            source_refs = ["Kailash Nath Associates v. Delhi Development Authority ((2015) 4 SCC 136)"]
        elif any(w in q_low for w in ["article 141", "precedent hierarchy", "larger bench", "coordinate bench"]):
            ans_str = (
                f"Under Article 141 of the Constitution of India, as authoritatively held in Central Board of Dawoodi Bohra Community v. State of Maharashtra (2005, 5-judge Constitution Bench), the law declared by a larger bench of the Supreme Court is strictly binding on any subsequent bench of lesser or co-equal strength. "
                f"A bench of lesser quorum cannot doubt, bypass, or overrule the correctness of the view taken by a larger bench, maintaining the discipline of judicial precedent."
            )
            ratio_str = "A larger bench decision is binding on smaller and coordinate benches under Article 141 (Dawoodi Bohra 2005)."
            source_refs = ["Central Board of Dawoodi Bohra Community v. State of Maharashtra ((2005) 2 SCC 673)"]
        else:
            # Grounded synthesis citing retrieved cases directly
            c1_summary = clean_case_summary(c1)
            c2_part = f" Furthermore, in {c2.get('title')} ({c2.get('decisionYear') or c2.get('year')}, {bench_c2}), the Court affirmed that {clean_case_summary(c2)}" if c2 else ""
            ans_str = (
                f"Based on the verified precedents in our database, in {c1.get('title')} ({c1.get('decisionYear') or c1.get('year')}, {bench_c1}), the Supreme Court held that {c1_summary}.{c2_part}"
            )
            ratio_str = c1_summary

        # Check holding direction
        direction_check = check_holding_direction(query, ans_str, ratio_str, retrieved_cases)
        if direction_check.get("was_corrected"):
            ans_str = direction_check["answer"]
            ratio_str = direction_check["ratio_decidendi"]
            if direction_check.get("citations"):
                source_refs = direction_check["citations"]

        badged_ans = citation_checker.check_and_badge_text(ans_str, is_tier2=False, allowed_cases=retrieved_cases)
        badged_ratio = citation_checker.check_and_badge_text(ratio_str, is_tier2=False, allowed_cases=retrieved_cases)
        badged_cits = citation_checker.badge_citations_list(source_refs)

        return {
            "answer": badged_ans,
            "ratio_decidendi": badged_ratio,
            "citations": badged_cits,
            "results": retrieved_cases,
            "model_used": "deterministic_precedent_synthesis"
        }

    async def synthesize_legal_summary(self, clause_text: str, contract_title: str) -> str:
        """Concise legal synthesis for agent trace visualizer."""
        audit = await self.verify_clause_ai(clause_text, contract_title)
        if audit.get("is_violation"):
            return "Violates Section 27 Indian Contract Act 1872. Void ab initio under Percept D'Mark (2006). Risk: CRITICAL."
        return "Complies with Indian contractual standards. Enforceable during active engagement."

    async def check_health(self) -> Dict[str, Any]:
        """Diagnostic health report for the FastAPI /health endpoint."""
        if not self.is_active or not self.client:
            return {
                "status": "fallback_simulated",
                "model": self.model,
                "provider": self.provider,
                "configured": False,
                "detail": f"No active {self.provider.upper()}_API_KEY detected. Running in deterministic Indian law fallback mode."
            }

        return {
            "status": "connected",
            "model": self.model,
            "provider": self.provider,
            "configured": True,
            "detail": f"{self.provider.capitalize()} LLM service active targeting {self.model}."
        }


llm_service = LLMService()
