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


if __name__ == "__main__":
    test_maxims_limit_300_no_422()
    test_maxims_category_and_letter_filters()
    test_maxim_of_the_day()
    test_maxims_explain_endpoint()
    print("\nALL MAXIMS ROUTE TESTS PASSED!")
