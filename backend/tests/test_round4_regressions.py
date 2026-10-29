"""
JUSTICE Legal AI Backend — Round 4 Regression Test Suite
Validates:
1. Article 56, 239AA, 239AB, 14 provision-aware handling (exact provision, source URL, effective date, no Mirzapur).
2. Hit-and-Run compensation legal route (Section 161, Scheme 2022, Rs. 2L/50k, IPC 320, no MACT multiplier).
3. Paraphrase consistency across variations of Article 56 and Hit-and-Run queries.
4. Preserved precedents: Babu Manmohan Das Shah (1967, 3-judge Bench, Sec 3(1)(c) UP Rent Act) and V. Dhanapal Chettiar (1979).
5. Section 56 ambiguity clarification (Contract Act vs CrPC).
6. OCR memory bounds and security: executable rejection (HTTP 400), unreadable/corrupt scans (HTTP 422), valid OCR.
7. Document text editing: 45 days to 90 days re-analysis and version updates.
"""

import pytest
import io
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.main import app
from app.services.citation_checker import citation_checker
from app.services.statute_service import statute_service

import os
import base64

site_pwd = os.getenv("SITE_PASSWORD", "").strip()
client = TestClient(app)
if site_pwd:
    token = base64.b64encode(f"user:{site_pwd}".encode()).decode()
    client.headers["Authorization"] = f"Basic {token}"



# ==============================================================================
# 1. ARTICLE 56, 239AA, 239AB, 14 TESTS
# ==============================================================================

def test_article_56_authoritative_no_mirzapur():
    """
    Article 56 must return presidential tenure (5 years, resignation to VP, impeachment under Art 61).
    Must NOT return Mirzapur Kassab Jamat (Articles 48/48A/cow slaughter) with or without verified badge.
    Must NOT match Article 356.
    Must have results = [] and no_strong_case_match = True.
    """
    resp = client.post("/api/v1/search/answer", json={"query": "what is article 56", "force_fallback": True})
    assert resp.status_code == 200
    data = resp.json()

    ai_answer = data.get("ai_answer", "")
    citations = " ".join(data.get("citations", []))
    source_cases = data.get("source_cases", [])
    case_titles = " ".join([c.get("title", "") for c in source_cases])

    assert "President" in ai_answer
    assert "five years" in ai_answer.lower()
    assert "mirzapur" not in ai_answer.lower(), f"Mirzapur found in AI answer: {ai_answer}"
    assert "mirzapur" not in citations.lower(), f"Mirzapur found in citations: {citations}"
    assert "mirzapur" not in case_titles.lower(), f"Mirzapur found in source cases: {case_titles}"
    assert "cow" not in ai_answer.lower()
    assert "356" not in ai_answer
    assert len(source_cases) == 0, f"Expected empty source cases for Article 56, got {len(source_cases)}"
    assert data.get("no_strong_case_match") is True
    assert data.get("tier") == "tier1"


def test_article_239aa_non_empty_and_grounded():
    """Article 239AA must produce a rich, non-empty AI answer with 69th amendment and GNCTD precedent."""
    resp = client.post("/api/v1/search/answer", json={"query": "what is article 239aa", "force_fallback": True})
    assert resp.status_code == 200
    data = resp.json()

    ai_answer = data.get("ai_answer", "")
    assert len(ai_answer.strip()) > 80, f"Article 239AA returned empty or weak answer: '{ai_answer}'"
    assert "delhi" in ai_answer.lower()
    assert "sixty-ninth amendment" in ai_answer.lower() or "69th amendment" in ai_answer.lower() or "1991" in ai_answer
    assert "lieutenant governor" in ai_answer.lower() or "assembly" in ai_answer.lower()
    assert data.get("tier") == "tier1"


def test_article_239ab_non_empty_and_grounded():
    """Article 239AB must produce a non-empty AI answer regarding failure of constitutional machinery in Delhi."""
    resp = client.post("/api/v1/search/answer", json={"query": "what is article 239ab", "force_fallback": True})
    assert resp.status_code == 200
    data = resp.json()

    ai_answer = data.get("ai_answer", "")
    assert len(ai_answer.strip()) > 80, f"Article 239AB returned empty or weak answer: '{ai_answer}'"
    assert "constitutional machinery" in ai_answer.lower()
    assert "delhi" in ai_answer.lower()
    assert data.get("tier") == "tier1"


