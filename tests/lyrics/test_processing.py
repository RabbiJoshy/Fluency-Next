import json
from pathlib import Path
import tempfile
import unittest

from fluency.lyrics.languages.spanish import SpanishLyricsAdapter
from fluency.lyrics.process import _scan_tokens
from fluency.lyrics.routing import RoutingSnapshot


class LyricsProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.elisions = root / "elisions.json"
        self.elisions.write_text(
            json.dumps(
                [
                    {
                        "elided_word": "estamo'",
                        "target_word": "estamos",
                        "action": "merge",
                        "merge_type": "elision_pair",
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.multi = root / "multi.json"
        self.multi.write_text(
            json.dumps({"entries": {"pa'l": ["para", "el"]}}),
            encoding="utf-8",
        )
        self.forms = root / "forms.json"
        self.forms.write_text(
            json.dumps(["dios", "dion", "lado", "estamos", "para", "el"]),
            encoding="utf-8",
        )
        self.frequency = root / "frequency.txt"
        self.frequency.write_text("dios 1000\ndion 1\n", encoding="utf-8")
        self.register = root / "register.json"
        self.register.write_text(
            json.dumps({"mai": {"word": "mai", "lemma": "mai"}, "dio": {"word": "dio", "lemma": "dar"}}),
            encoding="utf-8",
        )
        self.adapter = SpanishLyricsAdapter(
            elision_mapping=self.elisions,
            multi_word_elisions=self.multi,
            known_forms=self.forms,
            frequency_snapshot=self.frequency,
            lexeme_register=self.register,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_unicode_tokenizer_retains_lyrics_apostrophes_and_spans(self):
        text = "Porque estamo' arriba — 'Tamo bien"
        tokens = _scan_tokens(text)
        self.assertEqual(
            [surface for surface, _start, _end in tokens],
            ["Porque", "estamo'", "arriba", "'Tamo", "bien"],
        )
        for surface, start, end in tokens:
            self.assertEqual(text[start:end], surface)

    def test_spanish_adapter_restores_without_overwriting_valid_slang(self):
        self.assertEqual(
            self.adapter.normalize("'Tamo", previous=None, following="arriba")[0].form,
            "estamos",
        )
        self.assertEqual(
            [unit.form for unit in self.adapter.normalize("pa'l", previous=None, following=None)],
            ["para", "el"],
        )
        self.assertEqual(
            self.adapter.normalize("la'o", previous=None, following=None)[0].form,
            "lado",
        )
        self.assertEqual(
            self.adapter.normalize("Dio'", previous="y", following="sabe")[0].form,
            "dios",
        )
        self.assertEqual(
            self.adapter.normalize("mai'", previous="y", following="sabe")[0].form,
            "mai'",
        )

    def test_routing_snapshot_is_explicit_and_gracefully_unresolved(self):
        root = Path(self.temporary.name)
        path = root / "routing.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "exclude": {"noise": ["yeh"]},
                    "classifier": {"normal_vocab": ["arriba"]},
                    "derivation_map": {},
                    "sense_discovery": [],
                    "clitic_merge": {},
                }
            ),
            encoding="utf-8",
        )
        router = RoutingSnapshot(path)
        self.assertEqual(router.route("YEH")["bucket"], "exclude.noise")
        self.assertEqual(router.route("arriba")["status"], "classified")
        self.assertEqual(router.route("never-seen")["status"], "unresolved")


if __name__ == "__main__":
    unittest.main()
