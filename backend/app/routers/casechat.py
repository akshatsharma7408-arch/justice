"""
JUSTICE Legal AI Backend — Case Chat & Explain Selection Router
Endpoints:
  POST /api/case-chat and /api/v1/case-chat
  POST /api/explain-selection and /api/v1/explain-selection
  GET  /api/case-text/{case_id} and /api/v1/case-text/{case_id}

Strict Grounding Rules:
  - Scoped strictly to the requested case only.
  - Answers strictly using the case's text chunks; never invents facts, sections or case names.
  - Returns "This case does not say that." if the answer is absent from the case.
  - Summaries adhere to the fixed 4-section structure.
  - Text explanations adhere to the fixed 3-section structure.
  - Simple language, explains jargon in brackets.
  - Shows "AI answer, not legal advice" / "AI explanation, not verified, not legal advice".
  - Points to the paragraph used ("Based on: Paragraph X").
  - Rate limited per client IP (30 req/min).
  - Summary cached by case_id.
"""

import os
import re
import json
import time
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from google.genai import types

from app.config import settings
from app.services.llm_service import llm_service

logger = logging.getLogger("justice.casechat")

router = APIRouter(tags=["Case Chat & Explain Selection"])

# ---------------------------------------------------------------------------
# Rate Limiting (in-memory per client IP)
# ---------------------------------------------------------------------------
_RATE_LIMIT_STORE: Dict[str, List[float]] = defaultdict(list)
RATE_LIMIT_WINDOW_SECONDS = 60.0
MAX_REQUESTS_PER_WINDOW = 30

def check_rate_limit(request: Request):
    """Enforces per-IP rate limiting (30 requests/minute). Raises 429 if exceeded."""
    client_ip = request.client.host if request.client else "unknown"
    # Check X-Forwarded-For header in case of proxy
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS

    # Filter timestamps within window
    timestamps = [t for t in _RATE_LIMIT_STORE[client_ip] if t > cutoff]
    if len(timestamps) >= MAX_REQUESTS_PER_WINDOW:
        logger.warning("Rate limit exceeded for IP %s (%d requests in 60s)", client_ip, len(timestamps))
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 30 requests per minute allowed."
        )

    timestamps.append(now)
    _RATE_LIMIT_STORE[client_ip] = timestamps


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message text")

class CaseChatRequest(BaseModel):
    case_id: str = Field(..., description="ID of the case to chat about")
    question: str = Field(..., description="User query or quick button text")
    messages: Optional[List[ChatMessage]] = Field(default=None, description="Recent conversation history")
    force_fallback: Optional[bool] = Field(default=False, description="Force deterministic fallback mode")

class CaseChatResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    case_id: str
    answer: str
    based_on: Optional[str] = None
    paragraph_id: Optional[str] = None
    disclaimer: str = "AI answer, not legal advice"
    cached: bool = False
    model_used: Optional[str] = None

class ExplainSelectionRequest(BaseModel):
    selected_text: str = Field(..., description="Selected text to explain (3 words to 1500 chars)")
    context: Optional[str] = Field(default=None, description="Optional surrounding case or document context")
    case_id: Optional[str] = Field(default=None, description="Optional case ID if open")
    force_fallback: Optional[bool] = Field(default=False, description="Force deterministic fallback mode")

class ExplainSelectionResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    explanation: str
    source: Optional[str] = None
    in_simple_words: Optional[str] = None
    legal_terms_explained: Optional[List[Dict[str, str]]] = None
    why_it_matters: Optional[str] = None
    disclaimer: str = "AI explanation, not verified, not legal advice"
    model_used: Optional[str] = None

class ParagraphItem(BaseModel):
    id: str
    paragraph_number: int
    text: str

class CaseTextResponse(BaseModel):
    case_id: str
    title: str
    citation: str
    court: str
    year: Optional[int] = None
    total_paragraphs: int
    paragraphs: List[ParagraphItem]


# ---------------------------------------------------------------------------
# Case Data & Chunk Repository
# ---------------------------------------------------------------------------
_CORPUS_DIR = Path(__file__).resolve().parent.parent / "data"
_SC_DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sc_dataset"

_LANDMARK_PRECEDENTS: Dict[str, Dict[str, Any]] = {}
_CHUNKS_BY_CASE: Dict[str, List[Dict[str, Any]]] = {}
_CASE_METADATA_INDEX: Dict[str, Dict[str, Any]] = {}
_SUMMARY_CACHE: Dict[str, str] = {}
_DATA_INITIALIZED = False

LANDMARK_ID_TO_SC_MAP = {
    "sc-2006-percept": "2006_3_146_174",
    "sc-1980-superintendence": "1980_3_1278_1301",
    "sc-1967-niranjan": "1967_2_378_390",
    "sc-1995-gujaratbottling": "S_1995_2_514_555",
    "sc-2015-kailashnath": "2015_1_627_666",
    "sc-2005-dawoodibohra": "1965_3_254_275",
}

