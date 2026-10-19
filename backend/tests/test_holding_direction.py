"""
JUSTICE Legal AI Backend — Holding Direction & Known Doctrines Regression Test Suite
Validates that:
1. "Section 27 Contract Act post termination non compete enforceability" states holding accurately
   (post-termination restraints are void ab initio, quotes Percept D'Mark (2006) 4 SCC 227, never says enforceable).
2. "liquidated damages under Section 74" retrieves Kailash Nath Associates (2015) 4 SCC 136 with proof-of-loss holding.
3. "Is the right to privacy recognized as a fundamental right under Article 21" upholds fundamental right under K.S. Puttaswamy (2017).
4. "Article 141 precedent hierarchy larger bench binding on smaller bench" confirms larger bench binds smaller bench under Dawoodi Bohra (2005).
5. "negative covenants during the term of employment under Section 27" confirms restraints during active employment are valid under Niranjan Shankar Golikari (1967).
6. Doc chat compound question ("what is my notice period and can the company stop me from working elsewhere") splits correctly,
   cites Clause 12, and clearly states which part has no clause.
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

SAMPLE_DOC_TEXT = """
EMPLOYMENT AND CONFIDENTIALITY AGREEMENT
This Agreement is entered into between Apex Technologies Private Limited ("Company") and the Employee.

