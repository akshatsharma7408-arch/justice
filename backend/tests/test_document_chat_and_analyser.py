"""
JUSTICE Legal AI Backend — Document Chat and Analyser Regression Test Suite (Item 9)
Validates:
1. Document Chat answers with clause content, not only the heading.
   "What is the notice period?" returns the clause sentence ("Either party may terminate by giving 60 days notice"),
   plus a one-line plain explanation grounded in that clause.
2. "Who are the parties?" reads the preamble (first clause).
3. Questions not covered return "The document does not mention this.", never "AI service unavailable".
4. Contract audit flags penalty / fixed damages "regardless of actual loss" as Section 74 (severity WARNING, not void).
5. Post-employment non-compete is flagged as Section 27 (severity VOID_AB_INITIO, void).
"""

import sys
import os
import re
import base64
from pathlib import Path

# Ensure backend directory is in python path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app

site_pwd = os.getenv("SITE_PASSWORD", "").strip()
headers = {}
if site_pwd:
    token = base64.b64encode(f"user:{site_pwd}".encode()).decode()
    headers["Authorization"] = f"Basic {token}"

client = TestClient(app, headers=headers)

SAMPLE_SERVICE_AGREEMENT = """MASTER SERVICE AND CONSULTANCY AGREEMENT
This Agreement is entered into on January 1, 2024 between Alpha Technologies Private Limited ("Company") and Rahul Sharma ("Consultant").

Clause 1. Engagement & Deliverables
The Consultant is engaged to provide software architectural consulting services for a fixed tenure of 12 months.

Clause 2. Liquidated Damages as Penalty
In the event of delay or default, the Consultant shall pay fixed damages of INR 5,00,000 regardless of actual loss.

Clause 3. Notice of Termination
Either party may terminate this agreement by giving 60 days notice in writing to the other party.

Clause 4. Post-Termination Non-Compete
The Consultant agrees that for a period of twenty-four (24) months following termination of this Agreement, the Consultant shall not directly or indirectly engage in or consult for any competing business anywhere in India.

Clause 5. Governing Law & Jurisdiction
This Agreement shall be governed by the laws of India and subject to the exclusive jurisdiction of courts in New Delhi.
"""


def test_docchat_notice_period_returns_sentence_not_just_heading():
    """Item 9 Test 1: Notice period returns clause sentence and plain explanation, not only 'Notice.'"""
    upload_resp = client.post(
        "/api/v1/doc/upload",
        files={"file": ("service_agreement.txt", SAMPLE_SERVICE_AGREEMENT.encode("utf-8"), "text/plain")}
    )
    assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
    doc_id = upload_resp.json()["doc_id"]

    chat_resp = client.post(
        "/api/v1/doc/chat",
        json={"doc_id": doc_id, "question": "What is the notice period?"}
    )
    assert chat_resp.status_code == 200, f"Chat failed: {chat_resp.text}"
    data = chat_resp.json()
    ans = data["answer"]
    cits = data.get("citations", [])

    # Must contain the substantive clause sentence
    assert "60 days notice" in ans.lower() or "terminate" in ans.lower(), f"Answer must include clause sentence: {ans}"
    # Must NOT just return the heading "Notice." as the quote
    assert ans.strip().lower() != 'the document stipulates: "notice."', f"Answer must not only be heading: {ans}"
    assert 'stipulates: "notice."' not in ans.lower(), f"Answer must not be trivial header: {ans}"
    # Must have a plain explanation
    assert len(ans.split()) >= 10, f"Answer must include clause sentence and plain explanation: {ans}"
    # Citations must quote the substantive sentence
    assert len(cits) > 0, "Expected at least one citation"
    assert "notice" in cits[0]["quoted_text"].lower() and len(cits[0]["quoted_text"].split()) >= 4, (
        f"Citation quoted text must be substantive clause sentence: {cits[0]['quoted_text']}"
    )


