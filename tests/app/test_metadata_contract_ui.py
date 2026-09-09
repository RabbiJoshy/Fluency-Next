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

    def test_inactive_wiktionary_subsenses_use_clean_navigation_labels(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        styles = (APP_ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("function displaySenseGloss(meaning, value, active = true)", flashcards)
        self.assertIn("return senseSummaryText(projected) || projected;", flashcards)
        self.assertIn('class="sense-metadata-detail"', flashcards)
        self.assertIn(".sense-metadata-detail + .sense-metadata-detail::before", styles)
        self.assertIn("group-card-varying-cell${isMemberSelected ? ' is-active-subsense' : ''}", flashcards)
        self.assertIn(".group-card-varying-cell:not(.is-active-subsense)", styles)
        self.assertIn(".meaning-row-regular:not(.is-current-sense)", styles)


if __name__ == "__main__":
    unittest.main()
