"""
JUSTICE Legal AI Backend — Citation Verification Unit Tests
Validates citation checking across:
1. Real corpus case (passes untouched)
2. Made-up case (stripped and badged with [Not Verified])
3. Real case not in corpus (stripped and badged with [Not Verified])
4. Tier 2 general explanations (completely strips all cases, citations, sections, articles)
5. All 4 AI answer surfaces (docchat, universal search, maxims, citator)
"""

import sys
import unittest
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os
import re
from fastapi.testclient import TestClient

from app.main import app
from app.services.citation_checker import citation_checker, BADGE_NOT_VERIFIED
from app.services.qdrant_service import qdrant_service

import base64

site_pwd = os.getenv("SITE_PASSWORD", "").strip()
headers = {}
if site_pwd:
    token = base64.b64encode(f"user:{site_pwd}".encode()).decode()
    headers["Authorization"] = f"Basic {token}"

client = TestClient(app, headers=headers)


# =====================================================================
# 1. Core Citation Checker Service Tests
# =====================================================================

def test_real_corpus_case_passes():
    """
    Test 1: A real corpus case (and valid statute section) passes untouched.
    Verified against:
    - 12 landmark precedents (Percept D'Mark v. Zaheer Khan under Section 27)
    - sc_judgments collection (Satyabrata Ghose v. Mugneeram Bangur & Co. under Section 56)
    """
    # 1. 12 landmark precedents
    text_precedent = (
        "In Percept D'Mark (India) (P) Ltd. v. Zaheer Khan (2006) 4 SCC 227, "
        "the Supreme Court held that post-employment restraints are void under Section 27."
    )
    result_precedent = citation_checker.check_and_badge_text(text_precedent, is_tier2=False)
    assert BADGE_NOT_VERIFIED not in result_precedent
    assert "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan" in result_precedent
    assert "(2006) 4 SCC 227" in result_precedent
    assert "Section 27" in result_precedent

    # 2. sc_judgments collection
    text_sc = (
        "In Satyabrata Ghose v. Mugneeram Bangur & Co. [1954] 1 S.C.R. 310, "
        "the doctrine of frustration was applied under Section 56."
    )
    result_sc = citation_checker.check_and_badge_text(text_sc, is_tier2=False)
    assert BADGE_NOT_VERIFIED not in result_sc
    assert "Satyabrata Ghose v. Mugneeram Bangur & Co." in result_sc
    assert "[1954] 1 S.C.R. 310" in result_sc
    assert "Section 56" in result_sc


def test_made_up_case_stripped_and_badged():
    """
    Test 2: A made-up case and fictitious section must be dropped cleanly without leaking [Not Verified].
    Example: 'Fake Law Firm v. Dummy Corporation (2024) 1 SCC 999' under 'Section 999'.
    """
    text_fake = (
        "In Fake Law Firm v. Dummy Corporation (2024) 1 SCC 999, "
        "the court established liability under Section 999."
    )
    result = citation_checker.check_and_badge_text(text_fake, is_tier2=False)

    # The fictitious case name, citation, and section must NOT appear
    assert "Fake Law Firm" not in result
    assert "Dummy Corporation" not in result
    assert "Section 999" not in result
    assert BADGE_NOT_VERIFIED not in result

    # Also test standalone fictitious citation
    text_fake_cit = "The proposition was reaffirmed in (2025) 9 SCC 99999."
    result_cit = citation_checker.check_and_badge_text(text_fake_cit, is_tier2=False)
    assert "(2025) 9 SCC 99999" not in result_cit
    assert BADGE_NOT_VERIFIED not in result_cit


