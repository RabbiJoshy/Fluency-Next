import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.workspace import Workspace
from fluency.release.pilot import build_pilot_release, default_seed_path
from fluency.release.validation import validate_active_release, validate_release_bundle


class PilotReleaseTests(unittest.TestCase):
    def test_pilot_build_is_valid_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Workspace.initialize(Path(temporary) / "workspace")
            first = build_pilot_release(workspace)
            first_deck = (first / "deck.json").read_bytes()
            second = build_pilot_release(workspace)

            self.assertEqual(first, second)
            self.assertEqual(first_deck, (second / "deck.json").read_bytes())
            manifest, deck = validate_release_bundle(first)
            self.assertEqual(manifest["card_count"], 25)
            self.assertEqual(len(deck["cards"]), 25)
            self.assertEqual(len({card["card_id"] for card in deck["cards"]}), 25)

            active = json.loads(
                (workspace.root / "releases" / "fr" / "speech" / "active.json").read_text(
                    encoding="utf-8"
                )
            )
            validate_active_release(active)
            self.assertEqual(active["release_id"], manifest["release_id"])

    def test_existing_release_cannot_be_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            workspace = Workspace.initialize(temporary_root / "workspace")
            release_directory = build_pilot_release(workspace)
            (release_directory / "deck.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "immutable release"):
                build_pilot_release(workspace)

    def test_seed_contains_exactly_25_curated_cards(self) -> None:
        seed = json.loads(default_seed_path().read_text(encoding="utf-8"))
        self.assertEqual(len(seed["cards"]), 25)
        self.assertEqual(seed["release_id"], "fr-speech-pilot-0001")


if __name__ == "__main__":
    unittest.main()
