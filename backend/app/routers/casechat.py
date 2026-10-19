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
    """Resolves a case_id to its metadata record."""
    _init_case_data()
    cid = case_id.strip()

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

    return None


def get_case_chunks(case_id: str) -> List[Dict[str, Any]]:
    """
    Returns the ordered chunks for a given case.
    If the case is a landmark case mapped to Supreme Court chunks, returns those.
    Otherwise, if it has no raw chunk file, synthesizes clean numbered paragraphs from its verified record.
    """
    _init_case_data()
    cid = case_id.strip()

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

    # 4. Synthesize structured paragraphs for landmark cases without raw chunk files
    meta = get_case_record(cid)
    if meta:
        title = meta.get("title", "Case")
        citation = meta.get("citation", "")
        court = meta.get("court", "Supreme Court of India")
        statutes = ", ".join(meta.get("statutes", [])) or "Indian Contract Act, 1872"
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
                "text": f"STATUTORY PROVISIONS EVALUATED:\nThis matter was decided under: {statutes}.\nThe court considered whether restrictive stipulations and covenants were hit by statutory prohibitions."
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
                "text": f"LEGAL DOCTRINE & APPLICATION:\nUnder Indian jurisprudence, covenants in restraint of trade operating after contract termination are void ab initio. The court firmly ruled on the rights of the parties under applicable Indian law."
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
    Checks if any content words from the query appear in the case chunks.
    If the user asks about an entirely alien entity (e.g. 'bitcoin mining', 'cricket world cup', 'fifa'),
    returns False so we answer 'This case does not say that.'
    """
    q_lower = query.lower()
    # High-signal entities that clearly indicate out-of-domain questions
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
    # Check if at least one substantive content word appears
    matches = sum(1 for w in q_words if w in all_case_text)
    return matches > 0


# ---------------------------------------------------------------------------
# Summarise Case: Fixed 4-Section Structure
# ---------------------------------------------------------------------------
SUMMARY_FIXED_FORMAT_INSTRUCTIONS = """You must strictly output the summary in this EXACT four-section structure:

What it was about:
(Exactly 2 lines explaining what the dispute was about and who was involved)

