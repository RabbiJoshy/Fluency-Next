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
