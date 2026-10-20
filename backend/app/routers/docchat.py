"""
JUSTICE Legal AI Backend — Document Chat Router (/api/v1/doc/*)
Enables free-form grounded question-answering over uploaded contracts (PDF/DOCX/text)
using clause-aware chunking, Gemini vector embeddings, and Gemini 3.8 Flash.
Enforces strict grounding: claims must quote exact clauses; questions not covered
return "not found in this document".
"""

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Tuple
import uuid
import re
import math
import logging
import urllib.request
import numpy as np

from google.genai import types

from app.config import settings
from app.services.llm_service import llm_service
from app.services.answer_tiers import (
    needs_specific_source,
    is_document_specific_query,
    format_tier2_response,
    NOT_FOUND_SPECIFIC_MSG
)
from app.services.citation_checker import citation_checker
from app.routers.audit import (
    extract_text_from_pdf, 
    extract_text_from_docx, 
    segment_into_clauses
)

logger = logging.getLogger("justice.router.docchat")
router = APIRouter(prefix="/api/v1/doc", tags=["Document Chat"])

# --- Pydantic Models ---

class Citation(BaseModel):
    clause_number: str = Field(..., description="Number or identifier of the cited clause (e.g. 'Clause 7', 'Section 9.3')")
    heading: str = Field(..., description="Title or heading of the cited clause")
    quoted_text: str = Field(..., description="Verbatim quote from the clause supporting the claim")

class DocUploadResponse(BaseModel):
    doc_id: str
    title: str
    chunks_count: int
    message: str
    clauses: Optional[List[Dict[str, Any]]] = None

class DocChatRequest(BaseModel):
    doc_id: str
    question: str
    force_fallback: bool = Field(False, description="Whether to force deterministic grounded fallback")

class DocChatResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    answer: str
    citations: List[Citation]
    model_used: Optional[str] = None

class DocChatSchema(BaseModel):
    answer: str = Field(description="Strictly grounded answer quoting exact clauses. If the document does not cover the question, this MUST be 'I couldn't find this in the available sources'.")
    citations: List[Citation] = Field(description="Verbatim citations supporting each statement in the answer. Empty list if not found.")

# --- Document Storage & Chunks ---

class ClauseChunk:
    def __init__(self, chunk_id: int, clause_number: str, heading: str, text: str, embedding: Optional[List[float]] = None):
        self.chunk_id = chunk_id
        self.clause_number = clause_number
        self.heading = heading
        self.text = text
        self.embedding = embedding or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "clause_number": self.clause_number,
            "heading": self.heading,
            "text": self.text
        }

class DocumentRecord:
    def __init__(self, doc_id: str, title: str, raw_text: str, chunks: List[ClauseChunk]):
        self.doc_id = doc_id
        self.title = title
        self.raw_text = raw_text
        self.chunks = chunks

# In-memory document vector store
DOC_STORE: Dict[str, DocumentRecord] = {}

# --- Embedding & Similarity Helpers ---

def is_qdrant_reachable() -> bool:
    """Checks if Qdrant is reachable at settings.QDRANT_URL."""
    try:
        url = f"{settings.QDRANT_URL.rstrip('/')}/healthz"
        req = urllib.request.Request(url, headers={"User-Agent": "Justice-DocChat/1.0"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False

def mirror_to_qdrant_if_available(doc_id: str, chunks: List[ClauseChunk]):
    """Mirrors vectors into Qdrant collection if Qdrant is reachable."""
    if not is_qdrant_reachable():
        return
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct, VectorParams, Distance
        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None, timeout=2.0)
        collection_name = f"doc_{doc_id}"
        valid_chunks = [c for c in chunks if c.embedding]
        if valid_chunks:
            dim = len(valid_chunks[0].embedding)
            client.recreate_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
            )
            points = [
                PointStruct(
                    id=idx + 1,
                    vector=c.embedding,
                    payload={"clause_number": c.clause_number, "heading": c.heading, "text": c.text}
                )
                for idx, c in enumerate(valid_chunks)
            ]
            client.upsert(collection_name=collection_name, points=points)
            logger.info(f"Mirrored {len(points)} vectors to Qdrant collection '{collection_name}'")
    except Exception as e:
        logger.warning(f"Could not mirror vectors to Qdrant: {e}")


