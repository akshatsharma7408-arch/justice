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


@router.post("/chat", response_model=DocChatResponse)
async def chat_with_document_endpoint(payload: DocChatRequest):
    """
    POST /api/v1/doc/chat
    Takes doc_id + question, embeds question, retrieves top matching chunks,
    and answers using Gemini 3.8 Flash.
    Strict Grounding Rule: every claim in the answer must quote the exact clause it came from.
    If the answer is not in the document, returns "not found in this document".
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

    # 2. Retrieve top matching chunks
    top_chunks_with_scores = retrieve_top_chunks(doc, question, top_k=5)
    top_chunks = [item[0] for item in top_chunks_with_scores]
    max_score = top_chunks_with_scores[0][1] if top_chunks_with_scores else 0.0

    boilerplate_words = {
        "what", "when", "where", "which", "who", "whom", "how", "why", "this", "that", "there", 
        "have", "does", "with", "from", "your", "under", "about", "tell", "show", "give", 
        "please", "find", "explain", "describe", "company", "employer", "employee", "consultant", 
        "client", "party", "parties", "agreement", "contract", "herein", "hereof", "thereof", 
        "shall", "will", "would", "could", "should", "the", "and", "for", "any", "all", "terms", 
        "clause", "section", "document", "provision", "stipulation", "is", "are", "was", "were"
    }
    substantive_q_words = [w for w in re.findall(r'\b[a-z0-9]{3,}\b', question.lower()) if w not in boilerplate_words]
    doc_tokens = set(re.findall(r'\b[a-z0-9]{3,}\b', doc.raw_text.lower()))
    has_substantive_in_doc = any(w in doc_tokens for w in substantive_q_words) if substantive_q_words else False

    # CRITICAL: If retrieval returns nothing relevant, apply Two-Tier logic!
    if not has_substantive_in_doc or not top_chunks or max_score < 0.15:
        logger.info(f"DocChat: No relevant excerpts found in document for '{question}'.")
        if needs_specific_source(question) or is_document_specific_query(question):
            return DocChatResponse(
                answer=NOT_FOUND_SPECIFIC_MSG,
                citations=[],
                model_used="tier1_source_not_found"
            )
        else:
            tier2_ans = await llm_service.generate_tier2_explanation(question, force_fallback=payload.force_fallback)
            tier2_ans = citation_checker.check_and_badge_text(tier2_ans, doc_context=doc.raw_text, is_tier2=True)
            return DocChatResponse(
                answer=tier2_ans,
                citations=[],
                model_used="tier2_general_explanation"
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
        "1. Every single claim or statement in your answer MUST be grounded in the text and quote the exact clause it came from. "
        "2. If the question cannot be answered from the provided excerpts, or if the document does not mention or cover the topic, "
        "you MUST set the answer field to EXACTLY 'I couldn't find this in the available sources', set citations to an empty list [], and NEVER use outside legal knowledge or external facts. "
        "3. Do NOT make inferences, invent provisions, or assume standard industry terms if not explicitly stated in the document excerpts. "
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

                # Enforce strict "I couldn't find this in the available sources" guardrail
                lower_ans = ans.lower()
                is_not_found = (
                    "couldn't find" in lower_ans
                    or "could not find" in lower_ans
                    or "not found" in lower_ans
                    or "does not contain" in lower_ans
                    or "not mentioned" in lower_ans
                    or "not specified" in lower_ans
                    or "no mention" in lower_ans
                )

                if is_not_found or not ans or not raw_cits:
                    if needs_specific_source(question) or is_document_specific_query(question):
                        return DocChatResponse(
                            answer=NOT_FOUND_SPECIFIC_MSG,
                            citations=[],
                            model_used="tier1_source_not_found"
                        )
                    else:
                        tier2_ans = await llm_service.generate_tier2_explanation(question, force_fallback=payload.force_fallback)
                        tier2_ans = citation_checker.check_and_badge_text(tier2_ans, doc_context=doc.raw_text, is_tier2=True)
                        return DocChatResponse(
                            answer=tier2_ans,
                            citations=[],
                            model_used="tier2_general_explanation"
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

    if best_chunk and has_substantive_match and best_score >= 0.20:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', best_chunk.text) if s.strip()]
        matched_sentences = [
            s for s in sentences 
            if any(re.search(rf'\b{re.escape(w)}\b', s, re.IGNORECASE) for w in substantive_q_words)
        ]
        quote = matched_sentences[0] if matched_sentences else best_chunk.text

        ans_text = f"Under {best_chunk.clause_number} ({best_chunk.heading}), the document stipulates: \"{quote}\""
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

    if needs_specific_source(question) or is_document_specific_query(question):
        return DocChatResponse(
            answer=NOT_FOUND_SPECIFIC_MSG,
            citations=[],
            model_used="tier1_source_not_found"
        )
    else:
        tier2_ans = await llm_service.generate_tier2_explanation(question, force_fallback=payload.force_fallback)
        tier2_ans = citation_checker.check_and_badge_text(tier2_ans, doc_context=doc.raw_text, is_tier2=True)
        return DocChatResponse(
            answer=tier2_ans,
            citations=[],
            model_used="tier2_general_explanation"
        )



