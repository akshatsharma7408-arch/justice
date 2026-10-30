"""BSA 2023 corpus integrity and lookup tests (no network)."""
import json, re
from pathlib import Path
from app.ingest.seed_bare_acts import BSA_CORPUS_PATH, load_bsa_provisions, BSA_ACT_ID
from app.services.statute_service import StatuteService

def test_bsa_has_170_contiguous_sections_with_headings():
    c = json.loads(Path(BSA_CORPUS_PATH).read_text(encoding="utf-8"))
    assert sorted(map(int, c)) == list(range(1, 171))
    for k, e in c.items():
        assert e["heading"].strip().endswith("."), k
        assert len(e["body"]) > 40, k
        assert "( )" not in e["body"], k
        assert "THE SCHEDULE" not in e["body"].upper() or k != "170"

def test_bsa_rows_carry_source_and_status():
    rows = load_bsa_provisions()
    assert len(rows) == 170
    assert all(r["act_id"] == BSA_ACT_ID and r["source_url"] and r["status"] == "in_force" for r in rows)

def test_bsa_lookup_exact_and_alias():
    s = StatuteService()
    p = s.get_provision(BSA_ACT_ID, "63")
    assert p and p["heading"] == "Admissibility of electronic records."
    assert "Schedule" in (p.get("explanation") or "") and "expert" in (p.get("explanation") or "")
    assert s.normalize_act_id("section 63 of BSA") == BSA_ACT_ID
    assert s.get_provision(BSA_ACT_ID, "6") and s.get_provision(BSA_ACT_ID, "6")["heading"] != s.get_provision(BSA_ACT_ID, "63")["heading"]
    assert s.get_provision(BSA_ACT_ID, "171") is None

def test_bsa_savings_text_s170():
    p = StatuteService().get_provision(BSA_ACT_ID, "170")
    assert "Indian Evidence Act, 1872 is hereby repealed" in p["body"] and "pending" in p["body"]
    assert "pending" in p["explanation"]


def test_bsa_section_answer_has_caveat_and_no_unrelated_case():
    import logging; logging.disable(logging.CRITICAL)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    j = c.post('/api/v1/search/answer', json={'query': 'what does section 63 of BSA say about electronic records certificate', 'force_fallback': True}).json()
    a = j['ai_answer']
    assert "Admissibility of electronic records" in a and "Schedule" in a and "as enacted" in a.lower()
    assert "the Supreme Court held" not in a  # no case in the corpus names the BSA; sec-number-only matches are unrelated
    assert all("Bharatiya Sakshya" in x for x in j['citations'])
