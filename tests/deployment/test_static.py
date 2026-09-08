import json
from pathlib import Path
import tempfile
import unittest

from fluency.deployment.static import StaticDeploymentError, _validate_site


class StaticDeploymentTests(unittest.TestCase):
    def test_release_urls_are_portable_app_relative_paths(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "src/fluency/deployment/static.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('base = f"releases/{language}/speech/{release_id}"', source)
        self.assertIn('lyrics_base = f"releases/lyrics/{lyrics_release_id}"', source)
        self.assertNotIn('base = f"/releases/{language}/speech/{release_id}"', source)

    def test_public_spotify_oauth_client_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            (site / "config").mkdir()
            (site / "index.html").write_text("", encoding="utf-8")
            (site / "service-worker.js").write_text("", encoding="utf-8")
            config_path = site / "config/config.json"
            config_path.write_text(json.dumps({"publicServices": {}}), encoding="utf-8")

            with self.assertRaisesRegex(StaticDeploymentError, "Spotify OAuth client ID"):
                _validate_site(site, {"files": []})

            config_path.write_text(
                json.dumps({
                    "publicServices": {
                        "spotifyClientId": "a" * 32,
                        "progressSyncUrl": "https://script.google.com/macros/s/test-deployment/exec",
                    }
                }),
                encoding="utf-8",
            )
            _validate_site(site, {"files": []})

    def test_public_progress_sync_url_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            (site / "config").mkdir()
            (site / "index.html").write_text("", encoding="utf-8")
            (site / "service-worker.js").write_text("", encoding="utf-8")
            config_path = site / "config/config.json"
            config_path.write_text(
                json.dumps({"publicServices": {"spotifyClientId": "a" * 32}}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(StaticDeploymentError, "progress sync URL"):
                _validate_site(site, {"files": []})


if __name__ == "__main__":
    unittest.main()


class CognateLayerStagingTests(unittest.TestCase):
    """Cognate scores travel beside the release, so the deployment has to stage
    them and the app config has to point at them."""

    def setUp(self) -> None:
        self.source = (
            Path(__file__).resolve().parents[2] / "src/fluency/deployment/static.py"
        ).read_text(encoding="utf-8")

    def test_the_mapping_is_keyed_by_language_not_by_release(self) -> None:
        # Scores are surface-keyed and do not expire when a deck changes, so
        # binding them to a release id would force a pointless rebuild every
        # time the deck moved and would silently drop the feature in between.
        self.assertIn(
            'workspace.root / "cognates" / language / "cognates.json"', self.source
        )
        self.assertNotIn('f"{release_id}.json"', self.source)

    def test_absence_turns_the_capability_off_rather_than_being_inferred(self) -> None:
        self.assertIn('language_config["cognatesPath"] = None', self.source)
        self.assertIn('"cognateFilter"] = False', self.source)

    def test_a_present_layer_is_copied_and_declared(self) -> None:
        self.assertIn('cognate_relative = f"cognates/{language}/cognates.json"', self.source)
        self.assertIn('"cognateFilter"] = True', self.source)


class ProgressSyncBackendTests(unittest.TestCase):
    """The sync URL is where every learner's progress is posted, so the check
    stays exact — but it has to know about the backend the app actually uses."""

    def _site(self, url: str) -> Path:
        directory = Path(tempfile.mkdtemp())
        (directory / "index.html").write_text("", encoding="utf-8")
        (directory / "service-worker.js").write_text("", encoding="utf-8")
        (directory / "config").mkdir()
        (directory / "config/config.json").write_text(
            json.dumps({"publicServices": {
                "spotifyClientId": "f2341f303cff471ea80d3fcdefbb6d7d",
                "progressSyncUrl": url,
            }}),
            encoding="utf-8",
        )
        return directory

    def test_the_cloudflare_worker_backend_is_accepted(self) -> None:
        # f54540b moved progress sync to the Worker and left this check on the
        # old Apps Script pattern, which blocked every deployment build.
        site = self._site("https://fluency-api.rabbijoshy.workers.dev")
        _validate_site(site, {"files": []})

    def test_the_previous_apps_script_backend_still_validates(self) -> None:
        site = self._site("https://script.google.com/macros/s/AKfycbwZI7L1gQ/exec")
        _validate_site(site, {"files": []})

    def test_an_arbitrary_url_is_still_refused(self) -> None:
        for url in ("https://example.com/collect", "http://fluency-api.rabbijoshy.workers.dev", ""):
            with self.subTest(url=url), self.assertRaises(StaticDeploymentError):
                _validate_site(self._site(url), {"files": []})


class MergeLemmaCapabilityTests(unittest.TestCase):
    """Decision 0011 hides Merge Lemmas when the release cannot support it. The
    shipped config declared it anyway, so the toggle appeared and did nothing."""

    def setUp(self) -> None:
        self.source = (
            Path(__file__).resolve().parents[2] / "src/fluency/deployment/static.py"
        ).read_text(encoding="utf-8")

    def test_the_capability_is_read_from_the_release_not_the_app_config(self) -> None:
        # Grouping is by the assigned sense's headword, which every deck the
        # current pipeline builds already carries.
        self.assertIn('meaning.get("headword")', self.source)
        self.assertIn('["mergeLemmas"] = merges_lemmas', self.source)