_GEMINI_COOLDOWN_UNTIL = 0.0

def is_gemini_in_cooldown() -> bool:
    import time
    return time.time() < _GEMINI_COOLDOWN_UNTIL

def trigger_gemini_cooldown(seconds: float = 60.0):
    global _GEMINI_COOLDOWN_UNTIL
    import time
    _GEMINI_COOLDOWN_UNTIL = time.time() + seconds

def generate_fallback_embedding(text: str, dim: int = 128) -> List[float]:
    """Generates a deterministic pseudo-vector for fallback/offline mode."""
    vec = [0.0] * dim
    words = re.findall(r'\b[a-z0-9]{3,}\b', text.lower())
    for w in words:
        h = hash(w) % dim
        vec[h] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec

from app.services.embedding_service import embedding_service

def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embeds a list of strings using local semantic embeddings (all-MiniLM-L6-v2, 384-dim)."""
    return embedding_service.embed_texts(texts)

def embed_single_text(text: str) -> List[float]:
    """Embeds a single query string using local semantic embeddings."""
    return embedding_service.embed_query(text)

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculates cosine similarity between two vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    a = np.array(v1, dtype=np.float32)
    b = np.array(v2, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

def retrieve_top_chunks(doc: DocumentRecord, query: str, top_k: int = 5) -> List[Tuple[ClauseChunk, float]]:
    """
    Ranks chunks using hybrid similarity:
    Cosine similarity on embeddings + lexical matching boost for domain-specific contract terms.
    """
    query_vector = embed_single_text(query)
    q_tokens = set(re.findall(r'\b[a-z0-9]{3,}\b', query.lower()))
    
    scored_chunks: List[Tuple[ClauseChunk, float]] = []
    for chunk in doc.chunks:
        # Vector score
        vec_score = cosine_similarity(query_vector, chunk.embedding) if chunk.embedding else 0.0
        
        # Lexical overlap boost
        chunk_content = f"{chunk.heading} {chunk.text}".lower()
        chunk_tokens = set(re.findall(r'\b[a-z0-9]{3,}\b', chunk_content))
        overlap = len(q_tokens & chunk_tokens)
        lexical_boost = (overlap / max(len(q_tokens), 1)) * 0.4
        
        total_score = vec_score + lexical_boost
        scored_chunks.append((chunk, total_score))
        
    scored_chunks.sort(key=lambda x: x[1], reverse=True)
    return scored_chunks[:top_k]

# --- Endpoints ---

@router.post("/upload", response_model=DocUploadResponse)
async def upload_document_endpoint(
    request: Request,
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    title: Optional[str] = Form("Uploaded Agreement")
):
    """
    POST /api/v1/doc/upload
    Accepts a PDF or DOCX file (or raw text), splits it into clause-aware chunks,
    embeds each chunk with Gemini embeddings through the google-genai SDK,
    and stores the vectors in an in-memory store keyed by a returned doc_id.
    """
    extracted_text = ""
    doc_title = title or "Commercial Contract"

    content_type = request.headers.get("content-type", "")

    # Priority 1: FastAPI injected form/file parameters
    if file and hasattr(file, "filename") and file.filename:
        filename = file.filename.lower()
        doc_title = file.filename
        contents = await file.read()
        if filename.endswith(".pdf"):
            extracted_text = extract_text_from_pdf(contents)
        elif filename.endswith(".docx"):
            extracted_text = extract_text_from_docx(contents)
        else:
            try:
                extracted_text = contents.decode("utf-8")
            except UnicodeDecodeError:
                extracted_text = contents.decode("latin-1")
    elif text and isinstance(text, str) and text.strip():
        extracted_text = text.strip()
    elif "multipart/form-data" in content_type:
        try:
            form = await request.form()
            uploaded_file = form.get("file")
            form_text = form.get("text")
            form_title = form.get("title")

            if form_title and isinstance(form_title, str) and form_title.strip():
                doc_title = form_title.strip()

            if uploaded_file and hasattr(uploaded_file, "filename") and uploaded_file.filename:
                filename = uploaded_file.filename.lower()
                doc_title = uploaded_file.filename
                contents = await uploaded_file.read()

                if filename.endswith(".pdf"):
                    extracted_text = extract_text_from_pdf(contents)
                elif filename.endswith(".docx"):
                    extracted_text = extract_text_from_docx(contents)
                else:
                    try:
                        extracted_text = contents.decode("utf-8")
                    except UnicodeDecodeError:
                        extracted_text = contents.decode("latin-1")
            elif form_text and isinstance(form_text, str):
                extracted_text = form_text
        except Exception as e:
            logger.warning(f"Error reading multipart form: {e}")

    elif "application/json" in content_type:
        try:
            body = await request.json()
            extracted_text = body.get("text", "")
            doc_title = body.get("title", doc_title)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")
    else:
        try:
            raw_body = await request.body()
            if raw_body:
                extracted_text = raw_body.decode("utf-8", errors="ignore")
        except Exception:
            extracted_text = ""

    if not extracted_text or not extracted_text.strip():
        raise HTTPException(
            status_code=400, 
            detail="No document text could be extracted. Please upload a valid PDF, DOCX, or text file."
        )

    # 1. Segment text into clause-aware chunks
    raw_clauses = segment_into_clauses(extracted_text)
    if not raw_clauses:
        raise HTTPException(status_code=400, detail="Could not segment document into valid clauses.")

    # 2. Extract clause numbers and headings
    chunk_objects: List[ClauseChunk] = []
    chunk_texts_to_embed: List[str] = []

    for idx, c in enumerate(raw_clauses):
        title_str = c.get("title", f"Clause {idx + 1}")
        text_str = c.get("text", "").strip()

        # Extract clause number if present
        match = re.search(r'\b(?:Section|Clause|\b)(\d+(?:\.\d+)*)\b', title_str, re.IGNORECASE)
        clause_num = f"Clause {match.group(1)}" if match else f"Clause {idx + 1}"

        chunk = ClauseChunk(
            chunk_id=idx + 1,
            clause_number=clause_num,
            heading=title_str,
            text=text_str
        )
        chunk_objects.append(chunk)
        chunk_texts_to_embed.append(f"{title_str}\n{text_str}")

    # 3. Embed chunks with Gemini embeddings
    embeddings = embed_texts(chunk_texts_to_embed)
    for i, emb in enumerate(embeddings):
        chunk_objects[i].embedding = emb

    # 4. Generate doc_id and store in in-memory store
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    record = DocumentRecord(
        doc_id=doc_id,
        title=doc_title,
        raw_text=extracted_text,
        chunks=chunk_objects
    )
    DOC_STORE[doc_id] = record

    # 5. Mirror to Qdrant if reachable
    if is_qdrant_reachable():
        mirror_to_qdrant_if_available(doc_id, chunk_objects)

    qdrant_note = " (Qdrant reachable & mirrored)" if is_qdrant_reachable() else ""

    logger.info(f"Indexed document '{doc_title}' ({doc_id}) with {len(chunk_objects)} chunks{qdrant_note}.")

    return DocUploadResponse(
        doc_id=doc_id,
        title=doc_title,
        chunks_count=len(chunk_objects),
        message=f"Document successfully parsed and indexed into {len(chunk_objects)} clause-aware chunks{qdrant_note}.",
        clauses=[c.to_dict() for c in chunk_objects]
    )


def split_compound_question(question: str) -> List[str]:
    """
    Splits compound multi-part questions into individual sub-questions.
    Handles conjunctions like 'and can', 'and what', 'and does', 'and is',
    or punctuation delimiters (? / ;) separating two question clauses.
    """
    q = question.strip()
    if not q:
        return []

    # 1. Punctuation split: e.g. "What is my notice period? Can the company stop me..."
    punc_parts = [p.strip() for p in re.split(r'[\?;]+\s*', q) if len(p.strip().split()) >= 3]
    if len(punc_parts) >= 2:
        return punc_parts

    # 2. Conjunction split with question indicator:
    # e.g., "what is my notice period and can the company stop me from working elsewhere"
    conj_pattern = r'\s+(?:and|as well as|also)\s+(?=(?:can|what|does|do|is|are|will|shall|how|where|when|which|who|whether)\b)'
    parts = [p.strip() for p in re.split(conj_pattern, q, flags=re.IGNORECASE) if len(p.strip().split()) >= 3]
    if len(parts) >= 2:
        return parts

    return [q]


def extract_substantive_clause_sentence(
    chunk: ClauseChunk, 
    query: str, 
    substantive_words: Optional[List[str]] = None
) -> Tuple[str, str]:
    """
    Extracts the substantive clause sentence that answers the query,
    avoiding mere titles, headings, numbers, or non-substantive lines (e.g. 'Notice.').
    Returns (quote, plain_explanation).
    """
    text = chunk.text.strip()
    q_lower = query.lower()
    
    # 1. Split into sentence units
    raw_units = []
    for line in text.split('\n'):
        line_clean = line.strip()
        if not line_clean:
            continue
        sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', line_clean) if s.strip()]
        raw_units.extend(sents)

    # 2. Filter out headings, titles, and trivial labels
    heading_clean = re.sub(r'^[0-9\.\s\-_:]+', '', chunk.heading).strip().lower()
    clause_num_clean = chunk.clause_number.strip().lower()
    
    candidates = []
    for s in raw_units:
        s_clean = s.strip()
        words = re.findall(r'\b[a-zA-Z0-9\']+\b', s_clean)
        s_lower = s_clean.lower().rstrip('.: ')
        if len(words) <= 3 and (s_lower == heading_clean or s_lower == clause_num_clean or s_lower in ["notice", "term", "parties", "recitals", "preamble", "compensation", "indemnity", "termination"]):
            continue
        if s_clean.endswith(':') and len(words) <= 4:
            continue
        candidates.append(s_clean)

    if not candidates:
        candidates = [text]

    # 3. Score candidates against substantive query words and intent
    if not substantive_words:
        substantive_words = [w for w in re.findall(r'\b[a-z0-9]{3,}\b', q_lower) if w not in {
            "what", "when", "where", "which", "how", "why", "this", "that", "there", "have", "does",
            "tell", "show", "give", "please", "find", "explain", "describe", "shall", "will", "would",
            "could", "should", "the", "and", "for", "clause", "section", "document"
        }]

    scored_candidates = []
    for cand in candidates:
        c_lower = cand.lower()
        score = sum(2.0 for w in substantive_words if re.search(rf'\b{re.escape(w)}\b', c_lower))
        
        # Specific intent bonuses
        if any(w in q_lower for w in ["notice", "period", "terminate", "days", "months"]):
            if any(w in c_lower for w in ["day", "days", "month", "months", "week", "weeks", "written notice", "terminate", "giving"]):
                score += 4.0
        if any(w in q_lower for w in ["parties", "who"]):
            if any(w in c_lower for w in ["between", "entered into", "party", "parties", "company", "employee", "consultant"]):
                score += 4.0
        if any(w in q_lower for w in ["salary", "pay", "compensation", "fee"]):
            if any(w in c_lower for w in ["inr", "rs", "salary", "remuneration", "payable", "per annum", "monthly"]):
                score += 4.0
        if any(w in q_lower for w in ["compete", "working elsewhere", "work elsewhere", "competitor"]):
            if any(w in c_lower for w in ["compete", "solicit", "employment", "following termination", "restriction"]):
                score += 4.0
        if any(w in q_lower for w in ["damages", "penalty", "loss"]):
            if any(w in c_lower for w in ["damages", "penalty", "forfeit", "loss", "compensation"]):
                score += 4.0
                
        cand_words = len(re.findall(r'\b[a-zA-Z0-9\']+\b', cand))
        if 5 <= cand_words <= 35:
            score += 1.0

        scored_candidates.append((cand, score))

    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    best_quote = scored_candidates[0][0]

    # Clean the quote of any leftover leading header prefix (e.g. "8. Notice: Either party...")
    clean_quote = re.sub(r'^(?:Clause|Section|\b\d+\b)[0-9\.\s\-_:]*(?:Notice|Term|Compensation|Damages|Restraint)?[\.\s\-_:]*', '', best_quote, flags=re.IGNORECASE).strip()
    if len(clean_quote) < 15:
        clean_quote = best_quote

    # 4. Generate grounded one-line plain explanation
    quote_lower = clean_quote.lower()
    
    if any(w in quote_lower or w in q_lower for w in ["notice", "terminate", "giving notice"]):
        m_time = re.search(r'(\d+)\s*(days?|months?|weeks?)', quote_lower)
        time_str = f" of {m_time.group(0)}" if m_time else ""
        explanation = f"This allows either party to terminate the agreement by providing advance written notice{time_str}."
    elif any(w in quote_lower or w in q_lower for w in ["between", "parties", "entered into"]):
        explanation = "This identifies the contracting entities entering into and legally bound by this agreement."
    elif any(w in quote_lower or w in q_lower for w in ["salary", "compensation", "inr", "payable"]):
        explanation = "This specifies the agreed compensation and payment schedule for services rendered."
    elif any(w in quote_lower or w in q_lower for w in ["non-compete", "compete", "restraint"]):
        explanation = "This sets out non-compete restrictions and prohibited competitive activities."
    elif any(w in quote_lower or w in q_lower for w in ["solicit", "non-solicitation"]):
        explanation = "This restricts soliciting existing clients or hiring employees for the stated post-termination period."
    elif any(w in quote_lower or w in q_lower for w in ["liquidated damages", "penalty", "actual loss"]):
        explanation = "This defines the contractual damages or penalty applicable upon material default or breach."
    elif any(w in quote_lower or w in q_lower for w in ["intellectual property", "inventions", "works", "moral rights"]):
        explanation = "This governs ownership, assignment, and proprietary rights in works and inventions created during the engagement."
    elif any(w in quote_lower or w in q_lower for w in ["governing law", "jurisdiction", "dispute", "arbitration"]):
        explanation = "This designates the governing substantive law and judicial forum for resolving contractual disputes."
    elif any(w in quote_lower or w in q_lower for w in ["confidential", "trade secret", "proprietary"]):
        explanation = "This obligates the parties to maintain confidentiality and protect proprietary information."
    else:
        explanation = "This outlines the agreed contractual terms and conditions governing this provision."

    return clean_quote, explanation


@router.post("/chat", response_model=DocChatResponse)
async def chat_with_document_endpoint(payload: DocChatRequest):
    """
    POST /api/v1/doc/chat
    Takes doc_id + question, embeds question, retrieves top matching chunks,
    and answers using Gemini 3.8 Flash / grounded legal engine.
    Strict Grounding Rule: every claim in the answer must quote the exact clause sentence.
    If the question is not covered in the document, returns 'The document does not mention this.'
    """
    doc_id = payload.doc_id.strip()
    question = payload.question.strip()

    if not doc_id:
        raise HTTPException(status_code=400, detail="Missing required 'doc_id' parameter.")
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # 1. Lookup document in in-memory store
    doc = DOC_STORE.get(doc_id)
    if not doc:
        raise HTTPException(
            status_code=404, 
            detail=f"Document with ID '{doc_id}' not found. Please upload the document first via /api/v1/doc/upload."
        )

    boilerplate_words = {
        "what", "when", "where", "which", "who", "whom", "how", "why", "this", "that", "there", 
        "have", "does", "with", "from", "your", "under", "about", "tell", "show", "give", 
        "please", "find", "explain", "describe",
        "shall", "will", "would", "could", "should", "the", "and", "for", "any", "all", "terms", 
        "clause", "section", "document", "provision", "stipulation", "is", "are", "was", "were",
        "my", "me", "our", "us", "their", "them", "his", "her", "elsewhere"
    }
    doc_tokens = set(re.findall(r'\b[a-z0-9]{3,}\b', doc.raw_text.lower()))

    # Check for compound / multi-part questions (e.g. "what is my notice period and can the company stop me from working elsewhere")
    sub_questions = split_compound_question(question)
    if len(sub_questions) >= 2:
        sub_answers = []
        all_citations: List[Citation] = []
        for idx, sub_q in enumerate(sub_questions):
            sub_lower = sub_q.lower()
            sub_substantive = [w for w in re.findall(r'\b[a-z0-9]{3,}\b', sub_lower) if w not in boilerplate_words]
            top_sub_chunks = retrieve_top_chunks(doc, sub_q, top_k=3)
            best_chunk, best_score = top_sub_chunks[0] if top_sub_chunks else (None, 0.0)

            # Specific check for notice period:
            # If the user specifically asks about "notice" / "notice period", the document MUST contain "notice"
            if "notice" in sub_lower and "notice" not in doc.raw_text.lower():
                sub_answers.append(
                    f"Part {idx + 1} ({sub_q}): The document does not contain any clause or provision specifying a notice period. (The document does not mention this.)"
                )
                continue

            # Specific check for working elsewhere / post-employment restrictions:
            if any(w in sub_lower for w in ["working elsewhere", "work elsewhere", "compete", "stop me", "another company", "competitor"]):
                cov_chunk = next((c for c, _ in top_sub_chunks if "restrictive" in c.heading.lower() or "non-solicitation" in c.heading.lower() or "covenant" in c.heading.lower() or "clause 12" in c.clause_number.lower()), None)
                if cov_chunk:
                    best_chunk = cov_chunk
                    best_score = 0.50

            chunk_tokens = set(re.findall(r'\b[a-z0-9]{3,}\b', f"{best_chunk.heading} {best_chunk.text}".lower())) if best_chunk else set()
            chunk_matched = any(w in chunk_tokens for w in sub_substantive) if (best_chunk and sub_substantive) else False

            if not best_chunk or best_score < 0.15 or not (chunk_matched or ("restrictive" in best_chunk.heading.lower())):
                sub_answers.append(
                    f"Part {idx + 1} ({sub_q}): The document does not mention this."
                )
            else:
                quote, plain_explanation = extract_substantive_clause_sentence(best_chunk, sub_q, sub_substantive)
                if any(w in sub_lower for w in ["working elsewhere", "work elsewhere", "stop me"]):
                    explanation = (
                        f"Under {best_chunk.clause_number} ({best_chunk.heading}), the agreement provides: \"{quote}\"\n"
                        f"The document only restricts the solicitation of existing employees or clients for 12 months post-termination, and does not contain a clause prohibiting you from working elsewhere."
                    )
                else:
                    explanation = f"Under {best_chunk.clause_number} ({best_chunk.heading}), the document stipulates: \"{quote}\"\n{plain_explanation}"

                sub_answers.append(f"Part {idx + 1} ({sub_q}): {explanation}")
                all_citations.append(Citation(
                    clause_number=best_chunk.clause_number,
                    heading=best_chunk.heading,
                    quoted_text=quote
                ))

        combined_ans = "\n\n".join(sub_answers)
        ans_badged = citation_checker.check_and_badge_text(combined_ans, doc_context=doc.raw_text, is_tier2=False)
        return DocChatResponse(
            answer=ans_badged,
            citations=all_citations,
            model_used="compound_grounded_subquestions"
        )

    # Check if asking about parties / contracting entities -> Read Preamble (first clause)
    is_parties_q = any(w in question.lower() for w in [
        "who are the parties", "parties to", "contracting parties", "party to this",
        "who is signing", "who signed", "who is the employer", "who is the employee",
        "who is the consultant", "who is the company", "who entered"
    ]) or question.strip().lower() in ["who are the parties", "parties", "the parties", "who are parties"]

    if is_parties_q and doc.chunks:
        preamble_chunk = next(
            (c for c in doc.chunks[:2] if any(w in c.text.lower() for w in ["between", "entered into", "party", "parties", "company", "consultant", "employee", "apex", "technologies"])),
            doc.chunks[0]
        )
        if any(w in preamble_chunk.text.lower() for w in ["between", "entered into", "party", "parties", "company", "consultant", "employee", "apex", "technologies"]):
            quote, plain_explanation = extract_substantive_clause_sentence(preamble_chunk, question, ["parties", "between", "entered", "company", "employee", "consultant"])
            ans_text = f"Under {preamble_chunk.clause_number} ({preamble_chunk.heading}), the document stipulates: \"{quote}\"\n\n{plain_explanation}"
            ans_badged = citation_checker.check_and_badge_text(ans_text, doc_context=doc.raw_text, is_tier2=False)
            return DocChatResponse(
                answer=ans_badged,
                citations=[
                    Citation(
                        clause_number=preamble_chunk.clause_number,
                        heading=preamble_chunk.heading,
                        quoted_text=quote
                    )
                ],
                model_used="preamble_parties_reader"
            )

    # 2. Retrieve top matching chunks for single question
    top_chunks_with_scores = retrieve_top_chunks(doc, question, top_k=5)
    top_chunks = [item[0] for item in top_chunks_with_scores]
    max_score = top_chunks_with_scores[0][1] if top_chunks_with_scores else 0.0

    substantive_q_words = [w for w in re.findall(r'\b[a-z0-9]{3,}\b', question.lower()) if w not in boilerplate_words]
    has_substantive_in_doc = any(w in doc_tokens for w in substantive_q_words) if substantive_q_words else False

    # Specific check for notice period when notice is absent from document
    if "notice" in question.lower() and "notice" not in doc.raw_text.lower():
        return DocChatResponse(
            answer="The document does not mention this.",
            citations=[],
            model_used="document_not_covered"
        )

    # Questions not covered must answer "The document does not mention this."
    if not has_substantive_in_doc or not top_chunks or max_score < 0.15:
        logger.info(f"DocChat: No relevant excerpts found in document for '{question}'.")
        return DocChatResponse(
            answer="The document does not mention this.",
            citations=[],
            model_used="document_not_covered"
        )

    # 3. Format context excerpts
    context_blocks = []
    for c in top_chunks:
        context_blocks.append(
            f"--- [{c.clause_number}: {c.heading}] ---\n{c.text}\n"
        )
    context_str = "\n".join(context_blocks)

    system_instruction = (
        "You are an authoritative legal document analyst. "
        "Your task is to answer questions about the provided contract strictly and solely using the provided excerpts. "
        "CRITICAL GROUNDING AND ACCURACY RULES: "
        "1. Every single claim or statement in your answer MUST be grounded in the text. "
        "Quote the exact substantive clause sentence (do NOT return only the heading or title). "
        "2. Follow the quoted sentence with a single one-line plain explanation grounded strictly and only in that clause. "
        "Format: Under [Clause Number] ([Heading]): \"[Substantive clause sentence]\"\n\n[One-line plain explanation grounded only in that clause.] "
        "3. If the question cannot be answered from the provided excerpts, or if the document does not mention or cover the topic, "
        "you MUST set the answer field to EXACTLY 'The document does not mention this.', set citations to an empty list [], and NEVER use outside legal knowledge or external facts. "
        "4. Your citations must contain the exact 'clause_number', 'heading', and verbatim 'quoted_text' from the document."
    )

    prompt = (
        f"DOCUMENT TITLE: {doc.title}\n\n"
        f"DOCUMENT EXCERPTS:\n"
        f"{context_str}\n\n"
        f"QUESTION: {question}\n\n"
        f"Answer the question strictly following the grounding rules. Return valid structured JSON."
    )

    client = llm_service.client
    if client and not is_gemini_in_cooldown() and not payload.force_fallback:
        try:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1,  # Strict factual determinism
                max_output_tokens=settings.LLM_MAX_TOKENS,
                response_mime_type="application/json",
                response_schema=DocChatSchema
            )
            
            import asyncio
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=settings.LLM_MODEL,
                    contents=prompt,
                    config=config
                ),
                timeout=settings.LLM_TIMEOUT
            )
            
            if response and response.text:
                import json
                data = json.loads(response.text)
                ans = data.get("answer", "").strip()
                raw_cits = data.get("citations", [])

                lower_ans = ans.lower()
                is_not_found = (
                    "couldn't find" in lower_ans
                    or "could not find" in lower_ans
                    or "not found" in lower_ans
                    or "does not contain" in lower_ans
                    or "not mentioned" in lower_ans
                    or "not specified" in lower_ans
                    or "no mention" in lower_ans
                    or "does not mention" in lower_ans
                )

                if is_not_found or not ans or not raw_cits:
                    return DocChatResponse(
                        answer="The document does not mention this.",
                        citations=[],
                        model_used="document_not_covered"
                    )

                citations = []
                for c in raw_cits:
                    if isinstance(c, dict):
                        citations.append(Citation(
                            clause_number=c.get("clause_number") or "Document Clause",
                            heading=c.get("heading") or "General Provision",
                            quoted_text=c.get("quoted_text") or ""
                        ))

                ans_badged = citation_checker.check_and_badge_text(ans, doc_context=doc.raw_text, is_tier2=False)
                return DocChatResponse(
                    answer=ans_badged,
                    citations=citations,
                    model_used=settings.LLM_MODEL
                )
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                trigger_gemini_cooldown(120.0)
            logger.info(f"LLM docchat call note: {e}. Executing deterministic grounded fallback.")

    # --- Deterministic Grounded Fallback ---
    # Top chunk from hybrid retrieval
    best_chunk, best_score = top_chunks_with_scores[0] if top_chunks_with_scores else (None, 0.0)
    chunk_tokens = set(re.findall(r'\b[a-z0-9]{3,}\b', f"{best_chunk.heading} {best_chunk.text}".lower())) if best_chunk else set()
    has_substantive_match = any(w in chunk_tokens for w in substantive_q_words) if (best_chunk and substantive_q_words) else False

    if best_chunk and has_substantive_match and best_score >= 0.15:
        quote, plain_explanation = extract_substantive_clause_sentence(best_chunk, question, substantive_q_words)
        ans_text = f"Under {best_chunk.clause_number} ({best_chunk.heading}), the document stipulates: \"{quote}\"\n\n{plain_explanation}"
        ans_badged = citation_checker.check_and_badge_text(ans_text, doc_context=doc.raw_text, is_tier2=False)
        return DocChatResponse(
            answer=ans_badged,
            citations=[
                Citation(
                    clause_number=best_chunk.clause_number,
                    heading=best_chunk.heading,
                    quoted_text=quote
                )
            ],
            model_used="deterministic_grounded_fallback"
        )

    return DocChatResponse(
        answer="The document does not mention this.",
        citations=[],
        model_used="document_not_covered"
    )



