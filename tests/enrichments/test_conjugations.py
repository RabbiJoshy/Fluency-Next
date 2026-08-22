import json
from pathlib import Path
import tempfile
import unittest

from fluency.core.artifacts import artifact_directory, verify_artifact
from fluency.core.workspace import Workspace
from fluency.enrichments.conjugations import (
    ConjugationLayerError,
    build_conjugation_layer,
    pin_jehle_snapshot,
)


CSV = """infinitive,infinitive_english,mood,mood_english,tense,tense_english,verb_english,form_1s,form_2s,form_3s,form_1p,form_2p,form_3p,gerund,gerund_english,pastparticiple,pastparticiple_english
hablar,to speak,Indicativo,Indicative,Presente,Present,I speak,hablo,hablas,habla,hablamos,habláis,hablan,hablando,speaking,hablado,spoken
hablar,to speak,Subjuntivo,Subjunctive,Presente,Present,that I speak,hable,hables,hable,hablemos,habléis,hablen,hablando,speaking,hablado,spoken
"""


class ConjugationLayerTests(unittest.TestCase):
    def test_pins_source_and_builds_only_requested_verb_headwords(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = Workspace.initialize(root / "workspace")
            source = root / "jehle.csv"
            source.write_text(CSV, encoding="utf-8")
            snapshot = pin_jehle_snapshot(
                workspace,
                source=source,
                snapshot_id="jehle-test-v1",
            )
            menu = root / "sense-menu.json"
            menu.write_text(json.dumps({
                "menu_version": "sense-menu/v1",
                "language": "es",
                "snapshot_id": "menu-test-v1",
                "cards": [{
                    "card_id": "card_es_1234567890abcdef",
                    "surface_form": "hablo",
                    "analyses": [
                        {"headword": "hablar", "part_of_speech": "VERB"},
                        {"headword": "hablo", "part_of_speech": "NOUN"},
                    ],
                }],
            }), encoding="utf-8")

            metadata, coverage = build_conjugation_layer(
                workspace,
                sense_menu=menu,
                source_snapshot=snapshot,
            )

            self.assertEqual(coverage, {
                "requested_headwords": 1,
                "covered_headwords": 1,
                "missing_headwords": [],
            })
            self.assertEqual(verify_artifact(workspace, metadata.artifact_id), metadata)
            payload = json.loads((artifact_directory(workspace, metadata.artifact_id) / metadata.filename).read_text())
            self.assertEqual(payload["join_key"], "headword")
            self.assertEqual(payload["records"][0]["headword"], "hablar")
            self.assertEqual(payload["records"][0]["paradigms"][0]["forms"][0], {
                "person": "1s", "form": "hablo",
            })

    def test_rejects_duplicate_paradigms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = Workspace.initialize(root / "workspace")
            source = root / "jehle.csv"
            source.write_text(CSV + CSV.splitlines()[1] + "\n", encoding="utf-8")
            snapshot = pin_jehle_snapshot(workspace, source=source, snapshot_id="duplicate-v1")
            menu = root / "sense-menu.json"
            menu.write_text(json.dumps({
                "menu_version": "sense-menu/v1", "language": "es", "snapshot_id": "m",
                "cards": [{"analyses": [{"headword": "hablar", "part_of_speech": "VERB"}]}],
            }), encoding="utf-8")
            with self.assertRaises(ConjugationLayerError):
                build_conjugation_layer(workspace, sense_menu=menu, source_snapshot=snapshot)


if __name__ == "__main__":
    unittest.main()
