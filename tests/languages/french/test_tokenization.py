import json
from pathlib import Path
import unittest

from fluency.languages.french.tokenization import (
    load_tokenization_config,
    tokenize_french,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "french" / "tokenization_cases.json"


class FrenchTokenizationTests(unittest.TestCase):
    def test_golden_cases(self) -> None:
        cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                result = tokenize_french(
                    case["text"], known_surfaces=case["known_surfaces"]
                )
                actual = [
                    [
                        unit.surface_key,
                        unit.token_class,
                        unit.eligible,
                        unit.rejection_reason,
                    ]
                    for unit in result.units
                ]
                self.assertEqual(actual, case["expected"])
                for unit in result.units:
                    self.assertEqual(
                        result.canonical_text[unit.start : unit.end],
                        unit.observed_text,
                    )

    def test_all_approved_elision_prefixes_split_consistently(self) -> None:
        config = load_tokenization_config()
        for prefix in config.elision_expansions:
            with self.subTest(prefix=prefix):
                result = tokenize_french(f"{prefix}exemple")
                self.assertEqual(result.units[0].surface_key, prefix)
                self.assertEqual(result.units[0].token_class, "elided_clitic")
                self.assertEqual(result.units[1].surface_key, "exemple")

    def test_approved_surface_wins_before_grammatical_split(self) -> None:
        result = tokenize_french(
            "Rendez-vous aujourd'hui.",
            known_surfaces={"rendez-vous", "aujourd’hui"},
        )
        self.assertEqual(
            [unit.surface_key for unit in result.units],
            ["rendez-vous", "aujourd’hui"],
        )
        self.assertTrue(all(unit.token_class == "known_surface" for unit in result.units))

    def test_unknown_hyphenated_form_is_retained_without_guessing(self) -> None:
        unit = tokenize_french("alpha-bêta").units[0]
        self.assertFalse(unit.eligible)
        self.assertEqual(unit.token_class, "unresolved_hyphenated")
        self.assertEqual(unit.rejection_reason, "unknown_hyphenated_form")

    def test_url_and_email_are_retained_as_nonlexical(self) -> None:
        result = tokenize_french("Voir https://example.test et moi@example.test")
        rejected = [unit for unit in result.units if not unit.eligible]
        self.assertEqual(len(rejected), 2)
        self.assertTrue(all(unit.rejection_reason == "url_or_email" for unit in rejected))

    def test_token_record_matches_schema_contract(self) -> None:
        schema = json.loads(
            (REPOSITORY_ROOT / "schemas" / "token-unit.schema.json").read_text(
                encoding="utf-8"
            )
        )
        record = tokenize_french("Bonjour").units[0].to_dict()
        self.assertTrue(set(schema["required"]).issubset(record))
        self.assertEqual(
            record["record_version"],
            schema["properties"]["record_version"]["const"],
        )
        self.assertIn(record["token_class"], schema["properties"]["token_class"]["enum"])
        self.assertIn(record["decision"], schema["properties"]["decision"]["enum"])


if __name__ == "__main__":
    unittest.main()
