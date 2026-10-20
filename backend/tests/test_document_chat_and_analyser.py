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
