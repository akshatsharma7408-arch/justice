"""
JUSTICE Legal AI Backend — Statutory Audit Router (/api/v1/audit/*)
Performs automated clause segmentation and statutory compliance auditing under
Section 27 of the Indian Contract Act, 1872 and Article 141 Supreme Court precedents,
with dynamic bare acts retrieval from SQLite (backend/data/justice_statutes.db).
"""

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import io
import re
import logging

from app.services.llm_service import llm_service
from app.services.statute_service import statute_service
from app.services.audit_service import audit_service

logger = logging.getLogger("justice.router.audit")
router = APIRouter(prefix="/api/v1/audit", tags=["Statutory Contract Audit"])

# --- Request / Response Models ---

class VerifyClauseRequest(BaseModel):
    clause_text: str = Field(..., description="Single clause text to verify against Indian statutory provisions")
    clause_title: Optional[str] = Field("Restrictive Covenant", description="Optional clause title or identifier")

class VerifyClauseResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    status: str = Field(..., description="'NON_COMPLIANT' or 'COMPLIANT'")
    risk_level: str = Field(..., description="'CRITICAL', 'CRITICAL RISK', 'MODERATE', or 'LOW'")
    statute: str
    section: str
    heading: str
    statutory_text: str
    binding_precedent: str
    legal_doctrine: str
    layman_translation: Optional[str] = None
    practical_impact: Optional[str] = None
    balanced_redline: Optional[str] = None
    # Rich fields for direct React UI consumption
    is_violation: Optional[bool] = None
    severity: Optional[str] = None
    governing_authorities: Optional[List[str]] = None
    precedents: Optional[List[str]] = None
    statutory_issue: Optional[str] = None
    model_used: Optional[str] = None

class AuditRequest(BaseModel):
    text: Optional[str] = Field(None, description="Raw contract text to audit")
    title: Optional[str] = Field("Commercial Agreement", description="Contract title or identifier")

class ClauseAuditResult(BaseModel):
    clause_index: int
    title: str
    original_text: str
    is_violation: bool
    statutory_violation: Optional[str] = None
    severity: str  # "CLEAN", "MEDIUM", "VOID_AB_INITIO"
    governing_authorities: List[str]
    legal_assessment: str
    statutory_heading: Optional[str] = None
    statutory_body: Optional[str] = None
    layman_translation: str
    practical_impact: str
    balanced_redline: Optional[str] = None

class ContractAuditResponse(BaseModel):
    document_title: str
    total_clauses_analyzed: int
    void_clauses_count: int
    risk_level: str  # "LOW", "MODERATE", "CRITICAL_VOID_TERMS"
    statutory_framework: List[str]
    clauses: List[ClauseAuditResult]
    audit_summary: str

# --- Helper Functions ---

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extracts text content from uploaded PDF bytes using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for i, page in enumerate(reader.pages):
            txt = page.extract_text()
            if txt:
                pages_text.append(txt)
        return "\n\n".join(pages_text)
    except Exception as e:
        logger.error(f"Failed to parse PDF document: {e}")
        raise HTTPException(status_code=400, detail=f"PDF extraction error: {str(e)}")