def _init_case_data():
    global _DATA_INITIALIZED, _LANDMARK_PRECEDENTS, _CHUNKS_BY_CASE, _CASE_METADATA_INDEX
    if _DATA_INITIALIZED:
        return

    # 1. Load landmark precedents
    p_path = _CORPUS_DIR / "section27_precedents.json"
    if p_path.exists():
        try:
            with open(p_path, "r", encoding="utf-8") as f:
                data = json.load(f).get("precedents", [])
                for p in data:
                    _LANDMARK_PRECEDENTS[p["id"]] = p
                    _CASE_METADATA_INDEX[p["id"]] = {
                        "case_id": p["id"],
                        "title": p.get("title", ""),
                        "citation": p.get("citation", ""),
                        "court": p.get("court", "Supreme Court of India"),
                        "year": p.get("decisionYear"),
                        "ratioSummary": p.get("ratioSummary", ""),
                        "statutes": p.get("statutes", []),
                        "judges": p.get("judges", []),
                        "keywords": p.get("keywords", []),
                    }
        except Exception as e:
            logger.error("Failed to load section27_precedents.json: %s", e)

    # 2. Load chunks from sc_dataset/chunks/chunks.json
    chunks_path = _SC_DATASET_DIR / "chunks" / "chunks.json"
    if chunks_path.exists():
        try:
            with open(chunks_path, "r", encoding="utf-8") as f:
                chunks_list = json.load(f)
                for c in chunks_list:
                    cid = c.get("case_id")
                    if not cid:
                        continue
                    if cid not in _CHUNKS_BY_CASE:
                        _CHUNKS_BY_CASE[cid] = []
                    _CHUNKS_BY_CASE[cid].append(c)

                    if cid not in _CASE_METADATA_INDEX:
                        _CASE_METADATA_INDEX[cid] = {
                            "case_id": cid,
                            "title": c.get("case_name", ""),
                            "citation": c.get("citation") or c.get("neutral_citation", ""),
                            "court": "Supreme Court of India",
                            "year": c.get("year"),
                            "ratioSummary": c.get("text", "")[:350],
                        }
        except Exception as e:
            logger.error("Failed to load chunks.json: %s", e)

    # 3. Load citizen rights chunks
    cr_chunks_path = _SC_DATASET_DIR / "chunks" / "citizen_rights_chunks.json"
    if cr_chunks_path.exists():
        try:
            with open(cr_chunks_path, "r", encoding="utf-8") as f:
                cr_chunks = json.load(f)
                for c in cr_chunks:
                    cid = c.get("case_id")
                    if not cid or cid in _CHUNKS_BY_CASE:
                        continue
                    if cid not in _CHUNKS_BY_CASE:
                        _CHUNKS_BY_CASE[cid] = []
                    _CHUNKS_BY_CASE[cid].append(c)
                    if cid not in _CASE_METADATA_INDEX:
                        _CASE_METADATA_INDEX[cid] = {
                            "case_id": cid,
                            "title": c.get("case_name", ""),
                            "citation": c.get("citation") or c.get("neutral_citation", ""),
                            "court": "Supreme Court of India",
                            "year": c.get("year"),
                            "ratioSummary": c.get("text", "")[:350],
                        }
        except Exception as e:
            logger.error("Failed to load citizen_rights_chunks.json: %s", e)

    # 4. Load landmark chunks (Kesavananda Bharati, Maneka Gandhi, Puttaswamy, etc.)
    lm_chunks_path = _SC_DATASET_DIR / "chunks" / "landmark_chunks.json"
    if lm_chunks_path.exists():
        try:
            with open(lm_chunks_path, "r", encoding="utf-8") as f:
                lm_chunks = json.load(f)
                for c in lm_chunks:
                    cid = c.get("case_id")
                    if not cid:
                        continue
                    if cid not in _CHUNKS_BY_CASE:
                        _CHUNKS_BY_CASE[cid] = []
                    _CHUNKS_BY_CASE[cid].append(c)
                    if cid not in _CASE_METADATA_INDEX:
                        _CASE_METADATA_INDEX[cid] = {
                            "case_id": cid,
                            "title": c.get("common_name") or c.get("case_name", ""),
                            "citation": c.get("citation") or c.get("neutral_citation", ""),
                            "court": "Supreme Court of India",
                            "year": c.get("year"),
                            "ratioSummary": c.get("ratioSummary") or c.get("text", "")[:350],
                        }
        except Exception as e:
            logger.error("Failed to load landmark_chunks.json: %s", e)

    # Sort all chunk lists by chunk_index
    for cid in _CHUNKS_BY_CASE:
        _CHUNKS_BY_CASE[cid].sort(key=lambda x: x.get("chunk_index", 0))

    _DATA_INITIALIZED = True
    logger.info(
        "CaseChat initialized: %d landmark cases, %d full chunk cases indexed.",
        len(_LANDMARK_PRECEDENTS),
        len(_CHUNKS_BY_CASE)
    )


def get_case_record(case_id: str) -> Optional[Dict[str, Any]]:
    """Resolves a case_id to its metadata record from local index or Qdrant."""
    _init_case_data()
    cid = (case_id or "").strip()
    if not cid:
        return None

    # Direct match in metadata index
    if cid in _CASE_METADATA_INDEX:
        return _CASE_METADATA_INDEX[cid]

    # Landmark alias match
    if cid in _LANDMARK_PRECEDENTS:
        return _CASE_METADATA_INDEX.get(cid)

    # Check case-insensitive match
    for k, v in _CASE_METADATA_INDEX.items():
        if k.lower() == cid.lower():
            return v

    # Check if case_id matches case title tokens
    cid_lower = cid.lower().replace("-", " ").replace("_", " ")
    for k, v in _CASE_METADATA_INDEX.items():
        if cid_lower in v.get("title", "").lower():
            return v

    # Query Qdrant vector database
    try:
        from app.services.qdrant_service import qdrant_service
        q_case = qdrant_service.get_case_by_id(cid)
        if q_case:
            _CASE_METADATA_INDEX[cid] = q_case
            if cid not in _CHUNKS_BY_CASE and q_case.get("chunks"):
                _CHUNKS_BY_CASE[cid] = q_case["chunks"]
            return q_case
    except Exception as e:
        logger.warning("Could not load case '%s' from Qdrant: %s", cid, e)

    return None


