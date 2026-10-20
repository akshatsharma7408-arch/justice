import pytest
from app.services.qdrant_service import (
    qdrant_service,
    LANDMARK_METADATA,
    enrich_landmark_metadata,
    deduplicate_results_by_name_and_year,
    normalize_case_dedup_key,
)

def test_landmark_metadata_bench_sizes_and_types():
    expected = {
        "kesavananda": (13, "Constitution Bench", "S.M. Sikri, C.J.I."),
        "maneka gandhi": (7, "Constitution Bench", "M.H. Beg, C.J.I."),
        "puttaswamy": (9, "Constitution Bench", "J.S. Khehar, C.J.I."),
        "vishaka": (3, "3-Judge Bench", "J.S. Verma, C.J.I."),
        "navtej": (5, "Constitution Bench", "Dipak Misra, C.J.I."),
        "minerva mills": (5, "Constitution Bench", "Y.V. Chandrachud, C.J.I."),
        "golaknath": (11, "Constitution Bench", "K. Subba Rao, C.J.I."),
        "bommai": (9, "Constitution Bench", "S.R. Pandian, J."),
        "olga tellis": (5, "Constitution Bench", "Y.V. Chandrachud, C.J.I."),
        "arnesh kumar": (2, "Division Bench", "Chandramauli Kumar Prasad, J."),
        "dk basu": (2, "Division Bench", "Kuldip Singh, J."),
        "shreya singhal": (2, "Division Bench", "J. Chelameswar, J."),
    }

    for key, (bench_size, bench_type, lead_judge) in expected.items():
        assert key in LANDMARK_METADATA, f"Key {key} not found in LANDMARK_METADATA"
        meta = LANDMARK_METADATA[key]
        assert meta["benchSize"] == bench_size, f"{key} benchSize expected {bench_size}, got {meta['benchSize']}"
        assert meta["benchType"] == bench_type, f"{key} benchType expected {bench_type}, got {meta['benchType']}"
        assert meta["leadJudge"] == lead_judge, f"{key} leadJudge expected {lead_judge}, got {meta['leadJudge']}"


def test_handchecked_statutes():
    kesavananda_meta = LANDMARK_METADATA["kesavananda"]
    assert "Article 368" in kesavananda_meta["statutes"]
    assert "Article 13" in kesavananda_meta["statutes"]
    assert "Article 31C" in kesavananda_meta["statutes"]

    arnesh_meta = LANDMARK_METADATA["arnesh kumar"]
    assert "Section 41 CrPC" in arnesh_meta["statutes"]
    assert "Section 498A IPC" in arnesh_meta["statutes"]


def test_enrich_landmark_metadata():
    raw_case = {
        "title": "Kesavananda Bharati v. State of Kerala",
        "citation": "(1973) 4 SCC 225",
    }
    enriched = enrich_landmark_metadata(raw_case)
    assert enriched["benchSize"] == 13
    assert enriched["benchType"] == "Constitution Bench"
    assert enriched["leadJudge"] == "S.M. Sikri, C.J.I."
    assert "Article 368" in enriched["statutes"]
    assert enriched["year"] == 1973
    assert enriched["decisionYear"] == 1973


def test_percept_and_kailash_nath_years():
    percept = enrich_landmark_metadata({
        "title": "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan",
        "citation": "(2006) 4 SCC 227",
    })
    assert percept["year"] == 2006
    assert percept["decisionYear"] == 2006
    assert percept["leadJudge"] == "H.K. Sema, J."

    kailash = enrich_landmark_metadata({
        "title": "Kailash Nath Associates v. Delhi Development Authority",
        "citation": "(2015) 4 SCC 136",
    })
    assert kailash["year"] == 2015
    assert kailash["decisionYear"] == 2015
    assert kailash["leadJudge"] == "Ranjan Gogoi, J."


def test_lead_judge_hidden_when_unknown():
    unknown_case = {
        "title": "Some Unknown Case v. State of Maharashtra",
        "citation": "2024 INSC 123",
        "bench": "Division Bench",
    }
    enriched = enrich_landmark_metadata(unknown_case)
    assert enriched["leadJudge"] is None


def test_deduplication_puttaswamy_variants():
    results = [
        {
            "id": "puttaswamy-1",
            "title": "Justice K.S. Puttaswamy (Retd.) v. Union of India",
            "citation": "(2017) 10 SCC 1",
            "year": None,
        },
        {
            "id": "puttaswamy-2",
            "title": "K.S. Puttaswamy v. Union of India (right to privacy)",
            "citation": "AIR 2017 SC 4161",
            "year": 2017,
        }
    ]
    deduped = deduplicate_results_by_name_and_year(results)
    assert len(deduped) == 1
    assert deduped[0]["year"] == 2017
    assert deduped[0]["decisionYear"] == 2017
    assert deduped[0]["benchSize"] == 9
    assert deduped[0]["benchType"] == "Constitution Bench"
