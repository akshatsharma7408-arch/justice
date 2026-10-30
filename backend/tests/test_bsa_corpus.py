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


def test_new_codes_never_attach_case_that_does_not_name_the_code():
    """BNS/BNSS/BSA section answers: a case matched only on the section number (pre-2024 IPC/CrPC/other Act) must not be attached."""
    import re, logging; logging.disable(logging.CRITICAL)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    rx = {"Bharatiya Nyaya Sanhita": r"bharatiya\s+nyaya\s+sanhita|\bb\.?n\.?s\.?\b(?!s)",
          "Bharatiya Nagarik Suraksha Sanhita": r"bharatiya\s+nagarik\s+suraksha\s+sanhita|\bb\.?n\.?s\.?s\.?\b"}
    for act, nums in (("Bharatiya Nyaya Sanhita", (3, 4, 34, 74, 106, 356)), ("Bharatiya Nagarik Suraksha Sanhita", (41,))):
        for n in nums:
            j = c.post('/api/v1/search/answer', json={'query': f'what is section {n} of the {act}', 'force_fallback': True}).json()
            for r in (j.get('source_cases') or j.get('results') or []):
                txt = (str(r.get('text', '')) + str(r.get('title', '')) + str(r.get('ratioSummary', '')) + str(r.get('statutes', ''))).lower()
                assert re.search(rx[act], txt), (act, n, r.get('title'))
            assert "the Supreme Court held" not in j['ai_answer'] or any(re.search(rx[act], (str(r.get('text',''))+str(r.get('title',''))).lower()) for r in (j.get('source_cases') or j.get('results') or [])), (act, n)


def test_named_new_code_is_not_hijacked_by_other_act_routes():
    """'section 74 of the Bharatiya Nyaya Sanhita' must answer BNS s.74, not the Contract Act s.74 holding override;
    'section 74 BNS' must resolve to BNS (explicit act abbreviation), not an ambiguity list."""
    import logging; logging.disable(logging.CRITICAL)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    for q in ("what is section 74 of the Bharatiya Nyaya Sanhita", "section 74 BNS"):
        j = c.post('/api/v1/search/answer', json={'query': q, 'force_fallback': True}).json()
        assert j['ai_answer'].startswith("Section 74 of the Bharatiya Nyaya Sanhita, 2023"), (q, j['ai_answer'][:120])
        assert "Contract Act" not in j['ai_answer'] and "Kailash" not in j['ai_answer']
    j = c.post('/api/v1/search/answer', json={'query': 'section 173 BNSS FIR', 'force_fallback': True}).json()
    assert j['ai_answer'].startswith("Section 173 of the Bharatiya Nagarik Suraksha Sanhita, 2023")
    j = c.post('/api/v1/search/answer', json={'query': 'what is section 74 of the contract act', 'force_fallback': True}).json()
    assert "Indian Contract Act, 1872" in j['ai_answer'] and "Kailash" in j['ai_answer']