def test_docchat_parties_reads_preamble():
    """Item 9 Test 2: 'Who are the parties?' must read the preamble (first clause)."""
    upload_resp = client.post(
        "/api/v1/doc/upload",
        files={"file": ("service_agreement.txt", SAMPLE_SERVICE_AGREEMENT.encode("utf-8"), "text/plain")}
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["doc_id"]

    chat_resp = client.post(
        "/api/v1/doc/chat",
        json={"doc_id": doc_id, "question": "Who are the parties?"}
    )
    assert chat_resp.status_code == 200
    data = chat_resp.json()
    ans = data["answer"].lower()

    # Must identify the parties from the preamble
    assert "alpha technologies" in ans, f"Answer must identify Company from preamble: {ans}"
    assert "rahul sharma" in ans, f"Answer must identify Consultant from preamble: {ans}"
    assert len(data.get("citations", [])) > 0, "Expected citation to preamble"


def test_docchat_uncovered_question_returns_document_does_not_mention_this():
    """Item 9 Test 3: Questions not covered must answer 'The document does not mention this.' never 'AI service unavailable'."""
    upload_resp = client.post(
        "/api/v1/doc/upload",
        files={"file": ("service_agreement.txt", SAMPLE_SERVICE_AGREEMENT.encode("utf-8"), "text/plain")}
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["doc_id"]

    chat_resp = client.post(
        "/api/v1/doc/chat",
        json={"doc_id": doc_id, "question": "What is the policy on maternity leave and childcare allowances?"}
    )
    assert chat_resp.status_code == 200
    data = chat_resp.json()
    ans = data["answer"]

    # Must answer "The document does not mention this."
    assert "the document does not mention this" in ans.lower(), f"Expected 'The document does not mention this.' but got: {ans}"
    # Must NOT mention 'AI service is currently unavailable'
    assert "ai service is currently unavailable" not in ans.lower()
    assert "ai service unavailable" not in ans.lower()
    assert data["citations"] == []


def test_contract_audit_flags_section_74_as_warning_not_void():
    """Item 9 Test 4: Section 74 'regardless of actual loss' is flagged as WARNING (not void), non-compete is void under Section 27."""
    audit_resp = client.post(
        "/api/v1/audit/contract",
        json={"text": SAMPLE_SERVICE_AGREEMENT, "title": "Sample Service Agreement"}
    )
    assert audit_resp.status_code == 200, f"Audit failed: {audit_resp.text}"
    data = audit_resp.json()
    clauses = data["clauses"]

    # Find the liquidated damages clause (Clause 2)
    s74_clause = next(
        (c for c in clauses if "liquidated damages" in c["title"].lower() or "regardless of actual loss" in c["original_text"].lower()),
        None
    )
    assert s74_clause is not None, "Expected Liquidated Damages clause in audit results"
    assert s74_clause["severity"] == "WARNING", f"Section 74 severity must be WARNING, got {s74_clause['severity']}"
    assert s74_clause["is_violation"] is False, f"Section 74 must not be flagged as void violation, got {s74_clause['is_violation']}"
    assert "74" in (s74_clause["statutory_violation"] or ""), f"Must reference Section 74: {s74_clause['statutory_violation']}"

    # Find the post-termination non-compete clause (Clause 4)
    s27_clause = next(
        (c for c in clauses if "non-compete" in c["title"].lower() or "competing business" in c["original_text"].lower()),
        None
    )
    assert s27_clause is not None, "Expected Non-Compete clause in audit results"
    assert s27_clause["severity"] == "VOID_AB_INITIO", f"Section 27 severity must be VOID_AB_INITIO, got {s27_clause['severity']}"
    assert s27_clause["is_violation"] is True, "Section 27 non-compete must be flagged as void violation"
    assert "27" in (s27_clause["statutory_violation"] or ""), f"Must reference Section 27: {s27_clause['statutory_violation']}"

    # Check total void count (only Section 27 is void, Section 74 is warning not void)
    assert data["void_clauses_count"] == 1, f"Expected exactly 1 void clause (Section 27), got {data['void_clauses_count']}"


def test_verify_single_clause_section74_and_section27():
    """Item 9 Test 5: Verify single clause endpoint handles Section 74 warning and Section 27 void."""
    # Test Section 74
    s74_resp = client.post(
        "/api/v1/audit/verify-clause",
        json={
            "clause_text": "In the event of delay, Consultant shall pay fixed damages of INR 5,00,000 regardless of actual loss.",
            "clause_title": "Damages for Delay"
        }
    )
    assert s74_resp.status_code == 200
    s74_data = s74_resp.json()
    assert s74_data["section"] == "74"
    assert s74_data["severity"] == "WARNING"
    assert s74_data["status"] == "WARNING"
    assert s74_data["is_violation"] is False
    assert "kailash nath" in s74_data["binding_precedent"].lower()

    # Test Section 27
    s27_resp = client.post(
        "/api/v1/audit/verify-clause",
        json={
            "clause_text": "For two years following termination of employment, Consultant shall not engage in any competing business.",
            "clause_title": "Restrictive Covenant"
        }
    )
    assert s27_resp.status_code == 200
    s27_data = s27_resp.json()
    assert s27_data["section"] == "27"
    assert s27_data["severity"] == "VOID_AB_INITIO"
    assert s27_data["is_violation"] is True
    assert "percept" in s27_data["binding_precedent"].lower()


def test_upload_raw_text_and_clause_audit():
    """Item 9 Test 6: Verify /api/v1/doc/upload supports direct raw text and triggers compliance evaluation."""
    resp = client.post(
        "/api/v1/doc/upload",
        data={"raw_text": SAMPLE_SERVICE_AGREEMENT, "title": "Direct Raw Text Agreement"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_id"]
    assert "Rahul Sharma" in (data.get("raw_text") or "")
    assert "clauses" in data
    assert len(data["clauses"]) >= 4


def test_upload_images_blank_blurry_detection():
    """Item 9 Test 7: Verify /api/v1/doc/upload-images detects blank/blurry images and provides user guidance."""
    import io
    from PIL import Image

    # Create a small blank image (no readable text)
    blank_img = Image.new("RGB", (200, 200), color="white")
    buf = io.BytesIO()
    blank_img.save(buf, format="PNG")
    buf.seek(0)

    resp = client.post(
        "/api/v1/doc/upload-images",
        files=[("files", ("blank_photo.png", buf.getvalue(), "image/png"))]
    )
    assert resp.status_code == 422
    detail = resp.json().get("detail", "")
    assert "unreadable" in detail.lower() or "blurry" in detail.lower() or "ocr" in detail.lower()


def test_upload_images_with_drawn_text_ocr():
    """Item 9 Test 8: Verify RapidOCR extracts text from rendered images."""
    import io
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (800, 300), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 80), "TENANCY AGREEMENT: Notice period is 45 days.", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    resp = client.post(
        "/api/v1/doc/upload-images",
        files=[("files", ("page_1.png", buf.getvalue(), "image/png"))]
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "doc_id" in data
def test_upload_oversized_file_rejected():
    """Verify upload of file > 10MB returns 400."""
    fake_huge_bytes = b"x" * (10 * 1024 * 1024 + 1024)
    resp = client.post(
        "/api/v1/doc/upload",
        files={"file": ("huge_contract.pdf", fake_huge_bytes, "application/pdf")}
    )
    assert resp.status_code == 400
    assert "exceeds 10MB limit" in resp.json()["detail"]


def test_upload_too_many_files_rejected():
    """Verify upload of > 10 files returns 400."""
    files = [("files", (f"page_{i}.png", b"fake image content", "image/png")) for i in range(12)]
    resp = client.post(
        "/api/v1/doc/upload",
        files=files
    )
    assert resp.status_code == 400
    assert "Maximum 10 files allowed" in resp.json()["detail"]


def test_multi_image_order_preservation():
    """Verify multi-image uploads preserve page ordering (Page 1 before Page 2)."""
    import io
    from PIL import Image, ImageDraw

    img1 = Image.new("RGB", (600, 200), color="white")
    draw1 = ImageDraw.Draw(img1)
    draw1.text((30, 50), "Clause 1. First Page of Master Agreement", fill="black")
    buf1 = io.BytesIO()
    img1.save(buf1, format="PNG")

    img2 = Image.new("RGB", (600, 200), color="white")
    draw2 = ImageDraw.Draw(img2)
    draw2.text((30, 50), "Clause 2. Second Page of Master Agreement", fill="black")
    buf2 = io.BytesIO()
    img2.save(buf2, format="JPEG")

    resp = client.post(
        "/api/v1/doc/upload",
        files=[
            ("files", ("page_01.png", buf1.getvalue(), "image/png")),
            ("files", ("page_02.jpg", buf2.getvalue(), "image/jpeg"))
        ]
    )
    assert resp.status_code == 200
    data = resp.json()
    raw = data.get("raw_text") or ""
    # Check that Page 1 appears before Page 2
    pos1 = raw.find("--- Page 1")
    pos2 = raw.find("--- Page 2")
    assert pos1 != -1 and pos2 != -1, f"Expected page separators, got: {raw}"
    assert pos1 < pos2, "Expected Page 1 to appear before Page 2"


def test_format_decoding_webp():
    """Verify WEBP image format decoding and extraction."""
    import io
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (600, 200), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((30, 50), "WEBP FORMAT CLAUSE: All disputes in Delhi.", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="WEBP")

    resp = client.post(
        "/api/v1/doc/upload",
        files=[("files", ("contract.webp", buf.getvalue(), "image/webp"))]
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "doc_id" in data


def test_edited_text_reprocesses_same_doc_id():
    """Verify editing extracted text re-runs clause audit under the same doc_id."""
    initial_text = (
        "Clause 1. Post-Termination Non-Compete\n"
        "The Consultant agrees that for 24 months following termination of this Agreement, the Consultant shall not directly or indirectly engage in or consult for any competing business anywhere in India."
    )
    resp1 = client.post("/api/v1/doc/upload", data={"raw_text": initial_text})
    assert resp1.status_code == 200
    doc_id = resp1.json()["doc_id"]
    audit1 = resp1.json().get("audit_results", {})
    assert audit1.get("void_clauses_count", 0) >= 1

    # Now edit to remove the non-compete restraint
    edited_text = (
        "Clause 1. Permitted Future Engagement\n"
        "The Consultant is free to engage in or consult for any business or employer upon termination of this Agreement."
    )
    resp2 = client.post("/api/v1/doc/upload", data={"raw_text": edited_text, "doc_id": doc_id})
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["doc_id"] == doc_id
    audit2 = data2.get("audit_results", {})
    # Void count should now be 0
    assert audit2.get("void_clauses_count", 0) == 0

