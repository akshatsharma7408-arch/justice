import importlib.util
from pathlib import Path
import unittest

from app.services import holding_verification as h

class QuoteSafetyTests(unittest.TestCase):
    def test_no_holding_verb_cannot_bypass_quote_check(self):
        self.assertFalse(h.verify_holding_claims('The safeguard is "arrest can be made routinely on a mere allegation".', [(1, 'Arrest cannot be made routinely on a mere allegation.')])[0])

    def test_dropped_internal_negation_is_rejected(self):
        self.assertFalse(h.verify_holding_claims('The rule is "arrest can be made in a routine manner on a mere allegation".', [(1, 'Arrest cannot be made in a routine manner on a mere allegation.')])[0])

    def test_clipped_no_prefix_is_rejected(self):
        self.assertFalse(h.verify_holding_claims('The rule is "arrest can be made routinely on a mere allegation".', [(1, 'No arrest can be made routinely on a mere allegation.')])[0])

    def test_clipped_not_prefix_is_rejected(self):
        self.assertFalse(h.verify_holding_claims('The rule is "be arrested routinely on a mere allegation".', [(1, 'A person must not be arrested routinely on a mere allegation.')])[0])

    def test_valid_quote_without_holding_verb_passes(self):
        text = 'No arrest can be made routinely on a mere allegation.'
        self.assertTrue(h.verify_holding_claims('The text says "' + text + '".', [(1, text)])[0])

    def test_one_valid_quote_does_not_launder_another(self):
        text = 'No arrest can be made routinely on a mere allegation.'
        answer = 'The court held that "' + text + '". It also says "all police arrests are automatically lawful".'
        self.assertFalse(h.verify_holding_claims(answer, [(1, text)])[0])

    def test_curly_quotes_checked(self):
        self.assertFalse(h.verify_holding_claims('The text says \u201call police arrests are automatically lawful\u201d.', [(1, 'No such rule exists.')])[0])

    def test_whitespace_normalized(self):
        text = 'The person must be informed of the grounds of arrest.'
        self.assertTrue(h.verify_holding_claims('Text: "The person must be informed of the grounds of arrest."', [(1, text.replace(' ', '\n'))])[0])

    def test_plain_non_holding_text_unchanged(self):
        self.assertEqual(h.verify_holding_claims('Read the judgment for context.', []), (True, []))

    def test_holding_without_quote_still_rejected(self):
        self.assertFalse(h.verify_holding_claims('The court held that all arrests are unlawful.', [(1, 'Other text.')])[0])

    def test_verified_holding_keeps_supporting_paragraph(self):
        text = 'Arrest cannot be made routinely on a mere allegation.'
        self.assertEqual(h.verify_holding_claims('The court held that arrest needs scrutiny: "' + text + '"', [(7, text)]), (True, [7]))

    def test_article_22_1_not_production_deadline(self):
        self.assertFalse(h.verify_holding_claims('Article 22(1) requires production before a magistrate within 24 hours.', [])[0])

    def test_article_22_2_production_passes(self):
        self.assertTrue(h.verify_holding_claims('Article 22(2) concerns production before a magistrate within 24 hours.', [])[0])

    def test_article_22_1_counsel_passes(self):
        self.assertTrue(h.verify_holding_claims('Article 22(1) concerns the right to consult counsel and grounds of arrest.', [])[0])

    def test_both_article_clauses_not_rejected(self):
        self.assertTrue(h.verify_holding_claims('Article 22(1) concerns counsel; Article 22(2) concerns production before a magistrate.', [])[0])

    def test_long_fabricated_quote_cannot_bypass(self):
        self.assertFalse(h.verify_holding_claims('Text: "' + 'fabricated rule ' * 60 + '".', [(1, 'Different text.')])[0])

if __name__ == '__main__':
    unittest.main()