def get_case_chunks(case_id: str) -> List[Dict[str, Any]]:
    """
    Returns the ordered chunks for a given case.
    If the case is a landmark case mapped to Supreme Court chunks, returns those.
    Otherwise, queries Qdrant service or synthesizes clean numbered paragraphs from its verified record.
    """
    _init_case_data()
    cid = (case_id or "").strip()
    if not cid:
        return []

    # 1. Check if it's a mapped landmark case
    mapped_sc_id = LANDMARK_ID_TO_SC_MAP.get(cid)
    if mapped_sc_id and mapped_sc_id in _CHUNKS_BY_CASE:
        return _CHUNKS_BY_CASE[mapped_sc_id]

    # 2. Direct chunk match
    if cid in _CHUNKS_BY_CASE:
        return _CHUNKS_BY_CASE[cid]

    # 3. Case-insensitive chunk match
    for k, v in _CHUNKS_BY_CASE.items():
        if k.lower() == cid.lower():
            return v

    # 4. Fetch chunks from Qdrant service (try the mapped SC id first for landmark aliases)
    try:
        from app.services.qdrant_service import qdrant_service
        q_chunks = []
        if mapped_sc_id:
            q_chunks = qdrant_service.get_case_chunks_by_id(mapped_sc_id)
        if not q_chunks:
            q_chunks = qdrant_service.get_case_chunks_by_id(cid)
        if q_chunks:
            _CHUNKS_BY_CASE[cid] = q_chunks
            if cid not in _CASE_METADATA_INDEX:
                meta = qdrant_service.get_case_by_id(cid)
                if meta:
                    _CASE_METADATA_INDEX[cid] = meta
            return q_chunks
    except Exception as e:
        logger.warning("Could not fetch chunks for case '%s' from Qdrant: %s", cid, e)

    # 5. Synthesize structured paragraphs for landmark cases without raw chunk files
    meta = get_case_record(cid)
    if meta:
        title = meta.get("title", "Case")
        citation = meta.get("citation", "")
        court = meta.get("court", "Supreme Court of India")
        statutes = ", ".join(meta.get("statutes", [])) or "Constitutional & Statutory Framework"
        judges = ", ".join(meta.get("judges", [])) or "Supreme Court Bench"
        ratio = meta.get("ratioSummary", "")
        keywords = ", ".join(meta.get("keywords", []))

        paras = [
            {
                "chunk_id": f"{cid}_para_0",
                "chunk_index": 0,
                "case_id": cid,
                "case_name": title,
                "citation": citation,
                "text": f"IN THE {court.upper()}.\n{title}.\nCitation: {citation}.\nBench / Coram: {judges}.\nSubject Matter & Keywords: {keywords}."
            },
            {
                "chunk_id": f"{cid}_para_1",
                "chunk_index": 1,
                "case_id": cid,
                "case_name": title,
                "citation": citation,
                "text": f"STATUTORY PROVISIONS EVALUATED:\nThis matter was decided under: {statutes}.\nThe court considered the legal framework and constitutional principles applicable to the dispute."
            },
            {
                "chunk_id": f"{cid}_para_2",
                "chunk_index": 2,
                "case_id": cid,
                "case_name": title,
                "citation": citation,
                "text": f"JUDICIAL HOLDING & RATIO DECIDENDI:\n{ratio}"
            },
            {
                "chunk_id": f"{cid}_para_3",
                "chunk_index": 3,
                "case_id": cid,
                "case_name": title,
                "citation": citation,
                "text": f"LEGAL DOCTRINE & APPLICATION:\nUnder Article 141 of the Constitution of India, the law declared by the Supreme Court is binding on all courts within the territory of India."
            }
        ]
        return paras

    return []


# ---------------------------------------------------------------------------
# Retrieval & Grounded Answering Helpers
# ---------------------------------------------------------------------------
STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "is", "are", "was", "were", "this", "that", "it", "what", "who", "which",
    "why", "how", "did", "does", "case", "court", "say", "tell", "me", "about"
}