def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extracts text content from uploaded DOCX bytes using python-docx."""
    try:
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as e:
        logger.error(f"Failed to parse DOCX document: {e}")
        raise HTTPException(status_code=400, detail=f"DOCX extraction error: {str(e)}")

def segment_into_clauses(text: str) -> List[Dict[str, str]]:
    """Segments a contract into distinct clauses using pattern recognition."""
    raw_clauses = re.split(r'\n(?=(?:Section|Clause|\b\d+\.|\b[A-Z\s]{4,}:)\s*)', text)
    clauses = []
    
    for i, c in enumerate(raw_clauses):
        cleaned = c.strip()
        if len(cleaned) < 25:
            continue
            
        first_line = cleaned.split("\n")[0][:80].strip()
        title = first_line if len(first_line) > 5 else f"Clause {i+1}"
        clauses.append({
            "title": title,
            "text": cleaned
        })
        
    if not clauses and text.strip():
        clauses.append({
            "title": "Entire Agreement Body",
            "text": text.strip()
        })
        
    return clauses

def evaluate_section_27_violation(clause_text: str, clause_title: Optional[str] = None) -> Dict[str, Any]:
    """
    Statutory auditor evaluating Section 27, Indian Contract Act 1872.
    Delegates to AuditService for strict Section 27 post-employment classification
    and Article 141 precedent attribution.
    """
    return audit_service.evaluate_clause_heuristics(clause_text, clause_title)

async def process_contract_text(text: str, title: str) -> ContractAuditResponse:
    """Core pipeline executing segmentation, Section 27 evaluation, and Gemini redlining."""
    clauses = segment_into_clauses(text)
    audit_results: List[ClauseAuditResult] = []
    void_count = 0
    
    for idx, c in enumerate(clauses):
        eval_meta = audit_service.evaluate_clause_heuristics(c["text"], c["title"])
        is_viol = eval_meta["is_violation"]
        
        if is_viol:
            void_count += 1
            # Generate layman explanation & balanced redline via LLM or legal fallback
            synthesis = await llm_service.generate_layman_and_redline(
                clause_text=c["text"], 
                title=c["title"]
            )
            layman = synthesis.get("layman") or eval_meta.get("layman_translation", "")
            impact = synthesis.get("practical_impact") or eval_meta.get("practical_impact", "")
            redline = synthesis.get("redline") or eval_meta.get("balanced_redline", "")
        else:
            layman = eval_meta.get("layman_translation", "Standard operational clause governing terms during the active engagement.")
            impact = eval_meta.get("practical_impact", "Complies with Indian statutory standards; typical commercial risk.")
            redline = eval_meta.get("balanced_redline", None)

        audit_results.append(ClauseAuditResult(
            clause_index=idx + 1,
            title=c["title"],
            original_text=c["text"],
            is_violation=is_viol,
            statutory_violation=eval_meta.get("statutory_violation"),
            severity=eval_meta.get("severity", "CLEAN"),
            governing_authorities=eval_meta.get("governing_authorities", []),
            legal_assessment=eval_meta.get("legal_doctrine", ""),
            statutory_heading=eval_meta.get("heading"),
            statutory_body=eval_meta.get("statutory_text"),
            layman_translation=layman,
            practical_impact=impact,
            balanced_redline=redline
        ))

    risk = "CRITICAL_VOID_TERMS" if void_count > 0 else "LOW"
    summary = (
        f"Audited {len(clauses)} clauses. Identified {void_count} clause(s) violating Section 27 "
        f"of the Indian Contract Act, 1872. Under binding Supreme Court Article 141 precedent "
        f"(Percept D'Mark & Krishan Murgai), post-employment non-competes are void ab initio in India."
    )

    return ContractAuditResponse(
        document_title=title,
        total_clauses_analyzed=len(clauses),
        void_clauses_count=void_count,
        risk_level=risk,
        statutory_framework=[
            "Section 27, Indian Contract Act, 1872 (Restraint of Trade)",
            "Section 23, Indian Contract Act, 1872 (Lawful Object & Public Policy)",
            "Article 19(1)(g) & Article 141, Constitution of India"
        ],
        clauses=audit_results,
        audit_summary=summary
    )

# --- Endpoints ---

@router.post("/verify-clause", response_model=VerifyClauseResponse)
async def verify_clause_endpoint(payload: VerifyClauseRequest):
    """
    POST /api/v1/audit/verify-clause
    Inspects incoming clause text against Indian statutory provisions in justice_statutes.db.
    Invokes Gemini 3.8 Flash with structured JSON output for authoritative compliance audit.
    When a post-termination non-compete is detected:
    - status: 'NON-COMPLIANT'
    - risk_level: 'CRITICAL'
    - binding_precedent: Percept D'Mark (2006) & Krishan Murgai (1981)
    - legal_doctrine: Indian contract law treats post-employment non-compete covenants as void ab initio
      under Section 27, rejecting the English common law 'reasonableness' doctrine.
    """
    # 1. Fetch Section 27 dynamically from justice_statutes.db
    s27 = statute_service.get_provision_by_section("contract-act-1872", "27")
    heading = s27.get("heading") if s27 else "Agreement in restraint of trade, void"
    body = s27.get("body") if s27 else "Every agreement by which any one is restrained from exercising a lawful profession, trade or business of any kind, is to that extent void."
    statute_name = s27.get("act_title") if s27 else "The Indian Contract Act, 1872"

    # 2. Invoke LLM structured verification
    ai_audit = await llm_service.verify_clause_ai(
        clause_text=payload.clause_text,
        clause_title=payload.clause_title or "Restrictive Covenant"
    )

    # 3. Rule-based heuristic verification for robust validation
    heuristic_eval = audit_service.evaluate_clause_heuristics(payload.clause_text, payload.clause_title)
    is_violation = ai_audit.get("is_violation", False) or heuristic_eval.get("is_violation", False)

    if is_violation:
        status = "NON-COMPLIANT"
        risk_level = "CRITICAL"
        binding_precedent = (
            "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan & Anr. (2006) 4 SCC 227 and "
            "Superintendence Company of India (P) Ltd. v. Krishan Murgai (1981) 2 SCC 246"
        )
        legal_doctrine = (
            "Indian contract law treats post-employment non-compete covenants as void ab initio "
            "under Section 27, rejecting the English common law 'reasonableness' doctrine."
        )
        layman = ai_audit.get("layman_translation") or heuristic_eval.get("layman_translation")
        impact = ai_audit.get("practical_impact") or heuristic_eval.get("practical_impact")
        redline = ai_audit.get("balanced_redline") or heuristic_eval.get("balanced_redline")

        return VerifyClauseResponse(
            status=status,
            risk_level=risk_level,
            statute=statute_name,
            section="27",
            heading=heading,
            statutory_text=body,
            binding_precedent=binding_precedent,
            legal_doctrine=legal_doctrine,
            layman_translation=layman,
            practical_impact=impact,
            balanced_redline=redline,
            is_violation=True,
            severity="VOID_AB_INITIO",
            governing_authorities=[
                "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan & Anr. (2006) 4 SCC 227",
                "Superintendence Company of India (P) Ltd. v. Krishan Murgai (1981) 2 SCC 246",
                "Section 27, Indian Contract Act, 1872",
                "Article 19(1)(g) & Article 141, Constitution of India"
            ],
            precedents=[
                "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan & Anr. (2006) 4 SCC 227",
                "Superintendence Company of India (P) Ltd. v. Krishan Murgai (1981) 2 SCC 246"
            ],
            statutory_issue="Section 27, Indian Contract Act 1872 (Restraint of trade - Void ab initio)",
            model_used=ai_audit.get("model_used", "deterministic_legal_fallback")
        )
    else:
        return VerifyClauseResponse(
            status="COMPLIANT",
            risk_level="LOW",
            statute=statute_name,
            section="27",
            heading=heading,
            statutory_text=body,
            binding_precedent="Niranjan Shankar Golikari v. Century Spg. & Mfg. Co. Ltd. (1967) 2 SCR 378",
            legal_doctrine=(
                "Under Niranjan Shankar Golikari (1967), negative covenants operating strictly during the active subsistence "
                "of employment are valid to prevent conflict of interest. Does not violate Section 27."
            ),
            layman_translation=ai_audit.get("layman_translation") or "This clause appears compliant with Section 27 standards during the active term.",
            practical_impact=ai_audit.get("practical_impact") or "Standard commercial undertaking.",
            balanced_redline=None,
            is_violation=False,
            severity="CLEAN",
            governing_authorities=["Niranjan Shankar Golikari (1967) 2 SCR 378", "Section 27, Indian Contract Act, 1872"],
            precedents=["Niranjan Shankar Golikari v. Century Spg. & Mfg. Co. Ltd. (1967) 2 SCR 378"],
            statutory_issue=None,
            model_used=ai_audit.get("model_used", "deterministic_legal_fallback")
        )

@router.post("/contract", response_model=ContractAuditResponse)
@router.post("-contract", response_model=ContractAuditResponse)
async def audit_contract_endpoint(
    request: Request,
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    title: Optional[str] = Form("Uploaded Agreement")
):
    """
    POST /api/v1/audit/contract and POST /api/v1/audit-contract
    Universal multi-clause document analyzer accepting JSON bodies or file uploads (.pdf, .docx).
    """
    content_type = request.headers.get("content-type", "")
    extracted_text = ""
    doc_title = title or "Commercial Contract"

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

            if form_title and isinstance(form_title, str):
                doc_title = form_title

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
            logger.warning(f"Error reading multipart form in audit: {e}")

    # Handle standard JSON body
    elif "application/json" in content_type:
        try:
            body = await request.json()
            extracted_text = body.get("text", "")
            doc_title = body.get("title", "Standard Agreement")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")
    else:
        # Fallback reading raw body
        try:
            raw_body = await request.body()
            if raw_body:
                extracted_text = raw_body.decode("utf-8", errors="ignore")
        except Exception:
            extracted_text = ""

    if not extracted_text or not extracted_text.strip():
        # Provide sample non-compete text for interactive experimentation
        extracted_text = (
            "Clause 9. Restrictive Covenants and Non-Compete:\n"
            "The Consultant covenants and agrees that for a period of twenty-four (24) months following "
            "the termination or expiration of this Agreement for any reason whatsoever, the Consultant shall not, "
            "directly or indirectly, engage in, consult for, or be employed by any enterprise competing with the Company "
            "within the territory of India."
        )
        doc_title = "Sample Service Agreement (Section 27 Audit)"

    return await process_contract_text(extracted_text, doc_title)


class SynthesizeClauseRequest(BaseModel):
    clause_text: str = Field(..., description="Clause text to synthesize")
    contract_title: Optional[str] = Field("Commercial Agreement", description="Contract title")

@router.post("/synthesize")
async def synthesize_clause_endpoint(payload: SynthesizeClauseRequest):
    """
    POST /api/v1/audit/synthesize
    Generates real-time neural legal synthesis via LLM for agent trace cards.
    """
    from app.config import settings
    summary = await llm_service.synthesize_legal_summary(payload.clause_text, payload.contract_title or "Agreement")
    return {
        "synthesis": summary,
        "model": settings.LLM_MODEL
    }