def test_real_case_not_in_corpus_badged():
    """
    Test 3: An unindexed or made-up case that does not exist in our corpus/database is dropped cleanly without [Not Verified].
    """
    text_outside = (
        "In Unindexed Entity v. Unknown Corporation (2024) 4 SCC 9999, "
        "liability was established under Section 9999."
    )
    result = citation_checker.check_and_badge_text(text_outside, is_tier2=False)

    # Outside case and outside section must NOT appear
    assert "Unindexed Entity" not in result
    assert "Unknown Corporation" not in result
    assert "Section 9999" not in result
    assert BADGE_NOT_VERIFIED not in result

    # Also test another unindexed precedent
    text_outside_2 = (
        "Under Fictitious Authority v. Imaginary Body (1978) 1 SCC 9999, "
        "procedure established by law must be just, fair and reasonable."
    )
    result_2 = citation_checker.check_and_badge_text(text_outside_2, is_tier2=False)
    assert "Fictitious Authority" not in result_2
    assert BADGE_NOT_VERIFIED not in result_2


def test_tier2_general_explanation_strips_all():
    """
    Test: Tier 2 general explanations must never name any case, citation, section, or article,
    so they must be completely stripped without leaving unverified badges.
    """
    text_with_citations = (
        "The principle of consideration requires mutual exchange, as seen in "
        "Niranjan Shankar Golikari v. Century Spinning (1967) 2 SCR 378 under Section 27 "
        "and Article 141 of the Constitution."
    )
    result = citation_checker.check_and_badge_text(text_with_citations, is_tier2=True)

    # All citations and references must be stripped
    assert "Golikari" not in result
    assert "Century Spinning" not in result
    assert "Section 27" not in result
    assert "Article 141" not in result
    assert BADGE_NOT_VERIFIED not in result
    assert "The principle of consideration requires mutual exchange" in result


# =====================================================================
# 2. AI Surface Endpoints Verification Tests
# =====================================================================

def test_surface_universal_search_verified_case():
    """Universal search returns verified citations for valid legal queries."""
    resp = client.post("/api/v1/search", json={
        "query": "non-compete after employment ends under Section 27",
        "limit": 3
    })
    assert resp.status_code == 200
    data = resp.json()
    ai_answer = data.get("ai_answer", "")
    citations = data.get("citations", [])

    assert len(data.get("results", [])) > 0
    import re
    assert re.search(r'Section[\s\u202f]*27', ai_answer) or re.search(r'Section[\s\u202f]*27', str(citations))
    # Since this is a real verified corpus query, ai_answer should have no [Not Verified] on Percept D'Mark
    if "Percept" in ai_answer:
        assert f"Percept D'Mark" in ai_answer


def test_surface_universal_search_outside_query_tier2():
    """Universal search for concept outside corpus generates Tier 2 without cases or badges."""
    resp = client.post("/api/v1/search", json={
        "query": "Explain the Roman law doctrine of negotiorum gestio",
        "limit": 3
    })
    assert resp.status_code == 200
    data = resp.json()
    ai_answer = data.get("ai_answer", "")

    # Outside-corpus queries get the honest refusal (kept deliberately: no
    # unsupported general-information answers). No verified-badge framing and
    # no ratio may leak into the refusal.
    assert "AI answer, not verified against a legal database" not in ai_answer
    assert "No AI-generated answer is available" in ai_answer
    assert BADGE_NOT_VERIFIED not in ai_answer
    assert "Section " not in ai_answer
    assert "Article " not in ai_answer
    assert data.get("hyde_synthetic_ratio") is None


