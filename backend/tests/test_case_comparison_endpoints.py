"""
Tests for Cases collection search and detail lookup endpoints:
- GET /api/v1/cases/search
- GET /api/v1/cases/{case_id}
Verifies that cases across the 1,740+ collection can be searched by name, partial name, and citation,
and retrieved by ID for Precedent Comparison and Doctrine Matrix.
"""

import sys
import base64
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from app.main import app, SITE_PASSWORD

headers = {}
if SITE_PASSWORD:
    b64 = base64.b64encode(f"admin:{SITE_PASSWORD}".encode()).decode()
    headers["Authorization"] = f"Basic {b64}"

client = TestClient(app, headers=headers)


def test_cases_search_by_partial_name():
    """Search for 'Dhanapal' returns V. Dhanapal Chettiar tenancy precedent."""
    resp = client.get("/api/v1/cases/search?q=Dhanapal")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    found = any("dhanapal" in c["title"].lower() for c in data["cases"])
    assert found, f"Expected Dhanapal in search results, got: {[c['title'] for c in data['cases']]}"


def test_cases_search_by_citation():
    """Search for '[1975] 3 S.C.R. 1' finds Firm of Pratapchand Nopaji."""
    resp = client.get("/api/v1/cases/search?q=1975 3 SCR 1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    hit = data["cases"][0]
    assert "1975" in hit["citation"] or "1975" in str(hit["decisionYear"])


def test_cases_search_empty_query_returns_candidates():
    """Empty query returns popular candidate precedents without error."""
    resp = client.get("/api/v1/cases/search?q=&limit=15")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 10
    assert len(data["cases"]) >= 10


def test_get_case_by_id_landmark():
    """Retrieves full details for a verified landmark case (e.g. sc-2006-percept)."""
    resp = client.get("/api/v1/cases/sc-2006-percept")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "sc-2006-percept"
    assert "Percept" in data["title"]
    assert data["decisionYear"] == 2006
    assert data["benchSize"] == 2
    assert "Section 27" in " ".join(data["statutes"])


def test_get_case_by_id_tenancy():
    """Retrieves full details for Dhanapal Chettiar tenancy precedent."""
    resp = client.get("/api/v1/cases/sc-1979-dhanapal")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "sc-1979-dhanapal"
    assert "Dhanapal" in data["title"]
    assert data["decisionYear"] == 1979
    assert data["benchSize"] == 7
    assert "Constitution Bench" in (data["benchType"] or "")


def test_get_case_by_id_non_landmark_sc():
    """Retrieves a non-landmark case from the 84+ SC dataset (1975_3_1_20)."""
    resp = client.get("/api/v1/cases/1975_3_1_20")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "1975_3_1_20"
    assert "PRATAPCHAND" in data["title"].upper()
    assert data["decisionYear"] == 1975


def test_get_case_by_id_not_found():
    """Non-existent case ID returns honest 404 error message."""
    resp = client.get("/api/v1/cases/non-existent-case-id-99999")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "not found in the verified dataset" in detail or "couldn't find" in detail


def test_cases_search_full_collection_queries():
    """Full-collection search in cases router must query live collection and return real cases."""
    for q in ["Kesavananda", "Maneka Gandhi", "Vihaan", "Harminder", "AIR1973SC1461"]:
        resp = client.get(f"/api/v1/cases/search?q={q}&limit=5")
        assert resp.status_code == 200, f"Query '{q}' failed with status {resp.status_code}"
        data = resp.json()
        assert data["total"] >= 1, f"Expected at least 1 result for query '{q}', got 0"
        titles = [c["title"].lower() for c in data["cases"]]
        if q == "Kesavananda" or q == "AIR1973SC1461":
            assert any("kesavananda" in t for t in titles), f"Kesavananda missing for '{q}': {titles}"
        elif q == "Maneka Gandhi":
            assert any("maneka" in t for t in titles), f"Maneka missing for '{q}': {titles}"
        elif q == "Vihaan":
            assert any("vihaan" in t for t in titles), f"Vihaan missing for '{q}': {titles}"
        elif q == "Harminder":
            assert any("harminder" in t for t in titles), f"Harminder missing for '{q}': {titles}"


def test_unverified_case_ratio_label():
    """Unverified sliced text in case records must be labeled SOURCE EXCERPT / OPENING TEXT (UNVERIFIED)."""
    # 1975_3_1_20 is a non-landmark case whose ratio is extracted from raw text
    resp = client.get("/api/v1/cases/1975_3_1_20")
    assert resp.status_code == 200
    data = resp.json()
    assert "ratioLabel" in data
    assert data["is_verified_ratio"] is False
    assert data["ratioLabel"] == "SOURCE EXCERPT / OPENING TEXT (UNVERIFIED)"