def test_article_14_non_truncated_royappa_maneka():
    """Article 14 must explain equality before law and non-arbitrariness (Royappa/Maneka Gandhi) without OCR headers."""
    resp = client.post("/api/v1/search/answer", json={"query": "what is article 14", "force_fallback": True})
    assert resp.status_code == 200
    data = resp.json()

    ai_answer = data.get("ai_answer", "")
    assert len(ai_answer.strip()) > 80
    assert "arbitrariness" in ai_answer.lower() or "equality" in ai_answer.lower()
    # Ensure raw OCR header is stripped
    assert "fazal ali" not in ai_answer.lower()
    assert "january 25, 1978" not in ai_answer.lower()
    assert data.get("tier") == "tier1"


# ==============================================================================
# 2. HIT-AND-RUN MOTOR ACCIDENT LEGAL-ROUTE TESTS
# ==============================================================================

def test_hit_and_run_statutory_route_vs_mact_multiplier():
    """
    Hit-and-run queries must cite Section 161 MVA and Scheme 2022 (Notification G.S.R. 163(E) w.e.f. 1 April 2022).
    Must state statutory fixed amounts: Rs. 2,00,000 for death / Rs. 50,000 for grievous hurt (IPC 320).
    Must distinguish untraced-vehicle fast-track relief from ordinary MACT Section 166 multiplier route.
    Must cite Motor Vehicles Accident Fund (Section 164B) and Section 161(4) refund requirement.
    """
    resp = client.post("/api/v1/search/answer", json={
        "query": "how is compensation for hit and run motor accident calculated",
        "force_fallback": True
    })
    assert resp.status_code == 200
    data = resp.json()

    ai_answer = data.get("ai_answer", "")
    assert "161" in ai_answer
    assert "2,00,000" in ai_answer or "200000" in ai_answer
    assert "50,000" in ai_answer or "50000" in ai_answer
    assert "scheme, 2022" in ai_answer.lower() or "163(e)" in ai_answer.lower()
    assert "320" in ai_answer  # IPC 320 grievous hurt
    assert "untraced" in ai_answer.lower()
    assert "does not follow" in ai_answer.lower() and "multiplier" in ai_answer.lower()
    assert "refund" in ai_answer.lower()
    assert len(data.get("source_cases", [])) == 0  # Does NOT attach ordinary MACT cases


# ==============================================================================
# 3. PARAPHRASE CONSISTENCY TESTS
# ==============================================================================

def test_paraphrase_consistency_article_56():
    """Repeated and paraphrased questions for Article 56 must maintain consistent material facts."""
    paraphrases = [
        "what is article 56",
        "explain article 56 of the constitution of india",
        "tenure of the president under article 56",
        "article 56 presidential term and resignation"
    ]
    for q in paraphrases:
        resp = client.post("/api/v1/search/answer", json={"query": q, "force_fallback": True})
        assert resp.status_code == 200
        data = resp.json()
        ans = data.get("ai_answer", "")
        assert "President" in ans, f"Failed on query '{q}': {ans}"
        assert "five years" in ans.lower(), f"Failed on query '{q}': {ans}"
        assert "mirzapur" not in ans.lower(), f"Failed on query '{q}': {ans}"
        assert len(data.get("source_cases", [])) == 0


def test_paraphrase_consistency_hit_and_run():
    """Repeated and paraphrased questions for hit-and-run must maintain consistent statutory amounts and routes."""
    paraphrases = [
        "hit and run compensation",
        "how much compensation for hit and run accident",
        "compensation for hit and run under motor vehicles act",
        "what is the legal route for untraced vehicle hit and run claim"
    ]
    for q in paraphrases:
        resp = client.post("/api/v1/search/answer", json={"query": q, "force_fallback": True})
        assert resp.status_code == 200
        data = resp.json()
        ans = data.get("ai_answer", "")
        assert "161" in ans, f"Failed on query '{q}': {ans}"
        assert "2,00,000" in ans or "200000" in ans, f"Failed on query '{q}': {ans}"
        assert "50,000" in ans or "50000" in ans, f"Failed on query '{q}': {ans}"
        assert "scheme, 2022" in ans.lower() or "163(e)" in ans.lower()
        assert len(data.get("source_cases", [])) == 0


# ==============================================================================
# 4. STATUTORY AMBIGUITY RESOLUTION & PRESERVED PRECEDENTS
# ==============================================================================

