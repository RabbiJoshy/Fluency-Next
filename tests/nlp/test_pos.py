"""A run must not record a model revision it never verified.

Both modes declared es_dep_news_trf@3.8.0, but lyrics used the constant only to
write `occurrence_pos` into its manifest while loading the model unchecked. The
claim was true by luck. A provenance field that can be wrong is worse than an
absent one, because nothing downstream has reason to doubt it.
"""

import unittest

from fluency.nlp.pos import (
    PinnedModelError,
    canonicalize_target,
    load_pinned,
    parse_pin,
    tag_of_span,
)


class _Model:
    def __init__(self, version):
        self.meta = {"version": version}


class PinTests(unittest.TestCase):
    def test_parses_name_and_version(self) -> None:
        self.assertEqual(parse_pin("es_dep_news_trf@3.8.0"), ("es_dep_news_trf", "3.8.0"))

    def test_malformed_pin_is_refused(self) -> None:
        for bad in ("es_dep_news_trf", "@3.8.0", "name@", ""):
            with self.subTest(pin=bad), self.assertRaises(PinnedModelError):
                parse_pin(bad)

    def test_injected_model_is_the_callers_responsibility(self) -> None:
        """Tests supply doubles; re-verifying them would forbid that."""

        model = _Model("irrelevant")
        self.assertIs(load_pinned("es_dep_news_trf@3.8.0", model=model), model)


class CanonicalizationTests(unittest.TestCase):
    def test_capitalised_target_is_lowered_for_the_tagger(self) -> None:
        """A sentence-initial capital otherwise reads as a proper noun."""

        text, span, changed = canonicalize_target(
            "Casa grande", (0, 4), display_form="casa", observed_form="Casa"
        )
        self.assertEqual((text, span, changed), ("casa grande", (0, 4), True))

    def test_already_canonical_text_is_untouched(self) -> None:
        self.assertEqual(
            canonicalize_target("la casa", (3, 7), display_form="casa", observed_form="casa"),
            ("la casa", (3, 7), False),
        )

    def test_absent_span_is_passed_through(self) -> None:
        self.assertEqual(
            canonicalize_target("la casa", None, display_form="casa"),
            ("la casa", None, False),
        )

    def test_span_must_reproduce_the_observed_form(self) -> None:
        with self.assertRaises(ValueError):
            canonicalize_target("la casa", (0, 2), display_form="casa", observed_form="casa")

    def test_span_outside_the_text_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            canonicalize_target("casa", (0, 99), display_form="casa", observed_form="casa")


class _Token:
    def __init__(self, idx, text, pos):
        self.idx, self.text, self.pos_ = idx, text, pos


class TagOfSpanTests(unittest.TestCase):
    def test_returns_the_first_overlapping_token(self) -> None:
        document = [_Token(0, "la", "DET"), _Token(3, "casa", "NOUN")]
        self.assertEqual(tag_of_span(document, 3, 7), "NOUN")

    def test_returns_none_when_nothing_overlaps(self) -> None:
        self.assertIsNone(tag_of_span([_Token(0, "la", "DET")], 50, 60))


if __name__ == "__main__":
    unittest.main()
