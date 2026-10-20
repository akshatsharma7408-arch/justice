import sys
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from app.services.qdrant_service import (
    qdrant_service,
    extract_section_or_article,
    detect_everyday_rights_topic,
    ACT_MAP,
    EVERYDAY_RIGHTS_RULES
)

def test_extract_section_or_article():
    art21 = extract_section_or_article("Article 21")
    assert art21 is not None
    assert art21["type"] == "article"
    assert art21["number"] == "21"
    assert art21["act"] == "constitution"

    sec41 = extract_section_or_article("Section 41 CrPC")
    assert sec41 is not None
    assert sec41["type"] == "section"
    assert sec41["number"] == "41"
    assert sec41["act"] == "crpc"

    sec498a = extract_section_or_article("Section 498A")
    assert sec498a is not None
    assert sec498a["number"] == "498A"
    assert sec498a["act"] == "ipc"

    sec27 = extract_section_or_article("Section 27 Contract Act")
    assert sec27 is not None
    assert sec27["number"] == "27"
    assert sec27["act"] == "contract act"


def test_detect_everyday_rights_topic():
    t_arrest, _ = detect_everyday_rights_topic("arrest without warrant")
    assert t_arrest == "arrest"

    t_evict, _ = detect_everyday_rights_topic("landlord eviction notice")
    assert t_evict == "eviction"

    t_bribe, _ = detect_everyday_rights_topic("taking a bribe")
    assert t_bribe == "bribe"

    t_traffic, _ = detect_everyday_rights_topic("traffic stop on bike")
    assert t_traffic == "traffic"


def test_article_21_returns_landmark_first():
    results = qdrant_service.search_precedents("Article 21", limit=8)
    assert len(results) >= 1
    top_case = results[0]["title"]
    # Maneka Gandhi or Puttaswamy must be first, NOT a tax case (e.g. Narinderjit Singh Sahni)
    assert any(lm in top_case for lm in ["Maneka Gandhi", "Puttaswamy"])
    assert "NARINDERJIT" not in top_case


def test_section_41_crpc_returns_arnesh_kumar_first():
    results = qdrant_service.search_precedents("Section 41 CrPC", limit=8)
    assert len(results) >= 1
    top_case = results[0]["title"]
    # Arnesh Kumar must be first, NOT Arvind Kejriwal
    assert "Arnesh Kumar" in top_case
    assert "ARVIND KEJRIWAL" not in top_case


def test_section_498a_returns_arnesh_kumar():
    results = qdrant_service.search_precedents("Section 498A", limit=8)
    assert len(results) >= 1
    top_case = results[0]["title"]
    assert "Arnesh Kumar" in top_case


def test_section_27_contract_act_returns_percept_dmark():
    results = qdrant_service.search_precedents("Section 27 Contract Act", limit=8)
    assert len(results) >= 1
    top_case = results[0]["title"]
    assert any(pm in top_case for pm in ["Percept D'Mark", "Niranjan", "Superintendence"])


def test_everyday_rights_topics_filtering():
    # Arrest query: must have arrest keywords, no land acquisition or cheque bounce
    res_arrest = qdrant_service.search_precedents("arrest without warrant", limit=8)
    assert len(res_arrest) >= 1
    for r in res_arrest:
        comb = f"{r.get('title', '')} {r.get('ratioSummary', '')} {r.get('text', '')}".lower()
        assert not any(nk in comb for nk in ["land acquisition", "section 138", "dishonour of cheque"])
        assert any(rk in comb for rk in ["arrest", "warrant", "custody", "section 41", "detention"])

    # Eviction query: must have eviction keywords, no land acquisition or cheque bounce
    res_evict = qdrant_service.search_precedents("landlord eviction", limit=8)
    assert len(res_evict) >= 1
    for r in res_evict:
        comb = f"{r.get('title', '')} {r.get('ratioSummary', '')} {r.get('text', '')}".lower()
        assert not any(nk in comb for nk in ["land acquisition", "section 138", "dishonour of cheque"])
        assert any(rk in comb for rk in ["tenant", "landlord", "eviction", "rent control", "tenancy"])

    # Bribe query: must have corruption keywords, no land acquisition or cheque bounce
    res_bribe = qdrant_service.search_precedents("bribe", limit=8)
    assert len(res_bribe) >= 1
    for r in res_bribe:
        comb = f"{r.get('title', '')} {r.get('ratioSummary', '')} {r.get('text', '')}".lower()
        assert not any(nk in comb for nk in ["land acquisition", "section 138", "dishonour of cheque"])
        assert any(rk in comb for rk in ["bribe", "gratification", "corruption"])

    # Traffic query: must have traffic keywords, no land acquisition or cheque bounce
    res_traffic = qdrant_service.search_precedents("traffic stop", limit=8)
    assert len(res_traffic) >= 1
    for r in res_traffic:
        comb = f"{r.get('title', '')} {r.get('ratioSummary', '')} {r.get('text', '')}".lower()
        assert not any(nk in comb for nk in ["land acquisition", "section 138", "dishonour of cheque"])
        assert any(rk in comb for rk in ["motor vehicles", "challan", "traffic", "vehicle"])


def test_relevance_score_never_exceeds_99_and_max_8_results():
    queries = [
        "Article 21", "Section 41 CrPC", "arrest without warrant",
        "Section 27 Contract Act", "Kesavananda Bharati", "AIR 1973 SC 1461"
    ]
    for q in queries:
        results = qdrant_service.search_precedents(q, limit=8)
        assert len(results) <= 8
        for r in results:
            score = r.get("relevance_score", 0.0)
            assert score <= 0.99
            assert round(score * 100) <= 99


def test_nonsense_queries_return_empty_list():
    res1 = qdrant_service.search_precedents("quantum astrophysics supercollider", limit=8)
    assert len(res1) == 0

    res2 = qdrant_service.search_precedents("xyzzqwerty asdfgh", limit=8)
    assert len(res2) == 0