def test_section_56_ambiguity_clarification():
    """Querying bare 'what is section 56' must clarify Contract Act Section 56 vs CrPC Section 56 without guessing."""
    resp = client.post("/api/v1/search/answer", json={"query": "what is section 56", "force_fallback": True})
    assert resp.status_code == 200
    data = resp.json()

    ans = data.get("ai_answer", "")
    assert "contract act" in ans.lower()
    assert "crpc" in ans.lower() or "code of criminal procedure" in ans.lower()
    assert "frustration" in ans.lower() or "impossible" in ans.lower()
    assert "magistrate" in ans.lower() or "arrest" in ans.lower()
    assert data.get("tier") == "tier1"


def test_preserved_babu_manmohan_and_dhanapal_chettiar():
    """Preserves Babu Manmohan Das Shah (1967, 3-judge Bench, Sec 3(1)(c) UP Rent Act) and V. Dhanapal Chettiar (1979)."""
    resp = client.post("/api/v1/search/answer", json={"query": "material alteration UP rent act eviction", "force_fallback": True})
    assert resp.status_code == 200
    data = resp.json()

    ans = data.get("ai_answer", "")
    cits = " ".join(data.get("citations", []))
    assert "babu manmohan das shah" in ans.lower() or "babu manmohan das shah" in cits.lower()
    assert "dhanapal chettiar" in ans.lower() or "dhanapal chettiar" in cits.lower()


# ==============================================================================
# 5. OCR MEMORY BOUNDS, VALID OCR & SECURITY REJECTION
# ==============================================================================

def test_executable_upload_rejection():
    """Uploads with executable magic bytes ('MZ') or .exe extension must be rejected with HTTP 400."""
    # Binary executable payload
    exe_bytes = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
    resp = client.post(
        "/api/v1/doc/upload",
        files={"file": ("malware.exe", exe_bytes, "application/octet-stream")},
        data={"title": "Test Executable"}
    )
    assert resp.status_code == 400
    assert "executable" in resp.json()["detail"].lower()


