"""
Unit tests for Item 3: Exact Citation and Landmark Name Search.
Validates:
1. "AIR 1973 SC 1461" returns Kesavananda Bharati alone at the top.
2. "1973 4 SCC 225" returns Kesavananda Bharati alone at the top.
3. "(1978) 1 SCC 248" returns Maneka Gandhi alone at the top.
4. "AIR 1978 SC 597" returns Maneka Gandhi alone at the top.
5. Unknown citation like "AIR 1999 SC 99999" returns no results (never a random case).
"""

import os
import sys
import base64
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.qdrant_service import (
    qdrant_service,
    detect_citation,
    normalize_citation,
    is_pure_citation_query
)

site_pwd = os.getenv("SITE_PASSWORD", "").strip()
headers = {}
if site_pwd:
    token = base64.b64encode(f"user:{site_pwd}".encode()).decode()
    headers["Authorization"] = f"Basic {token}"

client = TestClient(app, headers=headers)


def test_citation_detection_patterns():
    assert detect_citation("AIR 1973 SC 1461") is not None
    assert detect_citation("(1973) 4 SCC 225") is not None
    assert detect_citation("1973 4 SCC 225") is not None
    assert detect_citation("[1973] Supp. 1 SCR 1") is not None
    assert detect_citation("1973INSC91") is not None
    assert detect_citation("(1978) 1 SCC 248") is not None
    assert detect_citation("AIR 1978 SC 597") is not None
    assert detect_citation("random legal question without citations") is None


def test_citation_normalization():
    assert normalize_citation("AIR 1973 SC 1461") == "air1973sc1461"
    assert normalize_citation("(1973) 4 SCC 225") == "19734scc225"
    assert normalize_citation("1973 4 SCC 225") == "19734scc225"
    assert normalize_citation("[1973] Supp. 1 SCR 1") == "1973supp1scr1"
    assert normalize_citation("1973INSC91") == "1973insc91"
    assert normalize_citation("(1978) 1 SCC 248") == "19781scc248"
    assert normalize_citation("AIR 1978 SC 597") == "air1978sc597"


def test_is_pure_citation_query():
    assert is_pure_citation_query("AIR 1973 SC 1461") is True
    assert is_pure_citation_query("(1978) 1 SCC 248") is True
    assert is_pure_citation_query("case AIR 1978 SC 597") is True
    assert is_pure_citation_query("what is the ratio in AIR 1973 SC 1461 on fundamental rights?") is False


def test_air_1973_sc_1461_returns_kesavananda():
    resp = client.post("/api/v1/search", json={"query": "AIR 1973 SC 1461", "limit": 3})
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])
    assert len(results) == 1
    assert "kesavananda" in results[0]["title"].lower()
    assert results[0]["relevance_score"] >= 0.95


def test_1973_4_scc_225_returns_kesavananda():
    resp = client.post("/api/v1/search", json={"query": "1973 4 SCC 225", "limit": 3})
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])
    assert len(results) == 1
    assert "kesavananda" in results[0]["title"].lower()
    assert results[0]["relevance_score"] >= 0.95


def test_1978_1_scc_248_returns_maneka_gandhi():
    resp = client.post("/api/v1/search", json={"query": "(1978) 1 SCC 248", "limit": 3})
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])
    assert len(results) == 1
    assert "maneka gandhi" in results[0]["title"].lower()
    assert results[0]["relevance_score"] >= 0.95


def test_air_1978_sc_597_returns_maneka_gandhi():
    resp = client.post("/api/v1/search", json={"query": "AIR 1978 SC 597", "limit": 3})
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])
    assert len(results) == 1
    assert "maneka gandhi" in results[0]["title"].lower()
    assert results[0]["relevance_score"] >= 0.95


def test_unmatched_citation_returns_no_results():
    resp = client.post("/api/v1/search", json={"query": "AIR 1999 SC 99999", "limit": 3})
    assert resp.status_code == 200
    data = resp.json()
    results = data.get("results", [])
    assert len(results) == 0
