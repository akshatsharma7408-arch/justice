"""
JUSTICE Legal AI Backend — Legal Maxims Route Unit Tests
Verifies that:
1. GET /api/v1/maxims with limit=300 returns HTTP 200 (no 422 Unprocessable Entity).
2. GET /api/v1/maxims with category and letter filters works cleanly.
3. GET /api/v1/maxims/random returns the Maxim of the Day.
4. POST /api/v1/maxims/explain returns grounded explanation without 422.
"""

import os
import sys
import base64
from pathlib import Path

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


def test_maxims_limit_300_no_422():
    """Frontend requests limit=300 to fetch full compendium. Must return 200, not 422."""
    resp = client.get("/api/v1/maxims?page=1&limit=300")
    assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "results" in data
    assert data["total"] > 200, f"Expected >200 maxims, got {data['total']}"
    assert len(data["results"]) > 200
    print(f" [PASS] Maxims list with limit=300: HTTP 200 ({len(data['results'])} items returned)")


def test_maxims_category_and_letter_filters():
    """Tests filtering by category and letter index."""
    resp_cat = client.get("/api/v1/maxims?category=Contract&limit=50")
    assert resp_cat.status_code == 200
    cat_data = resp_cat.json()
    assert all(m.get("category", "").lower() == "contract" for m in cat_data["results"])

    resp_letter = client.get("/api/v1/maxims?letter=A&limit=50")
    assert resp_letter.status_code == 200
    letter_data = resp_letter.json()
    assert all(m.get("maxim", "").lower().startswith("a") for m in letter_data["results"])
    print(" [PASS] Maxims category and letter filtering verified")


def test_maxim_of_the_day():
    """Tests deterministically stable maxim of the day."""
    resp = client.get("/api/v1/maxims/random")
    assert resp.status_code == 200
    data = resp.json()
    assert "maxim" in data
    assert "maxim" in data["maxim"]
    assert "meaning" in data["maxim"]
    print(" [PASS] Maxim of the day endpoint: HTTP 200")


def test_maxims_explain_endpoint():
    """Tests explain endpoint with valid and unverified maxims."""
    resp = client.post("/api/v1/maxims/explain", json={"maxim": "Actus non facit reum nisi mens sit rea"})
    assert resp.status_code == 200
    data = resp.json()
    assert "explanation" in data

    # Unverified maxim returns clean not found message
    resp_fake = client.post("/api/v1/maxims/explain", json={"maxim": "fake non existent maxim"})
    assert resp_fake.status_code == 200
    data_fake = resp_fake.json()
    assert data_fake.get("found") is False
    print(" [PASS] Maxims explain endpoint verified")


def test_maxim_chat_uses_user_text_and_history():
    """
    Item 11: Make maxim chat and 'apply to my situation' use user's text,
    sending maxim, user message, and last 4 messages to the model.
    Never returns the same stored static explanation.
    """
    resp = client.post("/api/v1/maxims/chat", json={
        "maxim_id": "audi-alteram-partem",
        "message": "Apply this to my situation: my employer fired me without giving me a hearing or notice",
        "history": [
            {"role": "user", "content": "What does audi alteram partem mean?"},
            {"role": "assistant", "content": "Audi alteram partem means listen to the other side."}
        ]
    })
    assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("found") is True
    assert "response" in data
    response_lower = data["response"].lower()
    # Must use user's text and context
    assert "application" in response_lower or "employer" in response_lower or "hearing" in response_lower
    print(" [PASS] Maxim chat with situation text verified")


def test_maxim_follow_up_uses_previous_maxim_context():
    """
    Item 11: Follow-ups (e.g. 'is this applicable for an adult') must use previous maxim as context;
    never return same stored text.
    """
    # Follow-up without explicit maxim_id, context inferred from history
    resp = client.post("/api/v1/maxims/chat", json={
        "message": "is this applicable for an adult?",
        "history": [
            {"role": "user", "content": "Tell me about doli incapax"},
            {"role": "assistant", "content": "Doli incapax means incapable of doing wrong under Indian law."}
        ]
    })
    assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("found") is True
    assert "doli" in data.get("maxim", "").lower()
    response_lower = data["response"].lower()
    # Must explicitly address adult application under Indian law (Sections 82/83 IPC)
    assert "adult" in response_lower
    assert "82" in response_lower or "mens rea" in response_lower or "not apply" in response_lower
    print(" [PASS] Maxim follow-up using previous maxim context verified")


def test_maxim_apply_to_situation_via_explain():
    """Tests fact situation application via explain endpoint."""
    resp = client.post("/api/v1/maxims/explain", json={
        "id": "caveat-emptor",
        "fact_situation": "A buyer purchased a machine which was defective on delivery"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("found") is True
    assert data.get("application_to_facts") is not None
    app_lower = data["application_to_facts"].lower()
    assert "buyer" in app_lower or "application" in app_lower or "defective" in app_lower
    print(" [PASS] Fact situation via explain endpoint verified")


if __name__ == "__main__":
    test_maxims_limit_300_no_422()
    test_maxims_category_and_letter_filters()
    test_maxim_of_the_day()
    test_maxims_explain_endpoint()
    test_maxim_chat_uses_user_text_and_history()
    test_maxim_follow_up_uses_previous_maxim_context()
    test_maxim_apply_to_situation_via_explain()
    print("\nALL MAXIMS ROUTE TESTS PASSED!")

