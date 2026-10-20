"""
Tests for Item 7: Spelling Tolerance & Query Correction
Verifies:
- Damerau-Levenshtein distance calculation
- Soundex phonetic matching
- Correction of misspelled user queries:
  * "arest without warant" -> "arrest without warrant"
  * "navtej jauhar" -> "navtej johar"
  * "kesavnanda bharti" -> "kesavananda bharati"
  * "maneka ghandi" -> "maneka gandhi"
  * "puttuswamy" -> "puttaswamy"
  * "golaknaath" -> "golaknath"
  * "shreya singal" -> "shreya singhal"
  * "basic structre doctrine" -> "basic structure doctrine"
  * "right to privcy" -> "right to privacy"
- Preservation of valid words, case numbers, statutory sections, and citations
- End-to-end precedent search retrieval with typos
"""

import sys
from pathlib import Path
import unittest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.spelling_service import (
    correct_query,
    damerau_levenshtein_distance,
    soundex
)
from app.services.qdrant_service import qdrant_service


class TestSpellingTolerance(unittest.TestCase):

    def test_damerau_levenshtein_distance(self):
        # 1 edit distance
        self.assertEqual(damerau_levenshtein_distance("arest", "arrest"), 1)
        self.assertEqual(damerau_levenshtein_distance("warant", "warrant"), 1)
        self.assertEqual(damerau_levenshtein_distance("structre", "structure"), 1)
        self.assertEqual(damerau_levenshtein_distance("privcy", "privacy"), 1)
        # Transposition: adjacent character swap is distance 1
        self.assertEqual(damerau_levenshtein_distance("teh", "the"), 1)
        self.assertEqual(damerau_levenshtein_distance("ca", "ac"), 1)

    def test_soundex_phonetic_matching(self):
        # jauhar matches johar
        self.assertEqual(soundex("jauhar"), soundex("johar"))
        # singal matches singhal
        self.assertEqual(soundex("singal"), soundex("singhal"))
        # ghandi matches gandhi
        self.assertEqual(soundex("ghandi"), soundex("gandhi"))
        # bharti matches bharati
        self.assertEqual(soundex("bharti"), soundex("bharati"))

    def test_required_misspelled_queries(self):
        test_cases = [
            ("arest without warant", "arrest without warrant"),
            ("navtej jauhar", "navtej johar"),
            ("kesavnanda bharti", "kesavananda bharati"),
            ("maneka ghandi", "maneka gandhi"),
            ("puttuswamy", "puttaswamy"),
            ("golaknaath", "golaknath"),
            ("shreya singal", "shreya singhal"),
            ("basic structre doctrine", "basic structure doctrine"),
            ("right to privcy", "right to privacy"),
        ]

        for typo_query, expected_corrected in test_cases:
            corrected, has_changes = correct_query(typo_query)
            self.assertTrue(has_changes, f"Expected correction for '{typo_query}'")
            self.assertEqual(
                corrected.lower(),
                expected_corrected.lower(),
                f"For query '{typo_query}', expected '{expected_corrected}' but got '{corrected}'"
            )

    def test_do_not_correct_valid_words_or_numbers(self):
        valid_queries = [
            "arrest without warrant",
            "Article 21",
            "Section 41 CrPC",
            "Section 498A",
            "AIR 1973 SC 1461",
            "(1973) 4 SCC 225",
            "1973 4 SCC 225",
            "(1978) 1 SCC 248",
            "basic structure doctrine",
            "right to privacy"
        ]

        for valid_query in valid_queries:
            corrected, has_changes = correct_query(valid_query)
            self.assertFalse(has_changes, f"Should not alter valid query '{valid_query}'")
            self.assertEqual(corrected, valid_query)

    def test_end_to_end_search_arest_without_warant(self):
        # In past: 'arest without warant' returned nothing.
        # Now: automatically corrected to 'arrest without warrant' and returns arrest topic cases.
        results = qdrant_service.search_precedents("arest without warant", limit=5)
        self.assertGreaterEqual(len(results), 1)
        titles_and_texts = " ".join(f"{r.get('title', '')} {r.get('ratioSummary', '')}" for r in results).lower()
        self.assertTrue(
            any(w in titles_and_texts for w in ["arrest", "warrant", "custody"]),
            f"Expected arrest/warrant topic cases for 'arest without warant', got: {titles_and_texts[:200]}"
        )

    def test_end_to_end_search_navtej_jauhar(self):
        # In past: 'navtej jauhar' returned nothing.
        # Now: automatically corrected to 'navtej johar' and returns Navtej Singh Johar.
        results = qdrant_service.search_precedents("navtej jauhar", limit=5)
        self.assertGreaterEqual(len(results), 1)
        first = results[0]
        self.assertIn("Navtej", first.get("title", ""))


if __name__ == "__main__":
    unittest.main()
