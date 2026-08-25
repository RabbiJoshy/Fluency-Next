"""Wiktionary parity with the fields SpanishDict publishes.

SpanishDict gives every sense a `context` and marks `regions` on some. Wiktionary
carries both, but embedded: context in the prose of a raw gloss, regions among a
flat tag list. These are derived so the two providers publish one shape.
"""

import unittest

from fluency.sense_menu.kaikki import _context, _regions


PT_POLICY = {"region_tags": ["Angola", "Brazil", "Mozambique", "Portugal"]}


class ContextDerivationTests(unittest.TestCase):
    def test_nested_subgloss_wins(self) -> None:
        sense = {"glosses": ["not; don't", "used in double negatives"]}
        self.assertEqual(_context(sense), "used in double negatives")

    def test_leading_parenthetical_of_raw_gloss(self) -> None:
        sense = {
            "glosses": ["what"],
            "raw_glosses": ["(interrogative) what (used to ask for a specific thing)"],
        }
        self.assertEqual(_context(sense), "interrogative")

    def test_topics_used_when_no_parenthetical(self) -> None:
        sense = {"glosses": ["bank"], "topics": ["finance", "business"]}
        self.assertEqual(_context(sense), "finance, business")

    def test_qualifier_is_the_last_resort(self) -> None:
        sense = {"glosses": ["thing"], "qualifier": "archaic"}
        self.assertEqual(_context(sense), "archaic")

    def test_absent_context_is_empty_not_missing(self) -> None:
        self.assertEqual(_context({"glosses": ["thing"]}), "")

    def test_parenthetical_must_precede_real_text(self) -> None:
        """A gloss that is only a parenthetical carries no separable context."""

        self.assertEqual(_context({"glosses": ["x"], "raw_glosses": ["(alone)"]}), "")

    def test_overlong_parenthetical_is_not_a_context_label(self) -> None:
        long = "(" + "x" * 80 + ") word"
        self.assertEqual(_context({"glosses": ["w"], "raw_glosses": [long]}), "")


class RegionDerivationTests(unittest.TestCase):
    def test_regional_tags_are_extracted(self) -> None:
        sense = {"tags": ["Brazil", "informal", "Portugal"]}
        self.assertEqual(_regions(sense, PT_POLICY), ["Brazil", "Portugal"])

    def test_non_regional_tags_are_ignored(self) -> None:
        self.assertEqual(_regions({"tags": ["informal", "slang"]}, PT_POLICY), [])

    def test_language_declaring_no_regions_gets_an_empty_list(self) -> None:
        """Empty is a statement, not an absence: the field is always present."""

        self.assertEqual(_regions({"tags": ["Brazil"]}, {"region_tags": []}), [])
        self.assertEqual(_regions({"tags": ["Brazil"]}, {}), [])


if __name__ == "__main__":
    unittest.main()
