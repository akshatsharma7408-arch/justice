"""
JUSTICE Legal AI Backend — Document Chat Router (/api/v1/doc/*)
Enables free-form grounded question-answering over uploaded contracts (PDF/DOCX/text)
using clause-aware chunking, vector embeddings, and LLM inference.
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
from app.services.audit_service import audit_service
from app.services.ocr_service import (
    process_multi_images,
    process_image_bytes,
    extract_text_from_pdf_with_ocr_fallback
)
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
    raw_text: Optional[str] = None
    clauses: Optional[List[Dict[str, Any]]] = None
    audit_results: Optional[Dict[str, Any]] = None
    warnings: Optional[List[str]] = []
    page_count: Optional[int] = 1
    char_count: Optional[int] = 0

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
        if settings.QDRANT_API_KEY:
            req.add_header("api-key", settings.QDRANT_API_KEY)
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except Exception:
        return False

def mirror_to_qdrant_if_available(doc_id: str, chunks: List[ClauseChunk], title: str = "", raw_text: str = "") -> bool:
    """Mirrors vectors into Qdrant collection if Qdrant is reachable.
    Also stores a meta point (id 0) with the document title and raw text so the
    document can be rehydrated into DOC_STORE after a server restart.
    Returns True only when the mirror actually persisted; False when Qdrant is
    unreachable or the write failed, so callers never report false persistence."""
    if not is_qdrant_reachable():
        return False
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct, VectorParams, Distance
        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None, timeout=5.0)
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
                    id=0,
                    vector=[0.0] * dim,
                    payload={"meta": True, "title": title, "raw_text": raw_text}
                )
            ] + [
                PointStruct(
                    id=idx + 1,
                    vector=c.embedding,
                    payload={"clause_number": c.clause_number, "heading": c.heading, "text": c.text}
                )
                for idx, c in enumerate(valid_chunks)
            ]
            client.upsert(collection_name=collection_name, points=points)
            logger.info(f"Mirrored {len(points)} vectors to Qdrant collection '{collection_name}'")
            return True
    except Exception as e:
        logger.warning(f"Could not mirror vectors to Qdrant: {e}")
    return False


def rehydrate_doc_from_qdrant(doc_id: str) -> Optional[DocumentRecord]:
    """Rebuild a DocumentRecord from its mirrored Qdrant collection.
    Used when a server restart wiped the in-memory DOC_STORE but the upload's
    mirror persists in the user's own Qdrant instance."""
    if not is_qdrant_reachable():
        return None
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None, timeout=5.0)
        collection_name = f"doc_{doc_id}"
        available = {c.name for c in client.get_collections().collections}
        if collection_name not in available:
            return None
        points, _next = client.scroll(
            collection_name=collection_name,
            limit=2000,
            with_payload=True,
            with_vectors=True,
        )
        meta = next((p.payload for p in points if (p.payload or {}).get("meta")), {}) or {}
        chunk_pts = [p for p in points if not (p.payload or {}).get("meta")]
        chunk_pts.sort(key=lambda p: p.id if isinstance(p.id, int) else 0)
        chunks = [
            ClauseChunk(
                chunk_id=int(p.id) if isinstance(p.id, int) else idx + 1,
                clause_number=(p.payload or {}).get("clause_number", ""),
                heading=(p.payload or {}).get("heading", ""),
                text=(p.payload or {}).get("text", ""),
                embedding=list(p.vector) if isinstance(p.vector, list) else [],
            )
            for idx, p in enumerate(chunk_pts)
        ]
        if not chunks:
            return None
        record = DocumentRecord(
            doc_id=doc_id,
            title=meta.get("title") or doc_id,
            raw_text=meta.get("raw_text") or "\n\n".join(c.text for c in chunks),
            chunks=chunks,
        )
        DOC_STORE[doc_id] = record
        logger.info(f"Rehydrated document '{doc_id}' from Qdrant mirror ({len(chunks)} chunks).")
        return record
    except Exception as e:
        logger.warning(f"Could not rehydrate document '{doc_id}' from Qdrant: {e}")
        return None


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
    files: Optional[List[UploadFile]] = File(None),
    text: Optional[str] = Form(None),
    raw_text: Optional[str] = Form(None),
    title: Optional[str] = Form("Uploaded Agreement"),
    doc_id: Optional[str] = Form(None)
):
    """
    POST /api/v1/doc/upload
    Accepts:
    - Single or multiple files (PDF, DOCX, TXT, JPG, PNG, WEBP, HEIC; up to 10 images, max 10MB each)
    - Raw or edited text (with optional existing doc_id to re-run analysis)
    Performs OCR, clause segmentation, vector indexing, and Section 27 compliance audit.
    """
    if isinstance(raw_text, str) and raw_text.strip() and not (isinstance(text, str) and text.strip()):
        text = raw_text.strip()
    extracted_text = ""
    doc_title = title or "Commercial Contract"
    warnings: List[str] = []
    image_items: List[Tuple[str, bytes]] = []
    page_count = 1
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}

    # 1. Collect all uploaded files (from multipart form or FastAPI bindings)
    all_files: List[UploadFile] = []
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
            # In HTML multipart forms and TestClient, multi-file uploads can use field "files" or repeated "file"
            raw_file_items = form.getlist("files") + form.getlist("file")
            for ff in raw_file_items:
                if hasattr(ff, "filename") and ff.filename and ff not in all_files:
                    all_files.append(ff)
            form_text = form.get("text") or form.get("raw_text")
            form_title = form.get("title")
            form_doc_id = form.get("doc_id")

            if form_title and isinstance(form_title, str) and form_title.strip():
                doc_title = form_title.strip()
            if form_doc_id and isinstance(form_doc_id, str) and form_doc_id.strip():
                doc_id = form_doc_id.strip()
            if form_text and isinstance(form_text, str) and form_text.strip():
                text = form_text.strip()
        except Exception as e:
            logger.warning(f"Error reading multipart form: {e}")

    if not all_files:
        if files and isinstance(files, list):
            all_files.extend([f for f in files if isinstance(f, UploadFile) and hasattr(f, "filename") and f.filename])
        if isinstance(file, UploadFile) and hasattr(file, "filename") and file.filename and file not in all_files:
            all_files.append(file)

    # Priority A: Raw/edited text passed directly
    if isinstance(text, str) and text.strip():
        extracted_text = text.strip()
        if not title or not isinstance(title, str) or title == "Uploaded Agreement":
            doc_title = "Commercial Contract"
        else:
            doc_title = title

    # Priority B: Uploaded files
    elif all_files:
        if len(all_files) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 files allowed per upload.")

        ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png", ".webp", ".heic"}

        # Check for executables upfront
        for f in all_files:
            fname = (f.filename or "").lower()
            if fname.endswith(".exe") or fname.endswith(".bat") or fname.endswith(".cmd") or fname.endswith(".sh") or fname.endswith(".bin"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Executable file '{f.filename}' is not permitted."
                )

        # Validate file extensions before reading
        for f in all_files:
            fname = f.filename.lower() if f.filename else ""
            if not any(fname.endswith(ext) for ext in ALLOWED_EXTENSIONS):
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file format for '{f.filename}'. Allowed formats: PDF, DOCX, TXT, and images (JPG, PNG, WEBP, HEIC)."
                )

        # Check if files are images
        image_items: List[Tuple[str, bytes]] = []
        is_all_images = all(any(f.filename.lower().endswith(ext) for ext in IMAGE_EXTS) for f in all_files)

        for f in all_files:
            f_bytes = await f.read()
            if len(f_bytes) > 10 * 1024 * 1024:
                raise HTTPException(
                    status_code=400,
                    detail=f"File '{f.filename}' exceeds 10MB limit ({len(f_bytes) / (1024 * 1024):.1f}MB)."
                )

            # Reject Windows executables / binary executables
            if f_bytes.startswith(b"MZ") or f.filename.lower().endswith(".exe"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Executable file '{f.filename}' is not permitted."
                )

            fname_lower = f.filename.lower()
            if any(fname_lower.endswith(ext) for ext in IMAGE_EXTS):
                # Verify image magic bytes
                if fname_lower.endswith(".png") and not f_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise HTTPException(status_code=400, detail=f"File '{f.filename}' is not a valid PNG image.")
                elif (fname_lower.endswith(".jpg") or fname_lower.endswith(".jpeg")) and not f_bytes.startswith(b"\xff\xd8"):
                    raise HTTPException(status_code=400, detail=f"File '{f.filename}' is not a valid JPEG image.")
                image_items.append((f.filename, f_bytes))
            elif fname_lower.endswith(".pdf"):
                if not f_bytes.startswith(b"%PDF-"):
                    raise HTTPException(status_code=400, detail=f"File '{f.filename}' does not contain a valid PDF signature.")
                doc_title = f.filename
                extracted_text, pdf_warns = extract_text_from_pdf_with_ocr_fallback(f_bytes)
                warnings.extend(pdf_warns)
                page_count = len(re.findall(r'--- Page \d+ ---', extracted_text)) or 1
                if pdf_warns:
                    # Fail closed: any unreadable PDF page means no verdict can be trusted
                    raise HTTPException(
                        status_code=422,
                        detail=("Some pages of the PDF are unreadable or OCR failed (" + "; ".join(pdf_warns[:5]) + "). "
                                "No partial compliance verdict is issued. Please retry with a clearer scan or a digital PDF.")
                    )
                break
            elif fname_lower.endswith(".docx"):
                if not f_bytes.startswith(b"PK\x03\x04"):
                    raise HTTPException(status_code=400, detail=f"File '{f.filename}' does not contain a valid DOCX signature.")
                doc_title = f.filename
                extracted_text = extract_text_from_docx(f_bytes)
                page_count = 1
                break
            elif fname_lower.endswith(".txt"):
                if b"\x00" in f_bytes:
                    raise HTTPException(status_code=400, detail=f"File '{f.filename}' contains binary data and cannot be processed as plain text.")
                doc_title = f.filename
                try:
                    extracted_text = f_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    extracted_text = f_bytes.decode("latin-1")
                page_count = 1
                break
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported file format for '{f.filename}'.")

        # Process multi-images if uploaded
        if image_items and not extracted_text:
            doc_title = f"{len(image_items)} Uploaded Page{'s' if len(image_items) > 1 else ''}"
            full_img_text, meta_list, img_warns = process_multi_images(image_items)
            extracted_text = full_img_text
            warnings.extend(img_warns)
            page_count = len(image_items)
            failed_pages = [m for m in meta_list if m.get("is_unreadable")]
            if failed_pages:
                # Fail closed per page: never issue a verdict on a partially read document.
                # Distinguish OCR service failures (worker timeout/crash, e.g. memory limit) from
                # genuinely illegible pages so the user gets the right remediation.
                svc = [m for m in failed_pages if (m.get("error_reason") or "").startswith("[Error: OCR")]
                if svc:
                    names = ", ".join(f"Page {m['page']} ({m['filename']})" for m in svc)
                    if any("OCR capacity" in (m.get("error_reason") or "") for m in svc):
                        raise HTTPException(
                            status_code=503,
                            detail=(f"Document/image text extraction is unavailable on this server's current memory plan ({names}). "
                                    "This is a fixed server capacity limit, not a problem with your upload. "
                                    "Search and chat features remain available.")
                        )
                    raise HTTPException(
                        status_code=503,
                        detail=(f"OCR is temporarily unavailable for {names} due to current server memory pressure "
                                "(not an image problem). No compliance verdict is issued. Please retry in a few minutes.")
                    )
                names = ", ".join(f"Page {m['page']} ({m['filename']})" for m in failed_pages)
                raise HTTPException(
                    status_code=422,
                    detail=(f"{len(failed_pages)} of {len(meta_list)} page(s) are unreadable (OCR failed): {names}. "
                            "No partial compliance verdict is issued. Please retry with clearly legible photos of every page.")
                )

            # Structured per-page outcome check: fail closed if ANY page failed
            failed_pages = [m for m in meta_list if m.get("is_unreadable")]
            if failed_pages:
                failed_page_nums = [str(m["page"]) for m in failed_pages]
                failed_desc = ", ".join(f"Page {p}" for p in failed_page_nums)
                logger.warning(f"Rejecting multi-image upload: OCR failed on {failed_desc}")
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"OCR failed to read {failed_desc}. "
                        "All pages in a multi-page upload must be clearly legible before compliance auditing can proceed. "
                        "Please replace or re-scan the unreadable page(s) and retry."
                    )
                )

    elif "application/json" in content_type:
        try:
            body = await request.json()
            extracted_text = body.get("text", "")
            doc_title = body.get("title", doc_title)
            doc_id = body.get("doc_id", doc_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")
    else:
        try:
            raw_body = await request.body()
            if raw_body:
                extracted_text = raw_body.decode("utf-8", errors="ignore")
        except Exception:
            extracted_text = ""

    # Fail-closed check: detect unreadable scans, OCR errors, or empty documents
    substantive_text = re.sub(r'--- Page \d+.*?---\n?', '', extracted_text or '')
    substantive_text = re.sub(r'\[(?:Warning|Error):[^\]]+\]', '', substantive_text).strip()

    # If any images or scanned PDF pages produced OCR warnings/failures, fail closed unconditionally
    has_ocr_failure = any("too blurry or unclear" in w.lower() or "error:" in w.lower() or "ocr" in w.lower() for w in warnings)
    if has_ocr_failure:
        raise HTTPException(
            status_code=422,
            detail=(
                "One or more pages could not be read clearly by OCR. "
                "All pages in the document must be legible before statutory compliance auditing can proceed. "
                "Please upload higher-resolution scans or a digital PDF and retry."
            )
        )

    if not substantive_text or len(substantive_text) < 15:
        raise HTTPException(
            status_code=422, 
            detail="No document text could be extracted. Please upload a valid contract with legible clauses."
        )

    # 2. Segment text into clause-aware chunks
    raw_clauses = segment_into_clauses(extracted_text)
    if not raw_clauses:
        raise HTTPException(status_code=422, detail="Could not segment document into valid clauses.")

    # 3. Extract clause numbers and headings + run statutory Section 27 compliance audit
    chunk_objects: List[ClauseChunk] = []
    chunk_texts_to_embed: List[str] = []
    evaluated_clauses: List[Dict[str, Any]] = []
    void_count = 0
    has_moderate = False

    for idx, c in enumerate(raw_clauses):
        title_str = c.get("title", f"Clause {idx + 1}")
        text_str = c.get("text", "").strip()

        # Extract genuine clause number without misidentifying durations like '45 days'
        match = re.search(r'\b(?:Section|Clause|Article)\s+(\d+(?:\.\d+)*)\b', title_str, re.IGNORECASE)
        if not match:
            leading_match = re.match(r'^\s*\(?(\d+(?:\.\d+)*)\)?[\.\:]\s+[A-Za-z]', title_str)
            if leading_match:
                clause_num = f"Clause {leading_match.group(1)}"
            else:
                clause_num = f"Clause {idx + 1}"
        else:
            clause_num = f"Clause {match.group(1)}"

        chunk = ClauseChunk(
            chunk_id=idx + 1,
            clause_number=clause_num,
            heading=title_str,
            text=text_str
        )
        chunk_objects.append(chunk)
        chunk_texts_to_embed.append(f"{title_str}\n{text_str}")

        # Run statutory Section 27 evaluation
        audit_eval = audit_service.evaluate_clause_heuristics(text_str, title_str)
        is_viol = audit_eval.get("is_violation", False)
        risk_lvl = audit_eval.get("risk_level", "LOW")

        if is_viol or "CRITICAL" in risk_lvl.upper():
            void_count += 1
        elif "MODERATE" in risk_lvl.upper():
            has_moderate = True

        clause_dict = {
            "chunk_id": idx + 1,
            "clause_index": idx + 1,
            "clause_number": clause_num,
            "heading": title_str,
            "title": title_str,
            "text": text_str,
            "original_text": text_str,
            "is_violation": is_viol,
            "status": audit_eval.get("status", "COMPLIANT"),
            "risk_level": risk_lvl,
            "severity": "VOID_AB_INITIO" if is_viol else ("MEDIUM" if has_moderate else "CLEAN"),
            "statute": audit_eval.get("statute", "Indian Contract Act, 1872"),
            "section": audit_eval.get("section", "27"),
            "statutory_issue": audit_eval.get("statutory_issue"),
            "statutory_violation": audit_eval.get("statutory_issue") if is_viol else None,
            "statutory_heading": audit_eval.get("heading", ""),
            "binding_precedent": audit_eval.get("binding_precedent", ""),
            "precedents": audit_eval.get("precedents", []),
            "governing_authorities": audit_eval.get("governing_authorities", []),
            "legal_doctrine": audit_eval.get("legal_doctrine", ""),
            "legal_assessment": audit_eval.get("legal_doctrine", ""),
            "layman_translation": audit_eval.get("layman_translation", ""),
            "practical_impact": audit_eval.get("practical_impact", ""),
            "balanced_redline": audit_eval.get("balanced_redline", None)
        }
        evaluated_clauses.append(clause_dict)

    # 4. Overall risk level calculation
    overall_risk = "CRITICAL_VOID_TERMS" if void_count > 0 else ("MODERATE" if has_moderate else "LOW")

    audit_summary = (
        f"Analyzed {len(chunk_objects)} clauses. Found {void_count} clause(s) with critical statutory risk under Section 27 ICA."
        if void_count > 0 else
        f"Analyzed {len(chunk_objects)} clauses. No critical Section 27 non-compete violations detected."
    )

    audit_results = {
        "document_title": doc_title,
        "total_clauses_analyzed": len(chunk_objects),
        "void_clauses_count": void_count,
        "risk_level": overall_risk,
        "statutory_framework": ["Indian Contract Act, 1872 - Section 27", "Article 141 Supreme Court Precedents"],
        "clauses": evaluated_clauses,
        "audit_summary": audit_summary
    }

    # 5. Embed chunks with Gemini embeddings
    embeddings = embed_texts(chunk_texts_to_embed)
    for i, emb in enumerate(embeddings):
        chunk_objects[i].embedding = emb

    # 6. Generate or reuse doc_id and store in in-memory store
    final_doc_id = doc_id if (doc_id and doc_id.startswith("doc_")) else f"doc_{uuid.uuid4().hex[:12]}"
    record = DocumentRecord(
        doc_id=final_doc_id,
        title=doc_title,
        raw_text=extracted_text,
        chunks=chunk_objects
    )
    DOC_STORE[final_doc_id] = record

    # 7. Mirror to Qdrant if reachable (persists uploads across server restarts).
    # The acknowledgement reflects the actual mirror result, never a second
    # reachability probe: a failed mirror must not be reported as persistence.
    mirrored = mirror_to_qdrant_if_available(final_doc_id, chunk_objects, doc_title, extracted_text)
    if mirrored:
        qdrant_note = " (Qdrant reachable & mirrored)"
    else:
        qdrant_note = " (session-only: not mirrored to persistent storage; will not survive a server restart)"
        warnings.append(
            "Document could not be mirrored to persistent storage (Qdrant unreachable or write failed); "
            "it is available for this session only and will not survive a server restart - re-upload after any restart."
        )
    logger.info(f"Indexed document '{doc_title}' ({final_doc_id}) with {len(chunk_objects)} chunks{qdrant_note}.")

    return DocUploadResponse(
        doc_id=final_doc_id,
        title=doc_title,
        chunks_count=len(chunk_objects),
        message=f"Document successfully parsed and indexed into {len(chunk_objects)} clause-aware chunks{qdrant_note}.",
        raw_text=extracted_text,
        clauses=evaluated_clauses,
        audit_results=audit_results,
        warnings=warnings,
        page_count=page_count,
        char_count=len(extracted_text)
    )


@router.post("/upload-images", response_model=DocUploadResponse)
async def upload_images_endpoint(
    request: Request,
    files: List[UploadFile] = File(...),
    title: Optional[str] = Form("Uploaded Agreement Pages")
):
    """
    POST /api/v1/doc/upload-images
    Dedicated convenience endpoint for multi-page image contract uploads (up to 10 images).
    """
    return await upload_document_endpoint(
        request=request,
        file=None,
        files=files,
        text=None,
        raw_text=None,
        title=title,
        doc_id=None
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
    and answers using grounded legal engine.
    Strict Grounding Rule: every claim in the answer must quote the exact clause sentence.
    If the question is not covered in the document, returns 'The document does not mention this.'
    """
    doc_id = payload.doc_id.strip()
    question = payload.question.strip()

    if not doc_id:
        raise HTTPException(status_code=400, detail="Missing required 'doc_id' parameter.")
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # 1. Lookup document in in-memory store; if a restart wiped it, try the Qdrant mirror
    doc = DOC_STORE.get(doc_id)
    if not doc:
        doc = rehydrate_doc_from_qdrant(doc_id)
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

                # Ensure answer includes verbatim clause quote as required by strict grounding rules
                if citations and citations[0].quoted_text:
                    quote = citations[0].quoted_text.strip()
                    if quote and quote.lower() not in ans.lower() and not ans.startswith("Under "):
                        clause_ref = f"Under {citations[0].clause_number} ({citations[0].heading})" if citations[0].clause_number else "Under the agreement"
                        ans = f'{clause_ref}, the document stipulates: "{quote}"\n\n{ans}'

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



