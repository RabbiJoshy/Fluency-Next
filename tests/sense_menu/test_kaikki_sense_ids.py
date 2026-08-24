"""Sense-ID derivation when Kaikki emits a non-unique provider ID.

Kaikki flattens ``senseid`` to its first entry and appends a counter without
re-checking it against IDs it already emitted, so nested sub-senses collide.
Observed on common words in both Portuguese (``não``, ``o``, ``um``) and
French (``canon``, ``charge``, ``voix``).
"""

import unittest

from fluency.sense_menu.kaikki import _sense_id, _sense_keys


def _sense(senseid, gloss, provider_id="en-não-pt-adv-pt:not1", **extra):
    sense = {"id": provider_id, "senseid": list(senseid), "glosses": [gloss]}
    sense.update(extra)
    return sense


class SenseIdTests(unittest.TestCase):
    def test_unique_provider_id_is_used_verbatim(self) -> None:
        """The common path must not change: French IDs stay bit-for-bit stable."""

        sense = _sense(["fr:x"], "gloss", provider_id="en-canon-fr-noun-fr:x")
        sense_id, reference = _sense_id(
            sense, language_code="fr", headword="canon", part_of_speech="noun"
        )
        self.assertEqual(sense_id, "en-canon-fr-noun-fr:x")
        self.assertEqual(reference, "kaikki:en-canon-fr-noun-fr:x")

    def test_collision_falls_back_to_full_senseid_list(self) -> None:
        sense = _sense(["pt:not", "pt:double negative"], "not")
        sense_id, reference = _sense_id(
            sense,
            language_code="pt",
            headword="não",
            part_of_speech="adv",
            provider_id_collides=True,
        )
        self.assertEqual(sense_id, "en-não-pt-adv-pt:not|pt:double negative")
        self.assertTrue(reference.startswith("kaikki-senseid:"))

    def test_colliding_sub_senses_receive_distinct_ids(self) -> None:
        ids = {
            _sense_id(
                _sense(["pt:not", tail], "not"),
                language_code="pt",
                headword="não",
                part_of_speech="adv",
                provider_id_collides=True,
            )[0]
            for tail in ("pt:double negative", "pt:emphatic negation", "pt:isn't")
        }
        self.assertEqual(len(ids), 3)

    def test_content_hash_used_when_sense_keys_also_collide(self) -> None:
        sense = _sense(["pt:not"], "one gloss")
        sense_id, reference = _sense_id(
            sense,
            language_code="pt",
            headword="não",
            part_of_speech="adv",
            provider_id_collides=True,
            sense_keys_collide=True,
        )
        self.assertTrue(sense_id.startswith("sense_"))
        self.assertTrue(reference.startswith("kaikki-content:"))

    def test_content_hash_is_not_positional(self) -> None:
        """Reordering an entry must never re-key a card."""

        first = _sense_id(
            _sense([], "alpha", provider_id=None),
            language_code="pt", headword="x", part_of_speech="noun",
        )[0]
        second = _sense_id(
            _sense([], "alpha", provider_id=None),
            language_code="pt", headword="x", part_of_speech="noun",
        )[0]
        self.assertEqual(first, second)

    def test_content_hash_separates_different_glosses(self) -> None:
        made = {
            _sense_id(
                _sense([], gloss, provider_id=None),
                language_code="pt", headword="x", part_of_speech="noun",
            )[0]
            for gloss in ("alpha", "beta")
        }
        self.assertEqual(len(made), 2)

    def test_sense_keys_ignores_blank_and_non_string(self) -> None:
        self.assertEqual(_sense_keys({"senseid": ["a", "  ", 3, "b"]}), ("a", "b"))


if __name__ == "__main__":
    unittest.main()
