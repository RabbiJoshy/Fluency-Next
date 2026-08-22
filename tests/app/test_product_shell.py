import json
from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPOSITORY_ROOT / "app"


class ProductShellTests(unittest.TestCase):
    def test_language_registry_is_multilingual_and_french_is_runnable(self) -> None:
        registry = json.loads(
            (APP_ROOT / "config" / "languages.json").read_text(encoding="utf-8")
        )
        languages = {item["key"]: item for item in registry["languages"]}

        self.assertEqual(registry["registry_version"], "language-registry/v1")
        self.assertEqual(set(languages), {"fr", "es", "nl", "pt"})
        self.assertEqual(languages["fr"]["locale"], "fr-FR")
        self.assertEqual(languages["fr"]["status"], "pilot")
        self.assertIn("artist", languages["es"]["modes"])
        self.assertIn("artist", languages["pt"]["modes"])

    def test_html_keeps_product_surface_without_legacy_boot_coupling(self) -> None:
        html = (APP_ROOT / "index.html").read_text(encoding="utf-8")

        for required_id in (
            "authModal",
            "languageTabs",
            "setupPanel",
            "appContent",
            "flashcard",
            "deckProgressSegments",
        ):
            self.assertIn(f'id="{required_id}"', html)
        self.assertIn('src="src/boot.js"', html)
        self.assertNotIn('src="js/main.js', html)
        self.assertNotIn("spotify-player.js", html)

    def test_pilot_html_is_preserved_as_a_readable_reference(self) -> None:
        reference = REPOSITORY_ROOT / "docs" / "reference" / "pilot-ui-v1.html"
        self.assertTrue(reference.is_file())
        self.assertIn('id="welcome-screen"', reference.read_text(encoding="utf-8"))

    def test_release_runtime_exposes_exact_candidate_and_layer_provenance(self) -> None:
        client = (APP_ROOT / "src" / "core" / "release-client.js").read_text(encoding="utf-8")
        boot = (APP_ROOT / "src" / "boot.js").read_text(encoding="utf-8")
        self.assertIn("release-catalog/v1", client)
        self.assertIn("composition_content_id", client)
        self.assertIn("Release & layer audit", boot)
        self.assertIn("composition.layers", boot)

    def test_card_data_inspector_is_example_first_and_complete(self) -> None:
        inspector = (
            APP_ROOT / "src" / "features" / "diagnostics" / "card-data-inspector.js"
        ).read_text(encoding="utf-8")
        options = (
            APP_ROOT / "src" / "features" / "study" / "study-options.js"
        ).read_text(encoding="utf-8")

        self.assertIn("Inspect example", inspector)
        self.assertIn("Complete recorded metadata", inspector)
        self.assertIn('flattenMetadata(example || {}, "example")', inspector)
        self.assertIn('layerSummary(release.composition, "wsd_assignments")', inspector)
        self.assertIn("Full sense menu", inspector)
        self.assertIn("Card Data", options)

    def test_set_lifecycle_keeps_learn_review_resume_and_completion_separate(self) -> None:
        boot = (APP_ROOT / "src" / "boot.js").read_text(encoding="utf-8")
        queues = (
            APP_ROOT / "src" / "features" / "study" / "study-queues.js"
        ).read_text(encoding="utf-8")
        sessions = (
            APP_ROOT / "src" / "services" / "study-session-store.js"
        ).read_text(encoding="utf-8")

        self.assertIn('queueType === "review"', queues)
        self.assertIn('progress.status(cardId) === "unseen"', queues)
        self.assertIn("study-session/v1", sessions)
        self.assertIn("Continue where you stopped?", boot)
        self.assertIn("Review Complete!", boot)
        self.assertIn("restartAllBtn", boot)
        self.assertNotIn("Review mistakes", boot)

    def test_language_selection_advances_and_can_be_reopened(self) -> None:
        boot = (APP_ROOT / "src" / "boot.js").read_text(encoding="utf-8")
        self.assertIn('button.addEventListener("click", () => selectLanguage(language))', boot)
        self.assertIn('levelStep.style.display = "block"', boot)
        self.assertIn('setStep.style.display = "block"', boot)
        self.assertIn('sourceLanguageButton.addEventListener("click", openLanguageChooser)', boot)

    def test_all_relative_module_imports_resolve(self) -> None:
        import_pattern = re.compile(r'^import\s+.*?from\s+["\'](.+?)["\'];?$', re.MULTILINE)
        for module in (APP_ROOT / "src").rglob("*.js"):
            for target in import_pattern.findall(module.read_text(encoding="utf-8")):
                if not target.startswith("."):
                    continue
                resolved = (module.parent / target).resolve()
                with self.subTest(module=module.name, target=target):
                    self.assertTrue(resolved.is_file())

    def test_runtime_has_no_global_mutable_state_bridge(self) -> None:
        scripts = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((APP_ROOT / "src").rglob("*.js"))
        )
        self.assertNotIn("globalThis", scripts)
        self.assertNotIn("window.state", scripts)
        self.assertNotIn("latest.json", scripts)


if __name__ == "__main__":
    unittest.main()
