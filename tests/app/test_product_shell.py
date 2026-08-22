import json
from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPOSITORY_ROOT / "app"


class ProductShellTests(unittest.TestCase):
    def test_existing_fluency_entrypoint_and_core_surfaces_are_present(self) -> None:
        html = (APP_ROOT / "index.html").read_text(encoding="utf-8")
        for required_id in (
            "authModal",
            "languageTabs",
            "setupPanel",
            "appContent",
            "flashcard",
            "deckProgressSegments",
            "cardBackScrubber",
            "settingsModal",
        ):
            self.assertIn(f'id="{required_id}"', html)
        self.assertIn('src="js/main.js?v=', html)
        self.assertNotIn('src="src/boot.js"', html)

    def test_complete_existing_runtime_module_set_is_transplanted(self) -> None:
        for filename in (
            "main.js",
            "state.js",
            "ui.js",
            "vocab.js",
            "flashcards.js",
            "progress.js",
            "knowledge.js",
            "speech.js",
            "auth.js",
            "theme.js",
            "data-contracts.js",
        ):
            self.assertTrue((APP_ROOT / "js" / filename).is_file(), filename)
        self.assertFalse((APP_ROOT / "src").exists())

    def test_abandoned_preview_and_csv_paths_are_removed(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (APP_ROOT / "js").glob("*.js")
        )
        self.assertFalse((APP_ROOT / "js" / "speech-vnext.js").exists())
        self.assertNotIn("speechVnext", combined)
        self.assertNotIn("loadCSVFiles", combined)

    def test_card_data_is_available_without_owner_login(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        self.assertIn("label: 'Card data'", flashcards)
        self.assertNotIn("if (!isJstOwner()) return null", flashcards)

    def test_only_languages_with_clean_releases_are_enabled(self) -> None:
        config = json.loads((APP_ROOT / "config" / "config.json").read_text(encoding="utf-8"))
        enabled = {
            key for key, value in config["languages"].items()
            if value.get("hasData", True)
        }
        self.assertEqual(enabled, {"french", "spanish"})
        self.assertEqual(
            config["languages"]["spanish"]["studyStructurePath"],
            "Data/Spanish/study-structure.json",
        )
        self.assertEqual(
            config["languages"]["spanish"]["releaseManifestPath"],
            "Data/Spanish/release-manifest.json",
        )
        self.assertEqual(
            config["languages"]["spanish"]["releaseCompositionPath"],
            "Data/Spanish/release-composition.json",
        )
        for legacy_path in (
            "conjugatedEnglishPath",
            "ppmDataPath",
        ):
            self.assertNotIn(legacy_path, config["languages"]["spanish"])
        self.assertEqual(
            config["languages"]["spanish"]["conjugationsPath"],
            "Data/Spanish/conjugations.json",
        )
        self.assertNotIn("ppmDataPath", config["languages"]["french"])
        self.assertEqual(
            config["languages"]["french"]["studyStructurePath"],
            "Data/French/study-structure.json",
        )
        self.assertFalse((APP_ROOT / "Data").exists())
        self.assertFalse((APP_ROOT / "Artists").exists())

    def test_surface_only_release_hides_legacy_lemma_control(self) -> None:
        ui = (APP_ROOT / "js" / "ui.js").read_text(encoding="utf-8")
        self.assertGreaterEqual(
            ui.count("lemmaFieldAvailable ? 'block' : 'none'"),
            2,
        )

    def test_active_set_keeps_existing_interaction_model(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        vocab = (APP_ROOT / "js" / "vocab.js").read_text(encoding="utf-8")
        for behavior in (
            "flipCard",
            "handleSwipeAction",
            "cycleExample",
            "showEndOfDeckOptions",
            "deckProgressSegments",
        ):
            self.assertIn(behavior, flashcards)
        self.assertIn('id="cardBackScrubber"', (APP_ROOT / "index.html").read_text(encoding="utf-8"))
        self.assertIn("saveStudySessionSnapshot", flashcards)
        self.assertIn("buildFocusedReviewCard", vocab)

    def test_unassigned_dictionary_menu_does_not_claim_wsd_confidence(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        css = (APP_ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("if (!m.unassigned)", flashcards)
        self.assertIn("hasAssignedEvidence", flashcards)
        self.assertIn("pos-pill-unassigned", flashcards)
        self.assertIn(".pos-collapsible .pos-pill-unassigned", css)

    def test_optional_conjugations_join_by_dictionary_headword_not_identity_lemma(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        self.assertIn(
            "currentMeaning?.headword || card.lemma || card.targetWord",
            flashcards,
        )
        self.assertIn("currentMeaning.cycle_pos", flashcards)

    def test_approved_numbered_scrubber_animation_is_retained(self) -> None:
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        css = (APP_ROOT / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("Numbered active-set scrubber", flashcards)
        self.assertIn("deck-scrubber-lens", css)
        self.assertIn(".deck-progress-segment.is-current", css)

    def test_active_release_aliases_are_never_cached(self) -> None:
        worker = (APP_ROOT / "service-worker.js").read_text(encoding="utf-8")
        self.assertIn("vocabulary\\.(?:index|examples)", worker)
        self.assertIn("study-structure", worker)
        self.assertIn("release-(?:manifest|composition)", worker)
        self.assertIn("conjugations", worker)
        self.assertIn("cache: 'no-store'", worker)

    def test_audit_accounts_and_flags_use_release_provenance(self) -> None:
        auth = (APP_ROOT / "js" / "auth.js").read_text(encoding="utf-8")
        modals = (APP_ROOT / "js" / "flashcards-modals.js").read_text(encoding="utf-8")
        config = json.loads((APP_ROOT / "config" / "config.json").read_text(encoding="utf-8"))
        self.assertIn("new Set(['JST', 'JSTA'])", auth)
        self.assertIn("provenanceJson: JSON.stringify(provenance)", auth)
        self.assertIn("flagId = createFlagId()", auth)
        self.assertIn("`flag|${flagId}`", auth)
        self.assertIn("schemaVersion: 4", auth)
        self.assertIn("function _flagRunProvenance", modals)
        self.assertIn("Release ID:", modals)
        self.assertEqual(
            config["languages"]["french"]["releaseManifestPath"],
            "Data/French/release-manifest.json",
        )

    def test_song_sets_retain_contributing_artist_slugs(self) -> None:
        song_sets = (APP_ROOT / "js" / "song-sets.js").read_text(encoding="utf-8")
        self.assertIn("function artistSlugsForSongs", song_sets)
        self.assertIn("artistSlugs,", song_sets)
        self.assertIn("remote.artistSlugs", song_sets)

    def test_language_switch_clears_source_scoped_runtime_data(self) -> None:
        ui = (APP_ROOT / "js" / "ui.js").read_text(encoding="utf-8")
        song_sets = (APP_ROOT / "js" / "song-sets.js").read_text(encoding="utf-8")
        flashcards = (APP_ROOT / "js" / "flashcards.js").read_text(encoding="utf-8")
        vocab = (APP_ROOT / "js" / "vocab.js").read_text(encoding="utf-8")
        self.assertIn("window.clearActiveExamplesData?.()", ui)
        self.assertIn("window.resetLanguageOptionalData?.()", ui)
        self.assertIn("export function clearActiveExamplesData", song_sets)
        self.assertIn("window._cachedExamplesDataPath = resolvedSource", song_sets)
        self.assertIn("function resetLanguageOptionalData", flashcards)
        self.assertIn("window._cachedExamplesDataPath !== langConfig.examplesPath", vocab)

    def test_pilot_interface_remains_a_readable_reference(self) -> None:
        reference = REPOSITORY_ROOT / "docs" / "reference" / "pilot-ui-v1.html"
        self.assertTrue(reference.is_file())
        self.assertIn('id="welcome-screen"', reference.read_text(encoding="utf-8"))

    def test_all_relative_module_imports_resolve(self) -> None:
        import_pattern = re.compile(r'^import\s+.*?(?:from\s+)?["\'](.+?)["\'];?$', re.MULTILINE)
        for module in (APP_ROOT / "js").glob("*.js"):
            for target in import_pattern.findall(module.read_text(encoding="utf-8")):
                if not target.startswith("."):
                    continue
                clean_target = target.split("?", 1)[0]
                resolved = (module.parent / clean_target).resolve()
                with self.subTest(module=module.name, target=target):
                    self.assertTrue(resolved.is_file())


if __name__ == "__main__":
    unittest.main()
