"""
JUSTICE Legal AI Backend — Citizen Rights 12-Question Test
Tests 12 questions through Universal Search (2 per topic).
Reports:
1. Topic and Question
2. Top 3 retrieved Supreme Court cases
3. AI Answer excerpt and model used
4. Whether answer cites a real verified case
"""

import sys
import json
import base64
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app, SITE_PASSWORD

headers = {"Authorization": "Basic " + base64.b64encode(f"user:{SITE_PASSWORD}".encode()).decode()} if SITE_PASSWORD else {}
client = TestClient(app, headers=headers)

TEST_QUESTIONS = [
    # arrest_detention
    ("arrest_detention", "what to do if police arrest me without a warrant"),
    ("arrest_detention", "guidelines for arrest, remand and bail in criminal procedure"),
    # police_misconduct
    ("police_misconduct", "compensation for custodial death and police atrocities"),
    ("police_misconduct", "remedies for custodial torture and police excesses"),
    # bribery_corruption
    ("bribery_corruption", "police officer is asking for a bribe"),
    ("bribery_corruption", "demand and acceptance of illegal gratification by public servant under Prevention of Corruption Act"),
    # housing_tenancy
    ("housing_tenancy", "can my landlord evict me without notice"),
    ("housing_tenancy", "tenant protection against unlawful ejectment and eviction under rent control laws"),
    # traffic_police_powers
    ("traffic_police_powers", "my rights when stopped on my bike"),
    ("traffic_police_powers", "powers of police to search vehicle and issue challan under Motor Vehicles Act"),
    # fundamental_rights
    ("fundamental_rights", "protection of right to life and personal liberty under Article 21"),
    ("fundamental_rights", "freedom of speech and reasonable restrictions under Article 19")
]

def run_12_tests():
    results = []
    print("\n=======================================================")
    print("RUNNING 12 CITIZEN RIGHTS QUESTIONS THROUGH UNIVERSAL SEARCH")
    print("=======================================================\n")

    for idx, (topic, q_text) in enumerate(TEST_QUESTIONS, 1):
        resp = client.post("/api/v1/search", json={"query": q_text, "limit": 3})
        assert resp.status_code == 200, f"Search failed: {resp.status_code} {resp.text}"
        data = resp.json()

        ai_ans = data.get("ai_answer", "")
        model_used = data.get("model_used", "")
        citations = data.get("citations", [])
        top_cases = data.get("results", [])

        # Check citation verification
        cites_verified_case = False
        if citations:
            cites_verified_case = all("[Not Verified]" not in c for c in citations)
        elif "[Not Verified]" not in ai_ans and "tier1" in model_used.lower():
            cites_verified_case = True

        results.append({
            "id": idx,
            "topic": topic,
            "question": q_text,
            "model_used": model_used,
            "cites_verified_case": cites_verified_case,
            "citations": citations,
            "top_3_cases": [
                {
                    "rank": i + 1,
                    "title": c.get("title", ""),
                    "citation": c.get("citation", ""),
                    "year": c.get("decisionYear", ""),
                    "score": round(c.get("score", 0), 4)
                }
                for i, c in enumerate(top_cases[:3])
            ],
            "ai_answer": ai_ans
        })

        print(f"[{idx}/12] [{topic}] {q_text}")
        print(f"  Model: {model_used} | Cites Verified Case: {cites_verified_case}")
        print(f"  Top 3 Cases:")
        for c in top_cases[:3]:
            print(f"    - {c.get('title')} ({c.get('citation')}) [score: {c.get('score', 0):.3f}]")
        excerpt = ai_ans.replace('\n', ' ').replace('\u202f', ' ').replace('\u00a0', ' ')[:140]
        try:
            print(f"  Answer: {excerpt}...\n")
        except UnicodeEncodeError:
            print(f"  Answer: {excerpt.encode('ascii', errors='replace').decode('ascii')}...\n")

    out_file = BACKEND_DIR / "tests" / "citizen_rights_12_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Full results saved to: {out_file}")
    return results

if __name__ == "__main__":
    run_12_tests()
