from pathlib import Path
import unittest


APP_ROOT = Path(__file__).resolve().parents[2] / "app"


class MetadataContractUITests(unittest.TestCase):
    def test_card_ui_prefers_canonical_features_and_source_metadata(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        self.assertIn("const canonical = metadata.sense_metadata || {};", flashcards)
        self.assertIn("canonical.source_metadata || metadata.sense_provider_metadata", flashcards)
        self.assertIn("Array.isArray(canonical.features)", flashcards)

    def test_legacy_string_parsing_is_only_a_pre_contract_compatibility_path(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        self.assertIn("canonical.contract_version ? [] : projectWiktionaryGloss", flashcards)
        self.assertIn("if (!canonical.contract_version", flashcards)


if __name__ == "__main__":
    unittest.main()
