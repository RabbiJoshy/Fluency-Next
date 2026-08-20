import json
from pathlib import Path
import re
import unittest

from fluency.core.identity import (
    IDENTITY_VERSION,
    CardRecord,
    build_card_id,
    create_card_record,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class CardIdentityTests(unittest.TestCase):
    def test_card_id_has_frozen_golden_value(self) -> None:
        self.assertEqual(
            build_card_id("fr", "aujourd’hui"),
            "card_fr_c4f77a5b321b2744890580cf02b7720f",
        )

    def test_card_id_is_deterministic(self) -> None:
        first = build_card_id("fr", "prendre")
        second = build_card_id("fr", "prendre")
        self.assertEqual(first, second)

    def test_language_is_part_of_identity(self) -> None:
        self.assertNotEqual(
            build_card_id("fr", "son"),
            build_card_id("es", "son"),
        )

    def test_inflected_forms_are_separate(self) -> None:
        ids = {
            build_card_id("fr", "prendre"),
            build_card_id("fr", "prends"),
            build_card_id("fr", "pris"),
        }
        self.assertEqual(len(ids), 3)

    def test_record_contains_only_identity_and_registry_fields(self) -> None:
        record = create_card_record("fr", "livre").to_dict()
        self.assertEqual(record["identity_version"], IDENTITY_VERSION)
        self.assertNotIn("mode", record)
        self.assertNotIn("source", record)
        self.assertNotIn("lemma", record)
        self.assertNotIn("part_of_speech", record)
        self.assertNotIn("sense_id", record)

    def test_schema_agrees_with_generated_record(self) -> None:
        schema_path = REPOSITORY_ROOT / "schemas" / "card.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        record = create_card_record("fr", "aujourd’hui").to_dict()

        self.assertEqual(set(schema["required"]), set(record))
        self.assertEqual(
            record["identity_version"],
            schema["properties"]["identity_version"]["const"],
        )
        self.assertEqual(
            record["unit_type"],
            schema["properties"]["unit_type"]["const"],
        )
        self.assertIsNotNone(
            re.fullmatch(schema["properties"]["card_id"]["pattern"], record["card_id"])
        )

    def test_invalid_identity_values_are_rejected(self) -> None:
        invalid_calls = [
            lambda: build_card_id("FR", "prendre"),
            lambda: build_card_id("fr-FR", "prendre"),
            lambda: build_card_id("fr", ""),
            lambda: build_card_id("fr", " prendre"),
            lambda: build_card_id("fr", "prendre", unit_type="lemma"),
            lambda: build_card_id(
                "fr", "prendre", identity_version="surface-card/v2"
            ),
        ]
        for invalid_call in invalid_calls:
            with self.subTest(call=invalid_call):
                with self.assertRaises((TypeError, ValueError)):
                    invalid_call()

    def test_merged_card_requires_same_language_redirect(self) -> None:
        old = create_card_record("fr", "porte‐monnaie")
        replacement = create_card_record("fr", "porte-monnaie")
        merged = CardRecord(
            **{
                **old.to_dict(),
                "status": "merged",
                "redirect_card_id": replacement.card_id,
            }
        )
        self.assertEqual(merged.redirect_card_id, replacement.card_id)

        spanish_redirect = create_card_record("es", "portamonedas").card_id
        with self.assertRaises(ValueError):
            CardRecord(
                **{
                    **old.to_dict(),
                    "status": "merged",
                    "redirect_card_id": spanish_redirect,
                }
            )


if __name__ == "__main__":
    unittest.main()

