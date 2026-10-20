"""
Unit and Integration Tests for Search Quality:
- Typo-tolerant name search (Levenshtein/fuzzy matching for landmark cases)
- Relevance bar filtering (dropping weak extras and returning empty list on non-matches)
- Tag extraction from judgment text (no hardcoded fake tags)
- Passage extraction (skipping OCR noise/exhibits, reasoning markers, ratio labeling)
"""

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.qdrant_service import (
    qdrant_service,
    levenshtein_distance,
    fuzzy_word_match,
    extract_statutes_from_text,
    extract_relevant_passage,
    extract_query_aliases
)


class TestSearchQuality(unittest.TestCase):

    def test_levenshtein_distance(self):
        self.assertEqual(levenshtein_distance("kesvananda", "kesavananda"), 1)
        self.assertEqual(levenshtein_distance("maneka", "maneka"), 0)
        self.assertEqual(levenshtein_distance("ghandi", "gandhi"), 2)
        self.assertEqual(levenshtein_distance("puttuswamy", "puttaswamy"), 1)
        self.assertEqual(levenshtein_distance("abc", "xyz"), 3)

    def test_fuzzy_word_match_rules(self):
        # 6+ letters: edit distance up to 2
        self.assertTrue(fuzzy_word_match("kesvananda", "kesavananda"))
        self.assertTrue(fuzzy_word_match("puttuswamy", "puttaswamy"))
        self.assertTrue(fuzzy_word_match("ghandi", "gandhi"))
        # 4-5 letters: edit distance up to 1
        self.assertTrue(fuzzy_word_match("wipro", "wipro"))
        self.assertTrue(fuzzy_word_match("wipr", "wipro"))
        # Digits must NOT be fuzzy matched
        self.assertFalse(fuzzy_word_match("1973", "1978"))
        self.assertFalse(fuzzy_word_match("1461", "1462"))
        self.assertFalse(fuzzy_word_match("74", "73"))
        # Short words (< 4 letters) must be exact
        self.assertTrue(fuzzy_word_match("air", "air"))
        self.assertFalse(fuzzy_word_match("air", "aim"))

    def test_extract_query_aliases_typos(self):
        # Queries with typos must identify the canonical landmark aliases
        self.assertTrue(any("Kesavananda" in a for a in extract_query_aliases("kesvananda")))
        self.assertTrue(any("Kesavananda" in a for a in extract_query_aliases("kesavanand bharti")))
        self.assertTrue(any("Maneka" in a for a in extract_query_aliases("maneka ghandi")))
        self.assertTrue(any("Puttaswamy" in a for a in extract_query_aliases("puttuswamy")))
        self.assertTrue("AIR 1973 SC 1461" in extract_query_aliases("AIR 1973 SC 1461"))

    def test_typo_search_returns_landmark(self):
        # "kesvananda" should retrieve Kesavananda Bharati at the top
        results = qdrant_service.search_precedents("kesvananda", limit=3)
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("Kesavananda Bharati", results[0]["title"])
        self.assertGreaterEqual(results[0]["relevance_score"], 0.95)

        # "puttuswamy" should retrieve Puttaswamy
        res_putt = qdrant_service.search_precedents("puttuswamy", limit=3)
        self.assertGreaterEqual(len(res_putt), 1)
        self.assertIn("Puttaswamy", res_putt[0]["title"])

    def test_relevance_bar_empty_on_nonsense(self):
        # Completely irrelevant nonsense query should return empty list
        results = qdrant_service.search_precedents("xyzzqwerty asdfgh", limit=5)
        self.assertEqual(len(results), 0)

        res_astro = qdrant_service.search_precedents("quantum astrophysics supercollider", limit=5)
        self.assertEqual(len(res_astro), 0)

    def test_relevance_bar_after_exact_match(self):
        # After exact match for Kesavananda or citation, weak unrelated extras are dropped
        results = qdrant_service.search_precedents("AIR 1973 SC 1461", limit=5)
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("Kesavananda", results[0]["title"])
        for r in results:
            if "Kesavananda" not in r["title"]:
                has_term = "1461" in r.get("text", "") or "kesavananda" in r.get("text", "").lower()
                self.assertTrue(has_term)

    def test_extract_statutes_no_fake_tags(self):
        # If no statutes are mentioned in text, return empty list (no hardcoded fake tags)
        empty_tags = extract_statutes_from_text("This case is about a commercial dispute regarding shipping containers.")
        self.assertEqual(empty_tags, [])
        self.assertNotIn("Indian Contract Act, 1872", empty_tags)
        self.assertNotIn("Constitution of India, Article 141", empty_tags)

    def test_extract_statutes_articles_and_sections(self):
        text = "The petitioner claims protection under Article 21 and Article 19(1)(a) of the Constitution."
        tags = extract_statutes_from_text(text)
        self.assertTrue(any("Article 21" in t for t in tags))
        self.assertTrue(any("Article 19" in t for t in tags))

    def test_extract_statutes_named_act(self):
        text = "Under Section 74 of the Indian Contract Act, reasonable compensation is awarded."
        tags = extract_statutes_from_text(text)
        self.assertTrue(any("Section 74" in t and "Contract" in t for t in tags))

    def test_skips_exhibits_and_transcripts(self):
        noisy_text = (
            "Exhibit P-12: The statement of PW-1 in cross-examination.\n\n"
            "Q. Did you inspect the premises?\n"
            "A. Yes, on June 4th.\n\n"
            "We hold that Section 74 of the Contract Act awards only reasonable compensation not exceeding the penalty named."
        )
        passage, label, is_ratio = extract_relevant_passage("liquidated damages Section 74", noisy_text, False)
        self.assertNotIn("PW-1", passage)
        self.assertNotIn("Exhibit", passage)
        self.assertIn("We hold that Section 74", passage)
        self.assertEqual(label, "RELEVANT PASSAGE")
        self.assertFalse(is_ratio)

    def test_verified_ratio_label(self):
        verified_text = "Section 27 renders post-employment non-compete covenants void ab initio."
        passage, label, is_ratio = extract_relevant_passage("non-compete", "", True, verified_text)
        self.assertEqual(passage, verified_text)
        self.assertEqual(label, "RATIO DECIDENDI / LEGAL PRINCIPLE")
        self.assertTrue(is_ratio)


if __name__ == "__main__":
    unittest.main()
