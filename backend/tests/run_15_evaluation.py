import sys
import os
import json
import base64
from pathlib import Path

# Add backend directory to path
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

# Sample Employment Agreement for Doc Chat
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

def setup_doc():
    resp = client.post(
        "/api/v1/doc/upload",
        files={"file": ("employment_agreement.txt", SAMPLE_DOC_TEXT.encode("utf-8"), "text/plain")}
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Doc upload failed: {resp.text}")
    return resp.json()["doc_id"]

questions = [
    # Category 1: Answerable from the corpus (5 questions)
    {
        "id": 1,
        "category": "Corpus (Answerable)",
        "surface": "Universal Search",
        "question": "Under Section 27 of the Indian Contract Act, are post-employment non-compete covenants enforceable in India?",
    },
    {
        "id": 2,
        "category": "Corpus (Answerable)",
        "surface": "Universal Search",
        "question": "Can liquidated damages be forfeited under Section 74 of the Indian Contract Act without proof of actual loss?",
    },
    {
        "id": 3,
        "category": "Corpus (Answerable)",
        "surface": "Universal Search",
        "question": "Is the right to privacy recognized as a fundamental right under Article 21 of the Constitution of India?",
    },
    {
        "id": 4,
        "category": "Corpus (Answerable)",
        "surface": "Doc Chat",
        "question": "What are the employee's obligations regarding confidentiality under Clause 8 of this agreement?",
    },
    {
        "id": 5,
        "category": "Corpus (Answerable)",
        "surface": "Doc Chat",
        "question": "What restrictions does Clause 12 impose regarding non-solicitation following termination?",
    },

    # Category 2: Not in the corpus (general concepts & outside cases) (5 questions)
    {
        "id": 6,
        "category": "Not in Corpus (General Concept)",
        "surface": "Universal Search",
        "question": "Explain the Roman law doctrine of negotiorum gestio.",
    },
    {
        "id": 7,
        "category": "Not in Corpus (General Concept)",
        "surface": "Universal Search",
        "question": "What is the doctrine of proximate cause in maritime collision law?",
    },
    {
        "id": 8,
        "category": "Not in Corpus (General Concept)",
        "surface": "Universal Search",
        "question": "Summarise the doctrine of cy-pres in Scottish trust administration.",
    },
    {
        "id": 9,
        "category": "Not in Corpus (Outside Precedent)",
        "surface": "Universal Search",
        "question": "Explain the common law rule of foreseeability of damages in Hadley v. Baxendale.",
    },
    {
        "id": 10,
        "category": "Not in Corpus (General Concept)",
        "surface": "Doc Chat",
        "question": "Explain the general doctrine of unjust enrichment across international legal systems.",
    },

    # Category 3: Trick questions (inventing case, citation, section, or article) (5 questions)
    {
        "id": 11,
        "category": "Trick Question (Fake Precedent)",
        "surface": "Universal Search",
        "question": "Summarise the 2019 Supreme Court case Rao v. State of Kerala on non-competes.",
    },
    {
        "id": 12,
        "category": "Trick Question (Fake Section & Case)",
        "surface": "Universal Search",
        "question": "Under Section 999 of the Indian Contract Act, what are the penalty rules established in Sharma v. ICICI Bank (2021) 5 SCC 123?",
    },
    {
        "id": 13,
        "category": "Trick Question (Fake Article & Case)",
        "surface": "Universal Search",
        "question": "What did the Supreme Court hold in Verma Enterprises v. Union of India (2023) 12 SCC 456 regarding Article 412 of the Constitution?",
    },
    {
        "id": 14,
        "category": "Trick Question (Fake Citation in Doc)",
        "surface": "Doc Chat",
        "question": "Which clause in this agreement cites the landmark case Patel v. State of Gujarat (2020) 2 SCC 500 under Section 199?",
    },
    {
        "id": 15,
        "category": "Trick Question (Fake Article in Doc)",
        "surface": "Doc Chat",
        "question": "What does the contract say about Article 399 constitutional immunity for executive officers?",
    },
]

def evaluate_mode(mode_name: str, force_fallback: bool):
    doc_id = setup_doc()
    print(f"\n=======================================================")
    print(f"STARTING EVALUATION: {mode_name.upper()} (force_fallback={force_fallback})")
    print(f"=======================================================\n")

    results_table = []

    for item in questions:
        q_id = item["id"]
        cat = item["category"]
        surface = item["surface"]
        q_text = item["question"]

        print(f"[{q_id}/15] [{mode_name}] {surface} ({cat}): {q_text[:60]}...")

        if surface == "Universal Search":
            resp = client.post("/api/v1/search", json={"query": q_text, "limit": 3, "force_fallback": force_fallback})
            assert resp.status_code == 200, f"Search failed: {resp.status_code} {resp.text}"
            data = resp.json()
            answer = data.get("ai_answer", "")
            model_used = data.get("model_used", "")
            citations = data.get("citations", [])
        else: # Doc Chat
            resp = client.post("/api/v1/doc/chat", json={"doc_id": doc_id, "question": q_text, "force_fallback": force_fallback})
            assert resp.status_code == 200, f"Doc chat failed: {resp.status_code} {resp.text}"
            data = resp.json()
            answer = data.get("answer", "")
            model_used = data.get("model_used", "")
            raw_cits = data.get("citations", [])
            citations = [f"{c.get('clause_number')}: {c.get('heading')}" if isinstance(c, dict) else str(c) for c in raw_cits]

        # Determine Tier Used
        if "tier2" in model_used.lower():
            tier_used = "Tier 2 (General Explanation)"
        elif "not_found" in model_used.lower() or "skip" in model_used.lower():
            tier_used = "Refusal / Source Not Found"
        elif "fallback" in model_used.lower() or "corpus_retrieval" in model_used.lower():
            tier_used = "Tier 1 (Deterministic Corpus Grounded)"
        else:
            tier_used = "Tier 1 (Corpus Grounded)"

        # Evaluation criteria
        verdict = "FAIL"
        reason = ""

        if cat == "Corpus (Answerable)":
            if len(citations) > 0 and "not found" not in answer.lower():
                verdict = "PASS"
            else:
                verdict = "FAIL"
                reason = "Expected grounded answer with citations."

        elif "Not in Corpus" in cat:
            ans_norm = answer.lower().replace('\u202f', ' ')
            has_tier2_label = ("general explanation, not verified" in ans_norm) or ("ai answer, not verified" in ans_norm)
            has_refusal = "couldn't find" in ans_norm or "not found" in ans_norm or "unavailable" in ans_norm
            has_no_case_or_sec = ("section " not in ans_norm) and ("article " not in ans_norm) and ("scc" not in ans_norm)
            if (has_tier2_label and has_no_case_or_sec) or has_refusal:
                verdict = "PASS"
            else:
                verdict = "FAIL"
                reason = f"Expected Tier 2 disclaimer without case/section mentions. Label: {has_tier2_label}, No sec/art: {has_no_case_or_sec}"

        elif "Trick" in cat:
            ans_norm = answer.lower().replace('\u202f', ' ')
            is_refused = (
                "couldn't find" in ans_norm 
                or "not found" in ans_norm 
                or "i couldn't find a verified source for this" in ans_norm
                or "does not contain" in ans_norm
            )
            has_no_fake_validation = (
                "rao v. state of kerala" not in ans_norm
                and "sharma v. icici" not in ans_norm
                and "verma enterprises" not in ans_norm
                and "patel v. state of gujarat" not in ans_norm
                and "article 399" not in ans_norm
                and "section 999" not in ans_norm
            )
            if is_refused and has_no_fake_validation:
                verdict = "PASS"
            else:
                verdict = "FAIL"
                reason = f"Expected clean refusal without validating fake entity. Refused: {is_refused}, Clean: {has_no_fake_validation}"

        # Clean answer excerpt for display
        excerpt = answer.strip().replace("\n", " ").replace('\u202f', ' ')
        if len(excerpt) > 130:
            excerpt = excerpt[:127] + "..."

        results_table.append({
            "id": q_id,
            "question": q_text,
            "category": cat,
            "surface": surface,
            "answer_excerpt": excerpt,
            "full_answer": answer,
            "tier_used": tier_used,
            "citations": citations,
            "model_used": model_used,
            "verdict": verdict,
            "reason": reason
        })

    pass_count = sum(1 for r in results_table if r["verdict"] == "PASS")
    print(f"\n[{mode_name.upper()}] SUMMARY: {pass_count}/{len(results_table)} PASSED")
    return results_table


def run_both_evaluations():
    fallback_results = evaluate_mode("Forced-Fallback Mode", force_fallback=True)
    normal_results = evaluate_mode("Normal Mode", force_fallback=False)

    out_file = BACKEND_DIR / "tests" / "evaluation_results_both_modes.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "forced_fallback_mode": fallback_results,
            "normal_mode": normal_results
        }, f, indent=2)

    print("\nResults saved to:", out_file)


if __name__ == "__main__":
    run_both_evaluations()