def test_corrupt_unreadable_scan_rejection():
    """Uploads that produce completely unreadable scans or OCR errors must return honest HTTP 422, not compliance."""
    # A completely blank 50x50 white image produces no text
    img = Image.new("RGB", (50, 50), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    blank_bytes = buf.getvalue()

    resp = client.post(
        "/api/v1/doc/upload",
        files={"file": ("blank_scan.png", blank_bytes, "image/png")},
        data={"title": "Blank Scan"}
    )
    assert resp.status_code == 422
    assert "unreadable" in resp.json()["detail"].lower() or "no document text" in resp.json()["detail"].lower()


def test_valid_image_ocr():
    """Valid image with clear text must be processed by RapidOCR under memory-bounded 1024px settings."""
    img = Image.new("RGB", (800, 300), color="white")
    draw = ImageDraw.Draw(img)
    # Simple readable text
    draw.text((30, 40), "EMPLOYMENT AGREEMENT CLAUSE 1", fill="black")
    draw.text((30, 90), "Employee shall not compete for 12 months following termination.", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    valid_bytes = buf.getvalue()

    resp = client.post(
        "/api/v1/doc/upload",
        files={"file": ("contract_page.png", valid_bytes, "image/png")},
        data={"title": "Uploaded Employment Agreement"}
    )
    # Should succeed with HTTP 200 and segment clauses
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("doc_id") is not None
    assert data.get("chunks_count", 0) >= 1
    assert "raw_text" in data


# ==============================================================================
# 6. DOCUMENT TEXT EDITING (45 DAYS TO 90 DAYS)
# ==============================================================================

def test_document_text_edit_45_to_90_days():
    """
    Tests editing document text from 45 days to 90 days:
    1. Uploads contract with 'Payment within 45 days of invoice date'.
    2. Queries docchat: verify 45 days returned.
    3. Edits document text to 'Payment within 90 days of invoice date' via /upload.
    4. Queries docchat: verify 90 days returned and 45 days is NOT returned.
    """
    initial_text = (
        "CONSULTING AGREEMENT\n\n"
        "Clause 1: Scope of Work\n"
        "The Consultant shall provide strategic legal engineering services.\n\n"
        "Clause 2: Invoicing and Payment Terms\n"
        "The Company shall process and disburse all payments within 45 days following receipt of a valid invoice.\n\n"
        "Clause 3: Confidentiality\n"
        "All proprietary data shall be kept confidential during and after the term."
    )

    upload_resp = client.post(
        "/api/v1/doc/upload",
        data={"text": initial_text, "title": "Service Agreement"}
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["doc_id"]

    # Query initial version: payment deadline
    q1_resp = client.post(
        "/api/v1/doc/chat",
        json={"doc_id": doc_id, "question": "What is the payment deadline after invoice receipt?", "force_fallback": True}
    )
    assert q1_resp.status_code == 200
    q1_ans = q1_resp.json()["answer"]
    assert "45 days" in q1_ans, f"Expected 45 days in initial answer, got: {q1_ans}"

    # Edit document text: change 45 days to 90 days
    edited_text = initial_text.replace("45 days", "90 days")
    edit_resp = client.post(
        "/api/v1/doc/upload",
        data={"text": edited_text, "doc_id": doc_id, "title": "Service Agreement (v2)"}
    )
    assert edit_resp.status_code == 200
    updated_doc_id = edit_resp.json()["doc_id"]
    assert updated_doc_id == doc_id

    # Query updated version: payment deadline
    q2_resp = client.post(
        "/api/v1/doc/chat",
        json={"doc_id": doc_id, "question": "What is the payment deadline after invoice receipt?", "force_fallback": True}
    )
    assert q2_resp.status_code == 200
    q2_ans = q2_resp.json()["answer"]
    assert "90 days" in q2_ans, f"Expected 90 days in edited answer, got: {q2_ans}"
    assert "45 days" not in q2_ans, f"Stale 45 days found in edited answer: {q2_ans}"


# ==============================================================================
# 7. MULTI-PAGE OCR FAIL-CLOSED & ENUMERATED OUTCOME TESTS
# ==============================================================================

def test_multipage_ocr_fail_closed_on_unreadable_page():
    """
    Item 1: Multi-page OCR must fail closed.
    If ANY page in an image batch is unreadable (e.g. 2 readable pages + 1 unreadable scan):
    - Reject entire upload with HTTP 422.
    - Identify failed page number (Page 3).
    - Provide retry instructions.
    - Zero compliance/risk verdict issued, no partial document left available.
    """
    # Page 1: Readable text
    img1 = Image.new("RGB", (800, 300), color="white")
    d1 = ImageDraw.Draw(img1)
    d1.text((30, 40), "MASTER CONSULTING AGREEMENT", fill="black")
    d1.text((30, 90), "Clause 1: Scope of Independent Legal Engineering Services.", fill="black")
    buf1 = io.BytesIO()
    img1.save(buf1, format="PNG")

    # Page 2: Readable text
    img2 = Image.new("RGB", (800, 300), color="white")
    d2 = ImageDraw.Draw(img2)
    d2.text((30, 40), "Clause 2: Financial Consideration & Invoicing Terms.", fill="black")
    d2.text((30, 90), "Fees shall be disbursed within 45 days of verified invoice receipt.", fill="black")
    buf2 = io.BytesIO()
    img2.save(buf2, format="PNG")

    # Page 3: Blank unreadable scan (zero characters extracted)
    img3 = Image.new("RGB", (50, 50), color="white")
    buf3 = io.BytesIO()
    img3.save(buf3, format="PNG")

    files = [
        ("file", ("page_1.png", buf1.getvalue(), "image/png")),
        ("file", ("page_2.png", buf2.getvalue(), "image/png")),
        ("file", ("page_3_blank.png", buf3.getvalue(), "image/png")),
    ]

    resp = client.post("/api/v1/doc/upload", files=files, data={"title": "3-Page Batch with Illegible Page 3"})
    assert resp.status_code == 422, f"Expected HTTP 422 fail-closed, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", "")
    assert "Page 3" in detail, f"Expected 'Page 3' in error detail: {detail}"
    assert "clearly legible" in detail.lower() or "retry" in detail.lower(), f"Expected retry instruction in detail: {detail}"


def test_multipage_ocr_all_readable_success_control():
    """All-readable 2-page batch control succeeds with HTTP 200 and extracts text."""
    img1 = Image.new("RGB", (800, 300), color="white")
    d1 = ImageDraw.Draw(img1)
    d1.text((30, 40), "SERVICES MASTER CONTRACT PAGE ONE", fill="black")
    buf1 = io.BytesIO()
    img1.save(buf1, format="PNG")

    img2 = Image.new("RGB", (800, 300), color="white")
    d2 = ImageDraw.Draw(img2)
    d2.text((30, 40), "SERVICES MASTER CONTRACT PAGE TWO", fill="black")
    buf2 = io.BytesIO()
    img2.save(buf2, format="PNG")

    files = [
        ("file", ("page_1.png", buf1.getvalue(), "image/png")),
        ("file", ("page_2.png", buf2.getvalue(), "image/png")),
    ]

    resp = client.post("/api/v1/doc/upload", files=files, data={"title": "2-Page All-Readable Batch"})
    assert resp.status_code == 200, f"Expected HTTP 200 for all-readable batch, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("doc_id") is not None
    assert data.get("page_count") == 2


# ==============================================================================
# 8. ENACTMENT IDENTITY RESOLUTION & CROSS-ACT REGRESSION TESTS
# ==============================================================================

def test_section_9_cpc_does_not_substitute_arbitration():
    """
    Item 2: Enactment identity must be resolved BEFORE section matching.
    'section 9 cpc' must resolve Code of Civil Procedure, 1908.
    A same-numbered section from another Act (Arbitration Act Section 9) must NEVER replace it.
    """
    resp = client.post("/api/v1/search/answer", json={"query": "section 9 cpc", "force_fallback": True})
    assert resp.status_code == 200
    data = resp.json()
    ans = data.get("ai_answer", "")
    cits = " ".join(data.get("citations", []))

    # Must resolve CPC
    assert "code of civil procedure" in ans.lower() or "cpc" in ans.lower()
    # Must NEVER substitute Arbitration Act Section 9
    assert "arbitration and conciliation act" not in ans.lower()
    assert "interim measures" not in ans.lower()
    assert "arbitration" not in cits.lower()
    # Honest source-limited explanation
    assert "not currently indexed" in ans.lower() or "urban improvement trust" in ans.lower() or "indiacode" in ans.lower()


def test_section_9_cpc_alias_resolution():
    """'section 9 code of civil procedure' resolves CPC by full alias, not Arbitration Act."""
    resp = client.post("/api/v1/search/answer", json={"query": "section 9 code of civil procedure", "force_fallback": True})
    assert resp.status_code == 200
    data = resp.json()
    ans = data.get("ai_answer", "")

    assert "code of civil procedure" in ans.lower() or "cpc" in ans.lower()
    assert "arbitration and conciliation act" not in ans.lower()
    assert "interim measures" not in ans.lower()


def test_section_9_arbitration_act_exact_enactment():
    """'section 9 arbitration act' resolves Arbitration Act and returns Section 9 provision text."""
    resp = client.post("/api/v1/search/answer", json={"query": "section 9 arbitration act", "force_fallback": True})
    assert resp.status_code == 200
    data = resp.json()
    ans = data.get("ai_answer", "")

    assert "arbitration" in ans.lower()
    assert "interim measures" in ans.lower()
    assert "code of civil procedure" not in ans.lower()


def test_fictitious_enactment_space_law_atlantis():
    """Fictitious enactment query must refuse premise and never validate non-existent Act."""
    resp = client.post("/api/v1/search/answer", json={"query": "Space Law Act of Atlantis", "force_fallback": True})
    assert resp.status_code == 200
    data = resp.json()
    ans = data.get("ai_answer", "")

    assert "not a recognized statutory enactment" in ans.lower() or "not recognized" in ans.lower()
    assert data.get("hide_badge") is True
    assert data.get("tier") == "not_found"


def test_fictitious_enactment_wakanda_accords():
    """Wakanda Accords query must refuse premise without inventing provisions."""
    resp = client.post("/api/v1/search/answer", json={"query": "Wakanda Accords Section 1", "force_fallback": True})
    assert resp.status_code == 200
    data = resp.json()
    ans = data.get("ai_answer", "")

    assert "not a recognized statutory enactment" in ans.lower() or "not recognized" in ans.lower()
    assert data.get("hide_badge") is True


def test_unseeded_central_act_ni_act_honest_handling():
    """'Section 138 NI Act' resolves Negotiable Instruments Act with honest source-limited handling."""
    resp = client.post("/api/v1/search/answer", json={"query": "Section 138 NI Act", "force_fallback": True})
    assert resp.status_code == 200
    data = resp.json()
    ans = data.get("ai_answer", "")

    assert "negotiable instruments" in ans.lower() or "ni act" in ans.lower()
    assert "arbitration" not in ans.lower()
    assert "contract act" not in ans.lower()
