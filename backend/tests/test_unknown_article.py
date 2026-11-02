from app.services.llm_service import unknown_article_message, _edit1

def test_edit1():
    assert _edit1("339AA", "239AA") and _edit1("339AA", "339A") and not _edit1("339AA", "340")

def test_339aa_not_found_lists_one_char_neighbours_without_substituting():
    m = unknown_article_message("339AA")
    assert m and "Article 339AA was not found" in m and "Nothing has been substituted" in m
    assert "Article 239AA" in m and "Delhi" in m
    assert "May 2022" in m

def test_existing_article_returns_none():
    assert unknown_article_message("339") is None and unknown_article_message("239AA") is None

def test_far_number_has_no_neighbours():
    m = unknown_article_message("9999")
    assert m and "one character away" not in m
