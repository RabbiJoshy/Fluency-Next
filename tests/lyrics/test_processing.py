import json
from pathlib import Path
import tempfile
import unittest

from fluency.lyrics.languages.spanish import SpanishLyricsAdapter
from fluency.lyrics.languages.spanish_routing import SpanishLiveRouter
from fluency.lyrics.overrides import RoutingOverrideError, RoutingOverrideRegistry
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

    def test_live_spanish_router_recomputes_decisions_from_pinned_inputs(self):
        root = Path(self.temporary.name)

        def write(name, value):
            path = root / name
            path.write_text(json.dumps(value), encoding="utf-8")
            return path

        known = write(
            "routing-forms.json",
            {"a": "letter", "dios": "name,noun", "eh": "intj", "madrid": "name", "líbrame": "verb", "librar": "verb", "video": "noun"},
        )
        spanish_frequency = root / "spanish-frequency.txt"
        spanish_frequency.write_text("librar 100\nvideo 50\n", encoding="utf-8")
        english_frequency = root / "english-frequency.txt"
        english_frequency.write_text("baby 100\nvideo 90\n", encoding="utf-8")
        router = SpanishLiveRouter(
            known_forms=known,
            spanish_frequency=spanish_frequency,
            english_frequency=english_frequency,
            english_loanwords=write("loanwords.json", {}),
            conjugation_reverse=write(
                "reverse.json",
                {"libra": [{"lemma": "librar", "mood": "imperativo", "person": "2s"}]},
            ),
            caps_stats=write(
                "caps.json",
                {"dios": {"total": 10, "firstcap": 1, "cap_rate": 0.9}},
            ),
            elision_mapping=write("routing-elisions.json", []),
        )
        self.assertEqual(router.route("brrr")["bucket"], "exclude.noise")
        self.assertEqual(router.route("baby")["bucket"], "exclude.english")
        self.assertEqual(router.route("Dios")["bucket"], "review.proper_noun_candidate")
        self.assertEqual(router.route("Madrid")["bucket"], "exclude.proper_nouns")
        self.assertEqual(router.route("eh")["bucket"], "classifier.spoken_particle")
        self.assertEqual(router.route("video")["bucket"], "classifier.normal_vocab")
        self.assertEqual(router.route("líbrame")["target"], "librar")
        self.assertEqual(router.route("new-slang")["bucket"], "sense_discovery")
        self.assertGreater(len(router.route("new-slang")["policy_trace"]), 5)

    def test_typed_overrides_are_scoped_attributable_and_conflict_intolerant(self):
        root = Path(self.temporary.name)
        registry_path = root / "overrides.json"
        entry = {
            "override_id": "es.bad-bunny.fium.v1",
            "status": "active",
            "language": "es",
            "normalized_form": "fium",
            "decision": {"status": "review", "bucket": "sense_discovery", "target": None},
            "reason": "Audit as possible artist slang instead of silently dropping it.",
            "author": "JSTA",
            "created_at": "2026-08-23T12:00:00Z",
            "scope": {"modes": ["lyrics"], "artist_ids": ["bad-bunny"], "song_ids": []},
        }
        registry_path.write_text(
            json.dumps({"schema_version": "lyrics-routing-overrides/v1", "entries": [entry]}),
            encoding="utf-8",
        )
        registry = RoutingOverrideRegistry(
            registry_path,
            language="es",
            mode="lyrics",
            artist_id="bad-bunny",
            song_id="6855744",
        )
        self.assertEqual(registry.match("FIUM")["author"], "JSTA")
        self.assertIsNone(
            RoutingOverrideRegistry(
                registry_path,
                language="es",
                mode="lyrics",
                artist_id="rosalia",
                song_id="6855744",
            ).match("fium")
        )
        registry_path.write_text(
            json.dumps({"schema_version": "lyrics-routing-overrides/v1", "entries": [entry, {**entry, "override_id": "es.bad-bunny.fium.v2"}]}),
            encoding="utf-8",
        )
        conflicting = RoutingOverrideRegistry(
            registry_path,
            language="es",
            mode="lyrics",
            artist_id="bad-bunny",
            song_id="6855744",
        )
        with self.assertRaises(RoutingOverrideError):
            conflicting.match("fium")


if __name__ == "__main__":
    unittest.main()
