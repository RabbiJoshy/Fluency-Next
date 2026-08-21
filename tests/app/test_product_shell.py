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
            "welcome-screen",
            "language-dialog",
            "setup-view",
            "study-view",
            "flashcard",
            "diagnostics-dialog",
        ):
            self.assertIn(f'id="{required_id}"', html)
        self.assertNotIn("Merge Lemmas", html)
        self.assertNotIn("service-worker", html)
        self.assertNotIn("spotify", html.lower())

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