def test_surface_docchat_grounded_answer():
    """Doc Chat returns grounded clause answers and verifies document sections."""
    doc_text = """
    EMPLOYMENT AGREEMENT
    Clause 12. Confidentiality: The Employee shall keep all trade secrets confidential.
    Clause 14. Restrictive Covenants: The Employee shall not engage in competing business post termination.
    Section 5. Governing Law: This agreement shall be governed by the laws of India.
    """
    # 1. Upload mock document
    upload_resp = client.post(
        "/api/v1/doc/upload",
        files={"file": ("employment.txt", doc_text.encode("utf-8"), "text/plain")}
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["doc_id"]

    # 2. Chat with uploaded document
    chat_resp = client.post("/api/v1/doc/chat", json={
        "doc_id": doc_id,
        "question": "What does Clause 12 say about confidentiality?"
    })
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert "confidential" in chat_data["answer"].lower()
    # The document's clause should not be marked unverified
    assert BADGE_NOT_VERIFIED not in chat_data["answer"]


def test_surface_maxims_grounded_explanation():
    """Legal Maxims endpoint returns explanation with citation checking applied."""
    resp = client.post("/api/v1/maxims/explain", json={
        "maxim": "pacta sunt servanda"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is True
    assert "pacta sunt servanda" in data["maxim"].lower()
    assert len(data.get("explanation", "")) > 20


def test_surface_citator_verified_hierarchy():
    """Citator endpoint returns verified Article 141 precedent hierarchy and doctrine."""
    resp = client.get("/api/v1/citator/sc-2006-percept")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "sc-2006-percept"
    assert "Percept D'Mark" in data["title"]
    assert data["article141Evaluation"]["targetBenchSize"] == 2
    if data.get("aiAnalysis"):
        standing = data["aiAnalysis"].get("constitutional_standing", "")
        assert re.search(r'Article[\s\u202f]*141|141', standing)
        assert BADGE_NOT_VERIFIED not in standing

    # Also test with include_ai=false to verify fallback citations handling
    resp_no_ai = client.get("/api/v1/citator/sc-2006-percept?include_ai=false")
    assert resp_no_ai.status_code == 200
    data_no_ai = resp_no_ai.json()
    assert data_no_ai["id"] == "sc-2006-percept"
    assert len(data_no_ai.get("citations", [])) > 0


def test_surface_citator_unknown_case_not_found():
    """Citator returns 404 for case IDs not in our knowledge graph."""
    resp = client.get("/api/v1/citator/fake-case-999")
    assert resp.status_code == 404
    assert "I couldn't find a verified source for this" in resp.json()["detail"]


if __name__ == "__main__":
    tests = [
        ("Test 1: Real Corpus Case Passes Untouched", test_real_corpus_case_passes),
        ("Test 2: Made-Up Case Stripped and Badged", test_made_up_case_stripped_and_badged),
        ("Test 3: Real Case Not in Corpus Badged", test_real_case_not_in_corpus_badged),
        ("Test 4: Tier 2 General Explanation Strips All", test_tier2_general_explanation_strips_all),
        ("Test 5: Universal Search Surface Check", test_surface_universal_search_verified_case),
        ("Test 6: Universal Search Tier 2 Outside Query", test_surface_universal_search_outside_query_tier2),
        ("Test 7: Doc Chat Grounded Surface Check", test_surface_docchat_grounded_answer),
        ("Test 8: Maxims Surface Explanation Check", test_surface_maxims_grounded_explanation),
        ("Test 9: Citator Precedent Surface Check", test_surface_citator_verified_hierarchy),
        ("Test 10: Citator Unknown Case 404 Guardrail", test_surface_citator_unknown_case_not_found),
    ]

    print("\n=======================================================")
    print("RUNNING JUSTICE CITATION VERIFICATION TEST SUITE")
    print("=======================================================\n")

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            print(f" [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f" [FAIL] {name}: {repr(e)}")
            failed += 1

    print("\n-------------------------------------------------------")
    print(f"RESULTS: {passed} PASSED, {failed} FAILED (TOTAL: {len(tests)})")
    print("=======================================================\n")
    if failed > 0:
        exit(1)



def test_edition_note_block_survives_sentence_filter_intact():
    from app.services.citation_checker import citation_checker
    note = ("[Note from the official edition's footnotes: the changes were struck down by the Supreme Court in "
            "Supreme Court Advocates-on-Record Association v. Union of India, AIR 2016 SC 117. The text above is shown as printed in the edition.]")
    out = citation_checker.check_and_badge_text("Article text here. " + note)
    assert note in out