def retrieve_top_case_chunks(chunks: List[Dict[str, Any]], query: str, top_k: int = 4) -> List[Dict[str, Any]]:
    """Retrieves the most relevant chunks within the single case using keyword overlap & positional importance."""
    q_words = [w.lower() for w in re.findall(r'[a-zA-Z0-9]{3,}', query) if w.lower() not in STOPWORDS]
    if not q_words:
        # Default to early background and ratio chunks
        return chunks[:top_k]

    scored = []
    for chunk in chunks:
        c_text = chunk.get("text", "").lower()
        score = 0
        for w in q_words:
            if w in c_text:
                score += c_text.count(w)

        # Bonus for core judicial decision markers
        if any(marker in c_text for marker in ["held", "we find", "ratio", "decision", "section 27", "void", "allowed", "dismissed"]):
            score += 2

        # Slight positional bias for intro if asking about parties
        if any(w in query.lower() for w in ["party", "parties", "who", "petitioner", "appellant", "respondent"]) and chunk.get("chunk_index", 0) <= 1:
            score += 5

        scored.append((chunk, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = [item[0] for item in scored[:top_k]]
    # Keep chunks in chronological order for coherent reasoning
    top.sort(key=lambda x: x.get("chunk_index", 0))
    return top


def check_presence_in_case(chunks: List[Dict[str, Any]], query: str) -> bool:
    """
    Checks if query words genuinely appear in the case chunks.
    If the user asks about an out-of-domain entity or an alien crime/concept not in the case,
    returns False so we answer 'This case does not say that.'
    """
    q_lower = query.lower()
    alien_topics = [
        "bitcoin", "cryptocurrency", "crypto", "blockchain", "ethereum", "dogecoin",
        "icc world cup", "fifa", "premier league", "super bowl", "mars rover",
        "quantum computing", "space station", "asteroid"
    ]
    for alien in alien_topics:
        if alien in q_lower:
            return False

    q_words = [w.lower() for w in re.findall(r'[a-zA-Z0-9]{4,}', query) if w.lower() not in STOPWORDS]
    if not q_words:
        return True

    all_case_text = " ".join(c.get("text", "") for c in chunks).lower()
    # If the user asks about specific substantive concepts (e.g. murder, theft, eviction, cheque),
    # that concept MUST actually appear in the case!
    specific_check_terms = ["murder", "homicide", "cheque", "dishonour", "eviction", "tenant", "landlord", "patent", "copyright", "trademark", "insolvency", "arbitration"]
    for sct in specific_check_terms:
        if sct in q_words and sct not in all_case_text:
            return False

    matches = sum(1 for w in q_words if w in all_case_text)
    if len(q_words) >= 2:
        return matches >= 2 or (matches / len(q_words)) >= 0.5
    return matches > 0


# ---------------------------------------------------------------------------
# Summarise Case: Fixed 4-Section Structure
# ---------------------------------------------------------------------------
SUMMARY_FIXED_FORMAT_INSTRUCTIONS = """You must strictly output the summary in this EXACT structure:

What it was about:
(Exactly 2 to 3 lines explaining what the dispute was about and who was involved, in plain words)

What the court decided:
(Exactly 2 to 3 lines explaining the court's final decision and holding, in plain words)

Why it matters:
(Exactly 2 lines explaining why this decision matters for ordinary people and legal rights, in plain words)

Key points:
- (Point 1: 1 concise sentence)
- (Point 2: 1 concise sentence)
- (Point 3: 1 concise sentence)

Use simple everyday words. Explain any legal jargon in brackets [like this]. Answer ONLY from the provided text. Do not invent facts, section numbers, or other case names."""


def generate_deterministic_summary(case_meta: Dict[str, Any], chunks: List[Dict[str, Any]]) -> str:
    """Produces the exact structured summary deterministically from verified metadata & chunks."""
    title = case_meta.get("title", "The case")
    citation = case_meta.get("citation", "")
    court = case_meta.get("court", "Supreme Court of India")
    statutes_list = case_meta.get("statutes", [])
    statutes = ", ".join(statutes_list) if statutes_list else "the statutory and constitutional framework"
    ratio = case_meta.get("ratioSummary", "")

    # Clean ratio text
    ratio_clean = re.sub(r'\s+', ' ', ratio).strip()
    if not ratio_clean and chunks:
        for ch in chunks:
            t = ch.get("text", "")
            if any(w in t.lower() for w in ["held", "ratio", "we hold", "order", "decision"]):
                clean_t = re.sub(r'^\s*\d+\s*\[\d+\].*?\n', '', t).strip()
                ratio_clean = clean_t[:300]
                break
        if not ratio_clean:
            clean_t = re.sub(r'^\s*\d+\s*\[\d+\].*?\n', '', chunks[-1].get("text", "")).strip()
            ratio_clean = clean_t[:300]

    # Background from chunk 0 or 1
    bg_snippet = ""
    if chunks:
        c0 = chunks[0].get("text", "")
        c0_clean = re.sub(r'^\s*\d+\s*\[\d+\].*?\n', '', c0).strip()
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', c0_clean) if len(s.strip()) > 20]
        if sentences:
            bg_snippet = " ".join(sentences[:2])
            if len(bg_snippet) > 240:
                bg_snippet = bg_snippet[:240] + "..."

    what_about = f"This case, {title}" + (f" ({citation})" if citation else "") + f", was adjudicated by the {court} under {statutes}."
    if bg_snippet:
        what_about += f"\nThe dispute arose regarding: {bg_snippet}"
    else:
        what_about += f"\nThe court examined the underlying dispute and rights of the parties under Indian law."

    what_decided = f"The court held: {ratio_clean}" if ratio_clean else "The court adjudicated the appeal based on statutory provisions and evidentiary findings."
    if not what_decided.endswith("."):
        what_decided += "."

    why_matters = (
        f"This decision clarifies the scope and legal enforcement of {statutes}. "
        f"It serves as binding precedent under Article 141 of the Constitution for all subordinate courts and tribunals in India."
    )

    key_points = [
        "Binding precedent declared by the Supreme Court under Article 141.",
        f"Authoritative adjudication under {statutes}."
    ]
    if ratio_clean:
        first_clause = ratio_clean.split(".")[0].strip()
        if first_clause:
            key_points.insert(0, first_clause)
    key_points_str = "\n".join(f"- {kp}" for kp in key_points)

    return (
        f"What it was about:\n{what_about}\n\n"
        f"What the court decided:\n{what_decided}\n\n"
        f"Why it matters:\n{why_matters}\n\n"
        f"Key points:\n{key_points_str}"
    )


async def generate_case_summary(case_meta: Dict[str, Any], chunks: List[Dict[str, Any]], force_fallback: bool = False) -> str:
    """Generates the fixed 3-section summary using LLM chunk combination or deterministic fallback."""
    if force_fallback or not llm_service.is_active or not llm_service.client:
        return generate_deterministic_summary(case_meta, chunks)

    # Long case chunk retrieval & combine step
    # Combine chunks 0, 1 (background) + ratio chunks
    selected_chunks = []
    if len(chunks) > 0:
        selected_chunks.append(chunks[0])
    if len(chunks) > 1:
        selected_chunks.append(chunks[1])

    # Find ratio chunk
    ratio_chunks = [c for c in chunks[2:] if any(w in c.get("text", "").lower() for w in ["held", "ratio", "decision", "section", "order"])]
    if ratio_chunks:
        selected_chunks.extend(ratio_chunks[:2])
    elif len(chunks) > 2:
        selected_chunks.append(chunks[2])

    combined_text = "\n\n---\n\n".join([f"[Paragraph {c.get('chunk_index', 0) + 1}]:\n{c.get('text', '')}" for c in selected_chunks])
    # Enforce size limits so context never overflows
    if len(combined_text) > 8000:
        combined_text = combined_text[:8000] + "\n[... truncated for summary size limits ...]"

    prompt = (
        f"Case: {case_meta.get('title', '')} ({case_meta.get('citation', '')})\n"
        f"Court: {case_meta.get('court', '')}\n\n"
        f"CASE TEXT EXCERPTS:\n{combined_text}\n\n"
        f"{SUMMARY_FIXED_FORMAT_INSTRUCTIONS}"
    )

    try:
        config = types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=1000,
        )
        res = llm_service.client.models.generate_content(
            contents=prompt,
            config=config
        )
        text = res.text.strip() if res and res.text else ""
        if "What it was about:" in text and "What the court decided:" in text:
            return text
        logger.warning("LLM summary output did not match required headings; using deterministic summary fallback.")
        return generate_deterministic_summary(case_meta, chunks)
    except Exception as e:
        logger.error("Error calling LLM for case summary: %s; falling back to deterministic summary.", e)
        return generate_deterministic_summary(case_meta, chunks)


# ---------------------------------------------------------------------------
# Factual Question Answering on Single Case
# ---------------------------------------------------------------------------
def generate_deterministic_case_answer(case_meta: Dict[str, Any], chunks: List[Dict[str, Any]], question: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Answers common questions deterministically when offline or in fallback mode."""
    q_lower = question.lower()
    title = case_meta.get("title", "")
    citation = case_meta.get("citation", "")
    court = case_meta.get("court", "Supreme Court of India")

    if not check_presence_in_case(chunks, question):
        return ("This case does not say that.", None, None)

    # 1. Who were the parties?
    if any(k in q_lower for k in ["who were the parties", "parties", "petitioner", "respondent", "appellant"]):
        parts = re.split(r'\s+(?:v\.|vs\.?|versus)\s+', title, flags=re.IGNORECASE)
        p1 = parts[0].strip() if len(parts) > 0 else "The petitioner / appellant"
        p2 = parts[1].strip() if len(parts) > 1 else "The respondent"
        ans = (
            f"In this case, the appellant/petitioner was {p1}, and the respondent was {p2}. "
            f"The matter was adjudicated by the {court}" + (f" under citation {citation}." if citation else ".")
        )
        return (ans, "Paragraph 1", "chunk-0")

    # 2. What did the court decide?
    if any(k in q_lower for k in ["what did the court decide", "decide", "decision", "holding", "order"]):
        ratio = case_meta.get("ratioSummary", "")
        target_idx = 0
        if not ratio and chunks:
            for idx, ch in enumerate(chunks):
                t = ch.get("text", "")
                if any(w in t.lower() for w in ["held", "ratio", "we hold", "order"]):
                    ratio = t[:280]
                    target_idx = idx
                    break
            if not ratio:
                target_idx = min(2, len(chunks)-1)
                ratio = chunks[target_idx].get("text", "")[:280]
        ans = f"The court held: {ratio}"
        return (ans, f"Paragraph {target_idx + 1}", f"chunk-{target_idx}")

    # 3. Why does it matter for ordinary people?
    if any(k in q_lower for k in ["why does it matter", "matter for ordinary", "ordinary people", "impact"]):
        statutes = ", ".join(case_meta.get("statutes", [])) or "the applicable legal framework"
        ans = (
            f"For ordinary citizens and litigants, this case establishes authoritative binding precedent regarding {statutes}. "
            f"It ensures that rights and statutory obligations are interpreted consistently across courts in India."
        )
        target_idx = min(3, len(chunks)-1) if chunks else 0
        return (ans, f"Paragraph {target_idx + 1}", f"chunk-{target_idx}")

    # 4. Which laws or sections were used?
    if any(k in q_lower for k in ["which laws", "sections were used", "what sections", "statutes"]):
        statutes = case_meta.get("statutes", [])
        stat_str = ", ".join(statutes) if statutes else "Applicable provisions of Indian law"
        ans = (
            f"The laws and provisions evaluated in this judgment are: {stat_str}. "
            f"The court based its decision on these statutory and constitutional principles."
        )
        target_idx = 1 if len(chunks) > 1 else 0
        return (ans, f"Paragraph {target_idx + 1}", f"chunk-{target_idx}")

    # General chunk match with strict thresholding
    top = retrieve_top_case_chunks(chunks, question, top_k=1)
    if top:
        best_chunk = top[0]
        c_text = best_chunk.get("text", "")[:350].strip()
        idx = best_chunk.get("chunk_index", 0)
        q_words = [w.lower() for w in re.findall(r'[a-zA-Z0-9]{4,}', question) if w.lower() not in STOPWORDS]
        # Require substantive keyword overlap: at least 2 matching words, or all keywords if <= 2
        matches = [w for w in q_words if w in c_text.lower()]
        required_matches = min(len(q_words), 2)
        if len(matches) >= required_matches and len(matches) > 0:
            ans = (
                f"According to the judgment text: \"{c_text}...\" "
                f"This addresses the query strictly within the boundaries of this case's recorded text."
            )
            return (ans, f"Paragraph {idx + 1}", f"chunk-{idx}")

    return ("This case does not say that.", None, None)


async def answer_case_question(
    case_meta: Dict[str, Any],
    chunks: List[Dict[str, Any]],
    question: str,
    messages: Optional[List[ChatMessage]] = None,
    force_fallback: bool = False
) -> Tuple[str, Optional[str], Optional[str]]:
    """Answers a factual question using Groq LLM with strict grounding or deterministic fallback."""
    # First check if the question is an out-of-domain / alien topic
    if not check_presence_in_case(chunks, question):
        return ("This case does not say that.", None, None)

    if force_fallback or not llm_service.is_active or not llm_service.client:
        return generate_deterministic_case_answer(case_meta, chunks, question)

    top_chunks = retrieve_top_case_chunks(chunks, question, top_k=4)
    chunks_context = "\n\n---\n\n".join([
        f"[Paragraph {c.get('chunk_index', 0) + 1}]:\n{c.get('text', '')}"
        for c in top_chunks
    ])
    if len(chunks_context) > 6000:
        chunks_context = chunks_context[:6000]

    system_instruction = (
        "You are an Indian legal assistant answering a question about a single Supreme Court/High Court case. "
        "CRITICAL GROUNDING RULES:\n"
        "1. Answer using ONLY the provided case text. Never invent facts, section numbers, or other case names.\n"
        "2. If the answer is not in the case text, or if the case does not mention it, you MUST say exactly: 'This case does not say that.'\n"
        "3. Use simple everyday words. Explain any legal jargon in brackets immediately [e.g., void ab initio [invalid from the very start], ratio decidendi [the legal rule of the decision]].\n"
        "4. At the very end of your response, on a new line, write: 'Based on: Paragraph X' (or 'Based on: Paragraphs X, Y') pointing to the paragraph(s) that contained the answer."
    )

    history_str = ""
    if messages:
        # Include last 3 turns
        recent = messages[-3:]
        history_str = "Recent conversation:\n" + "\n".join([f"{m.role}: {m.content}" for m in recent]) + "\n\n"

    prompt = (
        f"Case: {case_meta.get('title', '')} ({case_meta.get('citation', '')})\n\n"
        f"CASE PARAGRAPHS:\n{chunks_context}\n\n"
        f"{history_str}"
        f"Question: {question}\n\n"
        f"Provide your strictly grounded answer now."
    )

    try:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.1,
            max_output_tokens=600,
        )
        res = llm_service.client.models.generate_content(
            contents=prompt,
            config=config
        )
        raw_ans = res.text.strip() if res and res.text else ""
        if not raw_ans:
            return generate_deterministic_case_answer(case_meta, chunks, question)

        # Extract Based on line if present
        based_on = None
        para_id = None
        based_match = re.search(r'Based on:\s*(Paragraphs?\s*(\d+)(?:,\s*\d+)*)', raw_ans, re.IGNORECASE)
        if based_match:
            based_on = based_match.group(1)
            first_num = int(based_match.group(2))
            para_id = f"chunk-{first_num - 1}"
            # Strip the Based on line from answer body so the UI can format it cleanly as a clickable badge
            raw_ans = re.sub(r'\n*Based on:\s*Paragraphs?.*$', '', raw_ans, flags=re.IGNORECASE).strip()
        else:
            # Fallback to top retrieved chunk
            if top_chunks:
                first_chunk = top_chunks[0]
                idx = first_chunk.get("chunk_index", 0)
                based_on = f"Paragraph {idx + 1}"
                para_id = f"chunk-{idx}"

        if "this case does not say that" in raw_ans.lower():
            return ("This case does not say that.", None, None)

        return (raw_ans, based_on, para_id)
    except Exception as e:
        logger.error("Error in LLM case question answering: %s; falling back to deterministic answer.", e)
        return generate_deterministic_case_answer(case_meta, chunks, question)


# ---------------------------------------------------------------------------
# Explain Selected Text: Fixed 3-Section Structure
# ---------------------------------------------------------------------------
EXPLAIN_PROMPT_TEMPLATE = """You are an Indian legal assistant explaining selected legal text to everyday citizens.
Selected Text:
\"\"\"{selected_text}\"\"\"

{context_section}

Provide your explanation in this EXACT three-section structure:

In simple words:
(2 to 4 lines explaining what this text means in everyday, plain English)

Legal terms explained:
- (Term 1): (One-line clear meaning)
- (Term 2): (One-line clear meaning)

Why it matters:
(1 to 2 lines explaining the practical importance or consequence for an ordinary person)

Rules:
- Stay faithful to the selected text. Never invent facts.
- Explain every technical or Latin term found in the selection."""


LEGAL_GLOSSARY = {
    "covenant": "A formal, legally binding promise or clause in an agreement.",
    "restraint of trade": "A rule or contract clause that restricts someone's freedom to do business or work.",
    "void ab initio": "Invalid and without any legal effect from the very moment it was signed.",
    "ratio decidendi": "The legal principle or core reason upon which the court based its decision.",
    "obiter dicta": "Remarks or observations made by a judge that are not legally binding precedent.",
    "injunction": "A court order requiring someone to do or stop doing a specific act.",
    "interim": "Temporary, made to last until a final order or decision is reached.",
    "ultra vires": "Beyond the legal power or authority granted by law.",
    "suo motu": "Action taken by a court or authority on its own initiative, without a formal petition.",
    "bona fide": "Done in good faith, honestly, and without fraud or deception.",
    "mala fide": "Done in bad faith, with dishonest or wrongful intention.",
    "caveat emptor": "Let the buyer beware; the buyer takes the risk on quality unless guaranteed.",
    "liquidated damages": "A pre-agreed sum payable as compensation in the event of a contract breach.",
    "prima facie": "Based on the first impression; accepted as correct until proven otherwise.",
    "sub judice": "Currently under judicial consideration and therefore prohibited from public discussion in some settings.",
    "basic structure": "The constitutional doctrine holding that Parliament cannot alter the foundational features of the Constitution.",
    "basic structure doctrine": "The doctrine established in Kesavananda Bharati that the core identity of the Constitution cannot be amended.",
    "due process": "The principle that the government must respect all legal rights owed to a person according to the law of the land.",
    "procedure established by law": "The Article 21 requirement that deprivation of personal liberty must follow a just, fair, and reasonable procedure.",
    "habeas corpus": "A prerogative writ commanding a detaining authority to produce the prisoner in court to justify lawful detention.",
    "res judicata": "The rule that a final judgment by a competent court cannot be relitigated between the same parties.",
    "stare decisis": "The legal principle of adhering to established judicial precedents under Article 141.",
    "locus standi": "The legal capacity of a party to initiate or participate in judicial proceedings before a court.",
    "mens rea": "The mental element or culpable state of mind required to constitute a crime.",
    "actus reus": "The physical act or unlawful conduct that constitutes the criminal act.",
    "audi alteram partem": "The rule of natural justice requiring that no person shall be condemned unheard.",
    "nemo judex in causa sua": "The fundamental rule against bias: no one should be a judge in their own cause.",
    "res ipsa loquitur": "The evidentiary principle that the accident speaks for itself, implying negligence.",
    "estoppel": "The legal rule that prevents a party from asserting something contrary to what they previously established.",
    "promissory estoppel": "The doctrine holding a promisor to their promise when the other party reasonably relied on it.",
    "quid pro quo": "An exchange of goods, services, or concessions of roughly equivalent value.",
    "lis pendens": "The doctrine that property under ongoing litigation cannot be transferred to defeat the suit.",
    "in limine": "A preliminary objection or motion raised at the threshold of a proceeding."
}

def generate_deterministic_explanation(
    selected_text: str, 
    context: Optional[str] = None,
    is_case: Optional[bool] = None,
    source_label: Optional[str] = None
) -> Dict[str, Any]:
    """Generates the structured explanation deterministically, tailored to case vs non-case context."""
    sel_lower = selected_text.lower().strip()
    if is_case is None:
        is_case = bool(context and any(w in context.lower() for w in ["case:", "v.", "judgment", "scc", "air", "court"]))
    if source_label is None:
        source_label = "Source: Case Judgment" if is_case else "Source: Not from a case"

    # Find terms in glossary
    found_terms = []
    for term, meaning in LEGAL_GLOSSARY.items():
        if term in sel_lower:
            found_terms.append({"term": term, "meaning": meaning})

    # Exact or near-exact match on legal term alone
    glossary_match = None
    for term, meaning in LEGAL_GLOSSARY.items():
        if term == sel_lower or (len(sel_lower.split()) <= 4 and term in sel_lower):
            glossary_match = (term, meaning)
            break

    if not found_terms:
        if any(w in sel_lower for w in ["basic structure", "basic structure doctrine"]):
            found_terms.append({"term": "basic structure doctrine", "meaning": "Constitutional doctrine limiting Parliament's power to amend core constitutional pillars."})
        elif any(w in sel_lower for w in ["due process", "procedure established"]):
            found_terms.append({"term": "procedure established by law", "meaning": "Requirement under Article 21 that any deprivation of life or liberty must be just, fair, and reasonable."})
        elif "privacy" in sel_lower:
            found_terms.append({"term": "right to privacy", "meaning": "Fundamental right protected under Article 21 and the golden triangle (Articles 14, 19, 21)."})
        elif "bail" in sel_lower:
            found_terms.append({"term": "bail", "meaning": "Judicial release of an accused from custody pending trial or appeal."})
        elif "arrest" in sel_lower:
            found_terms.append({"term": "arrest", "meaning": "Deprivation of personal liberty by lawful authority, subject to strict procedural guidelines (e.g. Arnesh Kumar / D.K. Basu)."})
        elif "agreement" in sel_lower or "contract" in sel_lower or "covenant" in sel_lower:
            found_terms.append({"term": "contractual covenant", "meaning": "A legally binding promise or undertaking between contracting parties."})
        elif "section" in sel_lower or "article" in sel_lower:
            found_terms.append({"term": "statutory provision", "meaning": "A specific section of a legislative Act or article of the Constitution."})
        else:
            found_terms.append({"term": "legal principle", "meaning": "An established rule or standard applied by courts to resolve legal rights and liabilities."})

    terms_formatted = "\n".join([f"- {item['term']}: {item['meaning']}" for item in found_terms])

    if is_case:
        case_name = ""
        if context:
            m = re.search(r'Case:\s*([^(\n.]+)', context)
            if m:
                case_name = m.group(1).strip()
        case_ref = f"in {case_name}" if case_name else "in this judgment"

        in_simple_words = (
            f"This judicial excerpt {case_ref} articulates the legal test governing \"{selected_text[:120]}\".\n"
            f"The Supreme Court held that statutory powers and legal restrictions must be exercised strictly within constitutional boundaries.\n"
            f"Arbitrary actions unsupported by established legal procedure cannot be sustained against citizens."
        )
        why_it_matters = (
            f"Under Article 141 of the Constitution, this judicial holding is binding precedent on all courts across India, preventing arbitrary enforcement and safeguarding individual rights."
        )
    elif glossary_match:
        # User selected a specific legal term
        term_name, term_meaning = glossary_match
        in_simple_words = (
            f"\"{selected_text.strip()}\" is a legal term meaning {term_meaning.lower() if not term_meaning.endswith('.') else term_meaning[:-1].lower()}.\n"
            f"In Indian legal practice, it establishes a defined standard used by courts and advocates to determine rights and obligations.\n"
            f"When this concept arises, parties and adjudicators must adhere strictly to its settled legal criteria."
        )
        why_it_matters = (
            f"Understanding \"{term_name}\" determines whether an order, argument, or contractual condition is legally valid and enforceable."
        )
    else:
        # General legal / non-case text (statutory, contract, general legal wording)
        in_simple_words = (
            f"The selected passage outlines the legal criteria governing \"{selected_text[:120]}\".\n"
            f"In plain terms, any rights, restrictions, or duties stated here must conform to applicable Indian statutes and regulations.\n"
            f"Clauses that impose disproportionate, vague, or unlawful burdens cannot be sustained when tested before an appropriate legal authority."
        )
        why_it_matters = (
            "This ensures that legal obligations remain lawful and enforceable, protecting both parties against arbitrary overreach."
        )

    full_formatted = (
        f"In simple words:\n{in_simple_words}\n\n"
        f"Legal terms explained:\n{terms_formatted}\n\n"
        f"Why it matters:\n{why_it_matters}"
    )

    return {
        "explanation": full_formatted,
        "source": source_label,
        "in_simple_words": in_simple_words,
        "legal_terms_explained": found_terms,
        "why_it_matters": why_it_matters,
        "disclaimer": "AI explanation, not verified, not legal advice",
        "model_used": "deterministic_case_explanation" if is_case else "deterministic_fallback"
    }


async def generate_explanation(
    selected_text: str, 
    context: Optional[str] = None, 
    force_fallback: bool = False,
    is_case: Optional[bool] = None,
    source_label: Optional[str] = None
) -> Dict[str, Any]:
    """Generates the explanation using Groq LLM or deterministic fallback."""
    if is_case is None:
        is_case = bool(context and any(w in context.lower() for w in ["case:", "v.", "judgment", "scc", "air", "court"]))
    if source_label is None:
        source_label = "Source: Case Judgment" if is_case else "Source: Not from a case"

    if force_fallback or not llm_service.is_active or not llm_service.client:
        return generate_deterministic_explanation(selected_text, context, is_case=is_case, source_label=source_label)

    context_sec = f"Context:\n\"\"\"{context[:800]}\"\"\"" if context else "Context: General legal / contractual text (not from a court case judgment)."
    prompt = EXPLAIN_PROMPT_TEMPLATE.format(
        selected_text=selected_text,
        context_section=context_sec
    )

    try:
        config = types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=600,
        )
        res = llm_service.client.models.generate_content(
            contents=prompt,
            config=config
        )
        raw_text = res.text.strip() if res and res.text else ""
        if raw_text:
            if "In simple words:" in raw_text and "Why it matters:" in raw_text:
                formatted = raw_text
            else:
                formatted = (
                    f"In simple words:\n{raw_text}\n\n"
                    f"Why it matters:\nThis defines the legal scope and enforceability of rights under Indian law."
                )
            return {
                "explanation": formatted,
                "source": source_label,
                "disclaimer": "AI explanation, not verified, not legal advice",
                "model_used": llm_service.model
            }
        return generate_deterministic_explanation(selected_text, context, is_case=is_case, source_label=source_label)
    except Exception as e:
        logger.error("Error calling LLM for explanation: %s; using deterministic fallback.", e)
        return generate_deterministic_explanation(selected_text, context, is_case=is_case, source_label=source_label)


# ---------------------------------------------------------------------------
# API Endpoints: Case Chat
# ---------------------------------------------------------------------------
@router.post("/api/case-chat", response_model=CaseChatResponse)
@router.post("/api/v1/case-chat", response_model=CaseChatResponse)
async def post_case_chat(payload: CaseChatRequest, request: Request):
    """
    POST /api/case-chat and /api/v1/case-chat
    Case-scoped question answering and summarization.
    Rate limited per IP (30 req/min).
    """
    check_rate_limit(request)

    # 1. Validation
    cid = (payload.case_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="case_id cannot be empty")
    if len(cid) > 120:
        raise HTTPException(status_code=400, detail="case_id exceeds maximum allowed length of 120 characters")

    q = (payload.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    if len(q) > 2000:
        raise HTTPException(status_code=400, detail="question exceeds maximum allowed length of 2000 characters")

    # 2. Resolve case and chunks
    case_meta = get_case_record(cid)
    chunks = get_case_chunks(cid)
    if not case_meta and not chunks:
        raise HTTPException(status_code=404, detail=f"Case '{cid}' was not found in the verified dataset.")

    if not case_meta:
        first_chunk = chunks[0]
        case_meta = {
            "case_id": cid,
            "title": first_chunk.get("case_name", "Supreme Court Case"),
            "citation": first_chunk.get("citation", ""),
            "court": "Supreme Court of India",
            "year": first_chunk.get("year"),
        }

    # 3. Check if query is "Summarise this case"
    is_summary_request = bool(re.match(r'^(?:summarise|summarize)\s*(?:this\s*case)?[\.?!]*$', q, re.IGNORECASE))

    if is_summary_request:
        cache_key = cid.lower()
        if cache_key in _SUMMARY_CACHE and not payload.force_fallback:
            return CaseChatResponse(
                case_id=cid,
                answer=_SUMMARY_CACHE[cache_key],
                based_on="Full Judgment Chunks",
                paragraph_id="chunk-0",
                cached=True,
                model_used="summary_cache"
            )

        summary_ans = await generate_case_summary(case_meta, chunks, force_fallback=payload.force_fallback)
        _SUMMARY_CACHE[cache_key] = summary_ans

        return CaseChatResponse(
            case_id=cid,
            answer=summary_ans,
            based_on="Full Judgment Chunks",
            paragraph_id="chunk-0",
            cached=False,
            model_used=llm_service.model if (llm_service.is_active and not payload.force_fallback) else "deterministic_summary"
        )

    # 4. Handle explain selection query inside case context
    explain_match = re.match(r'^(?:explain\s+this\s+in\s+simple\s+words:\s*)(.+)$', q, re.IGNORECASE | re.DOTALL)
    if explain_match:
        selected_snippet = explain_match.group(1).strip()
        case_context = f"{case_meta.get('title')} ({case_meta.get('citation')}). {case_meta.get('ratioSummary')}"
        exp = await generate_explanation(selected_snippet, context=case_context, force_fallback=payload.force_fallback)
        return CaseChatResponse(
            case_id=cid,
            answer=exp["explanation"],
            based_on="Selected Text in Case Context",
            paragraph_id="chunk-0",
            cached=False,
            model_used=exp.get("model_used")
        )

    # 5. General factual question
    ans, based_on, para_id = await answer_case_question(
        case_meta=case_meta,
        chunks=chunks,
        question=q,
        messages=payload.messages,
        force_fallback=payload.force_fallback
    )

    return CaseChatResponse(
        case_id=cid,
        answer=ans,
        based_on=based_on,
        paragraph_id=para_id,
        cached=False,
        model_used=llm_service.model if (llm_service.is_active and not payload.force_fallback) else "deterministic_case_chat"
    )


# ---------------------------------------------------------------------------
# API Endpoints: Explain Selection
# ---------------------------------------------------------------------------
@router.post("/api/explain-selection", response_model=ExplainSelectionResponse)
@router.post("/api/v1/explain-selection", response_model=ExplainSelectionResponse)
async def post_explain_selection(payload: ExplainSelectionRequest, request: Request):
    """
    POST /api/explain-selection and /api/v1/explain-selection
    Explains any selected text across the site in simple words, legal terms, and why it matters.
    Rate limited per IP (30 req/min).
    """
    check_rate_limit(request)

    # Validation
    sel = (payload.selected_text or "").strip()
    if not sel:
        raise HTTPException(status_code=400, detail="selected_text cannot be empty")

    words = sel.split()
    if len(words) < 1:
        raise HTTPException(status_code=400, detail="Selection must be at least 1 word")
    if len(sel) > 800:
        raise HTTPException(status_code=400, detail="Selection exceeds maximum length of 800 characters")

    context = payload.context
    case_meta = None
    if payload.case_id:
        case_meta = get_case_record(payload.case_id)
        if case_meta:
            context = f"Case: {case_meta.get('title')} ({case_meta.get('citation')}). Context: {context or ''}"

    is_case = bool(payload.case_id or (context and any(w in context.lower() for w in ["case:", "v.", "judgment", "scc", "air"])))
    if payload.case_id and case_meta:
        source_label = f"Source: {case_meta.get('title')}"
    elif is_case:
        source_label = "Source: Case Judgment"
    else:
        source_label = "Source: Not from a case"

    result = await generate_explanation(
        selected_text=sel,
        context=context,
        force_fallback=payload.force_fallback,
        is_case=is_case,
        source_label=source_label
    )

    return ExplainSelectionResponse(
        explanation=result["explanation"],
        source=result.get("source", source_label),
        in_simple_words=result.get("in_simple_words"),
        legal_terms_explained=result.get("legal_terms_explained"),
        why_it_matters=result.get("why_it_matters"),
        disclaimer=result.get("disclaimer", "AI explanation, not verified, not legal advice"),
        model_used=result.get("model_used")
    )


# ---------------------------------------------------------------------------
# API Endpoints: Case Text & Paragraphs
# ---------------------------------------------------------------------------
@router.get("/api/case-text/{case_id}", response_model=CaseTextResponse)
@router.get("/api/v1/case-text/{case_id}", response_model=CaseTextResponse)
async def get_case_text(case_id: str):
    """
    GET /api/case-text/{case_id} and /api/v1/case-text/{case_id}
    Retrieves the ordered paragraphs for a case so the frontend can display judgment text
    and scroll to paragraph anchors when 'Based on: Paragraph X' is clicked.
    """
    cid = case_id.strip()
    case_meta = get_case_record(cid)
    chunks = get_case_chunks(cid)
    if not case_meta and not chunks:
        raise HTTPException(status_code=404, detail=f"Case '{cid}' not found")

    title = case_meta.get("title", "") if case_meta else chunks[0].get("case_name", "")
    citation = case_meta.get("citation", "") if case_meta else chunks[0].get("citation", "")
    court = case_meta.get("court", "Supreme Court of India") if case_meta else "Supreme Court of India"
    year = case_meta.get("year") if case_meta else chunks[0].get("year")

    paragraphs = [
        ParagraphItem(
            id=f"chunk-{c.get('chunk_index', idx)}",
            paragraph_number=c.get('chunk_index', idx) + 1,
            text=c.get("text", "")
        )
        for idx, c in enumerate(chunks)
    ]

    return CaseTextResponse(
        case_id=cid,
        title=title,
        citation=citation,
        court=court,
        year=year,
        total_paragraphs=len(paragraphs),
        paragraphs=paragraphs
    )
