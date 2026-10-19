"""
Tests for Qdrant exact-match boost for landmark case names, aliases, and citations.
Uses a mocked Qdrant client to verify query parsing, filtering, and priority ranking.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.qdrant_service import QdrantService, extract_query_aliases


class TestQdrantExactBoost(unittest.TestCase):

    def test_extract_query_aliases_citations_and_names(self):
        # 1. Kesavananda name
        aliases = extract_query_aliases("Kesavananda Bharati")
        self.assertTrue(any("Kesavananda" in a for a in aliases))

        # 2. AIR citation
        aliases = extract_query_aliases("AIR 1973 SC 1461")
        self.assertTrue(any("AIR 1973 SC 1461" in a for a in aliases))

        # 3. SCC citation with parentheses
        aliases = extract_query_aliases("(1973) 4 SCC 225")
        self.assertTrue(any("1973" in a and "SCC 225" in a for a in aliases))

        # 4. Basic structure doctrine
        aliases = extract_query_aliases("What is basic structure?")
        self.assertTrue(any("basic structure" in a.lower() for a in aliases))

        # 5. Maneka Gandhi
        aliases = extract_query_aliases("Maneka Gandhi passport impounding")
        self.assertTrue(any("Maneka Gandhi" in a for a in aliases))

        # 6. Right to privacy Puttaswamy
        aliases = extract_query_aliases("right to privacy Puttaswamy")
        self.assertTrue(any("Puttaswamy" in a for a in aliases))
        self.assertTrue(any("privacy" in a.lower() for a in aliases))

        # 7. Unrelated query has no landmark aliases
        aliases = extract_query_aliases("contract breach liquidated damages")
        self.assertEqual(aliases, [])

    def test_search_qdrant_boost_priority_with_mock_client(self):
        """Verifies that an exact citation match triggers scroll with filter and appears first."""
        service = QdrantService()

        # Mock the Qdrant client
        mock_client = MagicMock()
        service._client = mock_client

        # Mock collections response
        mock_col = MagicMock()
        mock_col.name = "sc_judgments"
        mock_client.get_collections.return_value.collections = [mock_col]

        # Mock scroll response (exact match boost)
        mock_scroll_record = MagicMock()
        mock_scroll_record.payload = {
            "case_name": "HIS HOLINESS KESAVANANDA BHARATI SRIPADAGALAVARU versus STATE OF KERALA",
            "common_name": "Kesavananda Bharati v. State of Kerala",
            "year": 1973,
            "citation": "[1973] SUPP. 1 S.C.R. 1",
            "topic": "constitutional_landmark",
            "landmark": True,
            "aliases": ["AIR 1973 SC 1461", "Kesavananda", "(1973) 4 SCC 225", "basic structure"],
            "text": "The basic structure of the Constitution cannot be abrogated by constitutional amendment."
        }
        mock_client.scroll.return_value = ([mock_scroll_record], None)

        # Mock vector search hits (general semantic search)
        mock_vector_hit = MagicMock()
        mock_vector_hit.score = 0.82
        mock_vector_hit.payload = {
            "case_name": "Minerva Mills v. Union of India",
            "year": 1980,
            "text": "Parliament has no power to alter basic structure."
        }
        mock_client.search.return_value = [mock_vector_hit]

        # Execute search with exact citation
        results = service._search_qdrant(
            query="AIR 1973 SC 1461 basic structure",
            court_filter="ALL",
            bench_filter="ALL",
            limit=5
        )

        # Assert scroll was called with filter on aliases
        self.assertTrue(mock_client.scroll.called)
        call_kwargs = mock_client.scroll.call_args[1]
        self.assertEqual(call_kwargs["collection_name"], "sc_judgments")
        scroll_filter = call_kwargs["scroll_filter"]
        self.assertIsNotNone(scroll_filter)

        # Assert Kesavananda is returned as the very first result with top score
        self.assertGreaterEqual(len(results), 1)
        first = results[0]
        self.assertEqual(first["title"], "Kesavananda Bharati v. State of Kerala")
        self.assertEqual(first["relevance_score"], 0.99)
        self.assertTrue("qdrant_exact_boost" in first["retrieval_mode"])

    def test_search_qdrant_unrelated_query_no_boost(self):
        """Verifies that queries without landmark aliases do not trigger scroll."""
        service = QdrantService()
        service.corpus = []
        mock_client = MagicMock()
        service._client = mock_client

        mock_col = MagicMock()
        mock_col.name = "sc_judgments"
        mock_client.get_collections.return_value.collections = [mock_col]

        mock_vector_hit = MagicMock()
        mock_vector_hit.score = 0.75
        mock_vector_hit.payload = {
            "case_name": "Gujarat Bottling Co. Ltd. v. Coca Cola Co.",
            "year": 1995,
            "text": "Negative covenant during contract is valid."
        }
        mock_client.search.return_value = [mock_vector_hit]

        results = service._search_qdrant(
            query="validity of negative covenant during employment",
            court_filter="ALL",
            bench_filter="ALL",
            limit=5
        )

        # scroll should NOT be called because query has no landmark aliases
        self.assertFalse(mock_client.scroll.called)
        self.assertTrue(mock_client.search.called)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Gujarat Bottling Co. Ltd. v. Coca Cola Co.")


if __name__ == "__main__":
    unittest.main()
