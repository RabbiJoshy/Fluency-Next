import json
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
        self.assertIn('class="sense-metadata-detail${overflow', flashcards)
        self.assertIn(".sense-metadata-detail + .sense-metadata-detail::before", styles)
        self.assertIn("group-card-varying-cell${isMemberSelected ? ' is-active-subsense' : ''}", flashcards)
        self.assertIn(".group-card-varying-cell:not(.is-active-subsense)", styles)
        self.assertIn(".meaning-row-regular:not(.is-current-sense)", styles)

    def test_active_metadata_is_ordered_compact_and_disclosable(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        styles = (APP_ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("const familyOrder = {", flashcards)
        self.assertIn("const visibleLimit = 3;", flashcards)
        self.assertIn("display.short", flashcards)
        self.assertIn("toggleSenseMetadataOverflow(event, this)", flashcards)
        self.assertIn("'gender=variable-by-person': 'varies by gender'", flashcards)
        self.assertIn(".sense-metadata-more", styles)

    def test_one_shared_metadata_renderer_serves_every_active_dictionary_language(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        config = json.loads((APP_ROOT / "config" / "config.json").read_text(encoding="utf-8"))
        gloss_renderer = flashcards[
            flashcards.index("function displaySenseGloss"):
            flashcards.index("function senseCrossReferences")
        ]
        metadata_renderer = flashcards[
            flashcards.index("function senseMetadataItems"):
            flashcards.index("function contextWithoutSenseMetadata")
        ]
        self.assertNotIn("selectedLanguage", gloss_renderer)
        self.assertNotIn("selectedLanguage", metadata_renderer)
        for language in ("portuguese", "french", "spanish", "czech"):
            with self.subTest(language=language):
                language_config = config["languages"][language]
                self.assertTrue(language_config["hasData"])
                self.assertTrue(language_config["indexPath"].endswith("vocabulary.index.json"))

    def test_cross_references_use_the_same_card_navigation_in_every_language(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        navigation = flashcards[
            flashcards.index("function senseCrossReferences"):
            flashcards.index("function condenseSenseContext")
        ]
        self.assertIn("openSenseCrossReference", navigation)
        self.assertIn("window.popupFoundWord", navigation)
        self.assertNotIn("selectedLanguage", navigation)


if __name__ == "__main__":
    unittest.main()
