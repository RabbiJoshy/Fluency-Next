import json
from pathlib import Path
import unittest

from fluency.languages.french.lookup import build_lookup_candidates
from fluency.languages.french.surfaces import create_french_card


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class FrenchLookupTests(unittest.TestCase):
    def test_elided_clitic_has_exact_and_expansion_candidates(self) -> None:
        card = create_french_card("l'")
        candidates = build_lookup_candidates(card)
        self.assertEqual(
            [(candidate.lookup_form, candidate.relation) for candidate in candidates],
            [("l’", "exact"), ("le", "elision_expansion"), ("la", "elision_expansion")],
        )
        self.assertTrue(all(candidate.card_id == card.card_id for candidate in candidates))

    def test_contraction_components_do_not_pollute_lookup_candidates(self) -> None:
        card = create_french_card("du")
        candidates = build_lookup_candidates(card)
        self.assertEqual([candidate.lookup_form for candidate in candidates], ["du"])

    def test_ordinary_surface_uses_exact_lookup_only(self) -> None:
        card = create_french_card("prendre")
        candidates = build_lookup_candidates(card)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].priority, 0)
        self.assertEqual(candidates[0].relation, "exact")

    def test_lookup_record_matches_schema_contract(self) -> None:
        schema = json.loads(
            (REPOSITORY_ROOT / "schemas" / "lookup-candidate.schema.json").read_text(
                encoding="utf-8"
            )
        )
        record = build_lookup_candidates(create_french_card("j’"))[0].to_dict()
        self.assertEqual(set(record), set(schema["required"]))
        self.assertEqual(
            record["record_version"],
            schema["properties"]["record_version"]["const"],
        )


if __name__ == "__main__":
    unittest.main()