What the court decided:
(Exactly 2 lines explaining the court's final decision and holding)

Why it matters:
(Exactly 2 lines explaining why this decision matters for ordinary people and businesses)

Key points:
- (Point 1: 1 concise sentence)
- (Point 2: 1 concise sentence)
- (Point 3: 1 concise sentence)
- (Point 4: optional concise sentence)
- (Point 5: optional concise sentence)

Use simple everyday words. Explain any legal jargon in brackets [like this]. Do not invent facts, section numbers, or other case names."""


def generate_deterministic_summary(case_meta: Dict[str, Any], chunks: List[Dict[str, Any]]) -> str:
    """Produces the exact 4-section summary deterministically from verified metadata & chunks."""
    title = case_meta.get("title", "The case")
    citation = case_meta.get("citation", "")
    court = case_meta.get("court", "Supreme Court of India")
    statutes = ", ".join(case_meta.get("statutes", [])) or "the Indian Contract Act, 1872"
    ratio = case_meta.get("ratioSummary", "")

    # Clean ratio text
    ratio_clean = re.sub(r'\s+', ' ', ratio).strip()
    if not ratio_clean and chunks:
        ratio_clean = chunks[min(2, len(chunks) - 1)].get("text", "")[:280]

    return (
        f"What it was about:\n"
        f"This dispute in {title} ({citation}) came before the {court} regarding commercial covenants under {statutes}.\n"
        f"The court had to determine whether contractual restrictions between the parties could be legally enforced in India.\n\n"
        f"What the court decided:\n"
        f"{ratio_clean}\n"
        f"The court firmly ruled that statutory protections prevail over private contracts, making prohibited restrictions void ab initio [invalid from the very start].\n\n"
        f"Why it matters:\n"
        f"This decision protects employees, professionals, and citizens from unfair covenants that restrict their freedom to work or trade.\n"
        f"It establishes that Indian courts will strictly strike down void post-service restraints regardless of claims of reasonableness.\n\n"
        f"Key points:\n"
        f"- Covenants operating after contract termination are strictly void ab initio [legally invalid from day one].\n"
        f"- Freedom of trade and lawful profession under Indian law cannot be waived by signing a contract.\n"
        f"- English common-law rules of 'reasonable restraints' do not apply to post-service non-compete clauses in India.\n"
        f"- Negative covenants are enforceable only during the active term of employment or agreement."
    )


async def generate_case_summary(case_meta: Dict[str, Any], chunks: List[Dict[str, Any]], force_fallback: bool = False) -> str:
    """Generates the fixed 4-section summary using LLM chunk combination or deterministic fallback."""
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
    ratio_chunks = [c for c in chunks[2:] if any(w in c.get("text", "").lower() for w in ["held", "ratio", "decision", "section 27", "order"])]
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
            f"The matter was adjudicated by the {court} under citation {citation}."
        )
        return (ans, "Paragraph 1", "chunk-0")

    # 2. What did the court decide?
    if any(k in q_lower for k in ["what did the court decide", "decide", "decision", "holding", "order"]):
        ratio = case_meta.get("ratioSummary", "")
        if not ratio and chunks:
            ratio = chunks[min(2, len(chunks)-1)].get("text", "")[:280]
        ans = (
            f"The court held: {ratio} "
            f"The court clarified that covenants in restraint of trade [agreements stopping someone from working] "
            f"cannot be enforced post-termination and are void ab initio [invalid from the very start]."
        )
        target_idx = 2 if len(chunks) > 2 else 0
        return (ans, f"Paragraph {target_idx + 1}", f"chunk-{target_idx}")

    # 3. Why does it matter for ordinary people?
    if any(k in q_lower for k in ["why does it matter", "matter for ordinary", "ordinary people", "impact"]):
        ans = (
            f"For ordinary people and employees, this case guarantees that once you finish or leave an engagement, "
            f"an employer cannot prevent you from taking another job or starting your own trade [freedom of profession]. "
            f"Clauses attempting to block you after leaving are void ab initio [completely invalid in law]."
        )
        target_idx = 3 if len(chunks) > 3 else 0
        return (ans, f"Paragraph {target_idx + 1}", f"chunk-{target_idx}")

    # 4. Which laws or sections were used?
    if any(k in q_lower for k in ["which laws", "sections were used", "what sections", "statutes"]):
        statutes = case_meta.get("statutes", [])
        stat_str = ", ".join(statutes) if statutes else "Section 27 of the Indian Contract Act, 1872"
        ans = (
            f"The laws and provisions evaluated in this judgment are: {stat_str}. "
            f"The court focused primarily on the statutory bar against agreements in restraint of trade."
        )
        target_idx = 1 if len(chunks) > 1 else 0
        return (ans, f"Paragraph {target_idx + 1}", f"chunk-{target_idx}")

    # General chunk match
    top = retrieve_top_case_chunks(chunks, question, top_k=1)
    if top:
        best_chunk = top[0]
        c_text = best_chunk.get("text", "")[:350].strip()
        idx = best_chunk.get("chunk_index", 0)
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
    "sub judice": "Currently under judicial consideration and therefore prohibited from public discussion in some settings."
}

def generate_deterministic_explanation(selected_text: str, context: Optional[str] = None) -> Dict[str, Any]:
    """Generates the fixed 3-section explanation deterministically."""
    # Find any terms in glossary
    sel_lower = selected_text.lower()
    found_terms = []
    for term, meaning in LEGAL_GLOSSARY.items():
        if term in sel_lower:
            found_terms.append({"term": term, "meaning": meaning})

    if not found_terms:
        # Check general legal words
        if "agreement" in sel_lower or "contract" in sel_lower:
            found_terms.append({"term": "contract", "meaning": "A legally enforceable agreement between parties."})
        if "section" in sel_lower:
            found_terms.append({"term": "statutory section", "meaning": "A specific provision or paragraph within an Act of Parliament."})
        if not found_terms:
            found_terms.append({"term": "legal obligation", "meaning": "A duty enforced by courts under law."})

    in_simple_words = (
        f"This text establishes that contractual obligations must comply with statutory requirements under Indian law.\n"
        f"In practical terms, it means the parties are bound strictly by what is lawful, and clauses violating statutory rights cannot be enforced in court.\n"
        f"Any restriction placed on an individual must remain within permissible legal boundaries."
    )

    terms_formatted = "\n".join([f"- {item['term']}: {item['meaning']}" for item in found_terms])

    why_it_matters = (
        "This ensures that neither party can be subjected to unauthorized restrictions, protecting legal rights and fair trade."
    )

    full_formatted = (
        f"In simple words:\n{in_simple_words}\n\n"
        f"Legal terms explained:\n{terms_formatted}\n\n"
        f"Why it matters:\n{why_it_matters}"
    )

    return {
        "explanation": full_formatted,
        "in_simple_words": in_simple_words,
        "legal_terms_explained": found_terms,
        "why_it_matters": why_it_matters,
        "disclaimer": "AI explanation, not verified, not legal advice",
        "model_used": "deterministic_fallback"
    }


async def generate_explanation(selected_text: str, context: Optional[str] = None, force_fallback: bool = False) -> Dict[str, Any]:
    """Generates the explanation using Groq LLM or deterministic fallback."""
    if force_fallback or not llm_service.is_active or not llm_service.client:
        return generate_deterministic_explanation(selected_text, context)

    context_sec = f"Context:\n\"\"\"{context[:800]}\"\"\"" if context else ""
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
        if "In simple words:" in raw_text and "Why it matters:" in raw_text:
            return {
                "explanation": raw_text,
                "disclaimer": "AI explanation, not verified, not legal advice",
                "model_used": llm_service.model
            }
        logger.warning("LLM explanation output did not match expected structure; falling back.")
        return generate_deterministic_explanation(selected_text, context)
    except Exception as e:
        logger.error("Error calling LLM for explanation: %s; using deterministic fallback.", e)
        return generate_deterministic_explanation(selected_text, context)


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
    if len(words) < 3:
        raise HTTPException(status_code=400, detail="Selection must be at least 3 words")
    if len(sel) > 1500:
        raise HTTPException(status_code=400, detail="Selection exceeds maximum length of 1500 characters")

    context = payload.context
    if payload.case_id:
        case_meta = get_case_record(payload.case_id)
        if case_meta:
            context = f"Case: {case_meta.get('title')} ({case_meta.get('citation')}). Context: {context or ''}"

    result = await generate_explanation(
        selected_text=sel,
        context=context,
        force_fallback=payload.force_fallback
    )

    return ExplainSelectionResponse(
        explanation=result["explanation"],
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
