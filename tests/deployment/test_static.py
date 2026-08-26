import json
from pathlib import Path
import tempfile
import unittest

from fluency.deployment.static import StaticDeploymentError, _validate_site


class StaticDeploymentTests(unittest.TestCase):
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
                json.dumps({"publicServices": {"spotifyClientId": "a" * 32}}),
                encoding="utf-8",
            )
            _validate_site(site, {"files": []})


if __name__ == "__main__":
    unittest.main()