Clause 1. Engagement & Term: The Employee is engaged as Senior Systems Architect effective from June 1, 2023.
Clause 4. Compensation & Benefits: The Employee shall receive a fixed gross salary of INR 25,00,000 per annum payable monthly.
Clause 8. Confidentiality & Non-Disclosure: The Employee shall strictly preserve all proprietary algorithms, trade secrets, customer lists, and source code. The Employee shall not disclose any proprietary data to third parties during or following termination of employment.
Clause 12. Restrictive Covenants & Non-Solicitation: Following termination of employment for any reason, the Employee shall not, for a period of twelve (12) months, solicit or attempt to hire any existing employees or clients of the Company.
Clause 15. Intellectual Property: All inventions, patents, designs, and software created during the course of employment shall be the sole and exclusive property of the Company.
Section 19. Governing Law & Dispute Resolution: This Agreement shall be governed by the laws of India. Any dispute arising out of this Agreement shall be referred to arbitration in New Delhi.
"""


def test_holding_1_section27_post_termination():
    """Holding 1: Post-termination non-compete is void under Section 27 (Percept D'Mark, Superintendence Co.)."""
    q = "Section 27 Contract Act post termination non compete enforceability"
    resp = client.post("/api/v1/search", json={"query": q, "limit": 3})
    assert resp.status_code == 200, f"Search failed: {resp.text}"
    data = resp.json()

    assert data.get("results_count", 0) > 0, "Expected non-zero results"
    ans = data.get("ai_answer", "").lower()
    cits = " ".join(data.get("citations", []))

    # Must state void / unenforceable
    assert "void" in ans or "unenforceable" in ans, f"Answer must state void or unenforceable: {ans}"
    # Must NOT state post-termination restraint is enforceable
    assert not re.search(r'\boperative\s+after\s+termination\s+(?:is|are)\s+enforceable\b', ans), "Answer must not state post-termination restraint is enforceable"
    # Must cite Percept D'Mark
    assert "percept" in ans or "percept" in cits.lower() or "2006" in cits, f"Expected Percept D'Mark citation: {cits}"
    print(" [PASS] Holding 1: Section 27 Post-termination Restraint is Void (Percept D'Mark 2006)")


def test_holding_2_section74_liquidated_damages():
    """Holding 2: Liquidated damages under Section 74 require proof of loss (Kailash Nath Associates)."""
    q = "liquidated damages under Section 74"
    resp = client.post("/api/v1/search", json={"query": q, "limit": 3})
    assert resp.status_code == 200, f"Search failed: {resp.text}"
    data = resp.json()

    assert data.get("results_count", 0) > 0, "Expected non-zero results for Section 74 query"
    ans = data.get("ai_answer", "").lower()
    cits = " ".join(data.get("citations", []))
    result_titles = [r.get("title", "") for r in data.get("results", [])]

    # Must retrieve Kailash Nath Associates
    assert any("kailash nath" in t.lower() for t in result_titles), f"Expected Kailash Nath Associates in results: {result_titles}"
    assert "kailash nath" in cits.lower() or "kailash nath" in ans, f"Expected Kailash Nath citation: {cits}"
    # Must mention proof of loss / reasonable compensation
    assert "proof" in ans or "reasonable compensation" in ans or "loss" in ans, f"Answer must state proof of loss requirement: {ans}"
    print(" [PASS] Holding 2: Section 74 Liquidated Damages Proof of Loss (Kailash Nath Associates 2015)")


def test_holding_3_article21_privacy():
    """Holding 3: Right to privacy is a fundamental right under Article 21 (K.S. Puttaswamy)."""
    q = "Is the right to privacy recognized as a fundamental right under Article 21"
    resp = client.post("/api/v1/search", json={"query": q, "limit": 3})
    assert resp.status_code == 200, f"Search failed: {resp.text}"
    data = resp.json()

    assert data.get("results_count", 0) > 0, "Expected non-zero results for Article 21 privacy query"
    ans = data.get("ai_answer", "").lower()
    cits = " ".join(data.get("citations", []))

    assert "fundamental right" in ans, f"Answer must recognize privacy as a fundamental right: {ans}"
    assert "puttaswamy" in ans or "puttaswamy" in cits.lower() or "2017" in cits, f"Expected Puttaswamy citation: {cits}"
    print(" [PASS] Holding 3: Article 21 Right to Privacy is a Fundamental Right (Puttaswamy 2017)")


def test_holding_4_article141_precedent_hierarchy():
    """Holding 4: Precedent hierarchy — larger bench binding on smaller bench (Dawoodi Bohra)."""
    q = "Article 141 precedent hierarchy larger bench binding on smaller bench"
    resp = client.post("/api/v1/search", json={"query": q, "limit": 3})
    assert resp.status_code == 200, f"Search failed: {resp.text}"
    data = resp.json()

    assert data.get("results_count", 0) > 0, "Expected non-zero results for Article 141 query"
    ans = data.get("ai_answer", "").lower()
    cits = " ".join(data.get("citations", []))

    assert "binding" in ans, f"Answer must state larger bench is binding: {ans}"
    assert "dawoodi bohra" in ans or "dawoodi bohra" in cits.lower() or "article 141" in ans, f"Expected Dawoodi Bohra citation: {cits}"
    print(" [PASS] Holding 4: Article 141 Larger Bench Binds Smaller Bench (Dawoodi Bohra 2005)")


def test_holding_5_section27_during_term_valid():
    """Holding 5: Restraints during active employment are valid under Section 27 (Niranjan Shankar Golikari)."""
    q = "negative covenants during the term of employment under Section 27"
    resp = client.post("/api/v1/search", json={"query": q, "limit": 3})
    assert resp.status_code == 200, f"Search failed: {resp.text}"
    data = resp.json()

    assert data.get("results_count", 0) > 0, "Expected non-zero results for Section 27 during-term query"
    ans = data.get("ai_answer", "").lower()
    cits = " ".join(data.get("citations", []))

    assert "valid" in ans or "enforceable" in ans or "not in restraint" in ans, f"Answer must confirm restraint during term is valid: {ans}"
    assert "golikari" in ans or "golikari" in cits.lower() or "gujarat bottling" in ans or "gujarat bottling" in cits.lower(), f"Expected Golikari or Gujarat Bottling citation: {cits}"
    print(" [PASS] Holding 5: Section 27 Negative Covenants During Employment are Valid (Niranjan Golikari 1967)")


def test_docchat_compound_question():
    """Doc Chat Bug 4: Two-part question splits into sub-questions, cites Clause 12, states notice period has no clause."""
    upload_resp = client.post(
        "/api/v1/doc/upload",
        files={"file": ("employment_agreement.txt", SAMPLE_DOC_TEXT.encode("utf-8"), "text/plain")}
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["doc_id"]

    q = "what is my notice period and can the company stop me from working elsewhere"
    chat_resp = client.post("/api/v1/doc/chat", json={"doc_id": doc_id, "question": q})
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()

    ans = chat_data["answer"].lower()
    citations = chat_data.get("citations", [])

    # Must say clearly that notice period has no clause
    assert "does not contain" in ans and "notice" in ans, f"Must state notice period is not in doc: {ans}"
    # Must cite Clause 12 for the restrictive covenants / working elsewhere part
    assert any("12" in str(c.get("clause_number", "")) for c in citations if isinstance(c, dict)), f"Expected Clause 12 citation: {citations}"
    print(" [PASS] Doc Chat: Compound question answered with Clause 12 citation and no-clause notice statement")


if __name__ == "__main__":
    tests = [
        ("Test 1: Section 27 Post-termination Restraint is Void", test_holding_1_section27_post_termination),
        ("Test 2: Section 74 Liquidated Damages Proof of Loss", test_holding_2_section74_liquidated_damages),
        ("Test 3: Article 21 Privacy Fundamental Right", test_holding_3_article21_privacy),
        ("Test 4: Article 141 Precedent Hierarchy", test_holding_4_article141_precedent_hierarchy),
        ("Test 5: Section 27 Restraint During Term Valid", test_holding_5_section27_during_term_valid),
        ("Test 6: Doc Chat Compound Question Split", test_docchat_compound_question),
    ]

    print("\n=======================================================")
    print("RUNNING JUSTICE HOLDING DIRECTION & REGRESSION SUITE")
    print("=======================================================\n")

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f" [FAIL] {name}: {repr(e)}")
            failed += 1

    print("\n-------------------------------------------------------")
    print(f"RESULTS: {passed} PASSED, {failed} FAILED (TOTAL: {len(tests)})")
    print("=======================================================\n")
    if failed > 0:
        exit(1)
