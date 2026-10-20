import sys
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from app.services.qdrant_service import (
    clean_judgment_text,
    cut_to_sentence_boundary,
    extract_relevant_passage,
    LANDMARK_METADATA,
)

def test_clean_judgment_text_strips_page_headers():
    raw = "432 [2025] 2 S.C.R. Digital Supreme Court Reports The court held that no arrest may be made without compliance."
    cleaned = clean_judgment_text(raw)
    assert "[2025] 2 S.C.R." not in cleaned
    assert "Digital Supreme Court Reports" not in cleaned
    assert cleaned.startswith("The court held that")


def test_clean_judgment_text_removes_broken_glyphs():
    raw = "Judgment record \ufffd\u25a1\u25a0 Personal liberty is inviolable under Article 21."
    cleaned = clean_judgment_text(raw)
    assert "\ufffd" not in cleaned
    assert "\u25a1" not in cleaned
    assert "\u25a0" not in cleaned
    assert "Personal liberty is inviolable under Article 21." in cleaned


def test_clean_judgment_text_collapses_spaces():
    raw = "The   court     held   that \n\n  bail   is \t the rule."
    cleaned = clean_judgment_text(raw)
    assert cleaned == "The court held that bail is the rule."


def test_cut_to_sentence_boundary_max_320():
    text = (
        "The Supreme Court of India held that personal liberty under Article 21 is of paramount importance. "
        "Every procedure established by law must be fair, just, and reasonable. "
        "Arbitrary state actions violate the core constitutional ethos of equality before law. "
        "Therefore, no detention can stand if statutory safeguards are not strictly respected."
    )
    snippet = cut_to_sentence_boundary(text, max_chars=320)
    assert len(snippet) <= 320
    assert snippet.endswith(".")  # Complete sentence boundary


def test_never_shows_alias_list_as_passage():
    alias_chunk_text = "Kesavananda Bharati v. State of Kerala. Citations: [1973] SUPP. 1 S.C.R. 1, AIR 1973 SC 1461. Also known as: basic structure doctrine, Kesavananda Bharati, (1973) 4 SCC 225."
    real_chunk_text = "The power to amend under Article 368 does not include the power to alter the basic structure or essential features of the Constitution."

    chunks = [
        {"text": alias_chunk_text, "is_alias_chunk": True},
        {"text": real_chunk_text, "is_alias_chunk": False}
    ]

    passage, label, is_ratio = extract_relevant_passage(
        query="basic structure",
        chunks=chunks,
        case_name="Kesavananda Bharati"
    )

    assert "Also known as" not in passage
    assert "Citations:" not in passage
    assert "basic structure" in passage
    assert "alter the basic structure" in passage


def test_short_cleaned_passage_picks_next_best_chunk():
    short_chunk = "432 [2025] 2 S.C.R. Page 1" # cleans to < 40 chars
    good_chunk = "In our view, the police officer must record recorded reasons in writing before effecting any arrest under Section 41."

    chunks = [
        {"text": short_chunk},
        {"text": good_chunk}
    ]

    passage, label, is_ratio = extract_relevant_passage(
        query="arrest",
        chunks=chunks,
        case_name="Test Case"
    )

    assert len(passage) >= 40
    assert "police officer must record" in passage


def test_landmark_no_judgment_chunk_shows_stored_holding():
    # When a landmark has no valid chunks or empty chunks
    passage, label, is_ratio = extract_relevant_passage(
        query="basic structure",
        chunks=[],
        case_name="Kesavananda Bharati v. State of Kerala"
    )

    expected_holding = LANDMARK_METADATA["kesavananda"]["holding"]
    assert passage == expected_holding
    assert is_ratio is True
    assert label == "RATIO DECIDENDI / LEGAL PRINCIPLE"


def test_only_label_holding_if_operative_part():
    operative_text = "Accordingly, we hold that Section 66A of the Information Technology Act is unconstitutional in its entirety."
    non_operative_text = "The petitioner filed a writ petition challenging the validity of various notices issued by the authorities."

    op_passage, op_label, op_is_ratio = extract_relevant_passage(
        query="section 66A",
        text=operative_text,
        is_verified_ratio=True
    )
    assert op_is_ratio is True
    assert op_label == "RATIO DECIDENDI / LEGAL PRINCIPLE"

    non_op_passage, non_op_label, non_op_is_ratio = extract_relevant_passage(
        query="petitioner notices",
        text=non_operative_text,
        is_verified_ratio=False
    )
    assert non_op_is_ratio is False
    assert non_op_label == "RELEVANT PASSAGE"
