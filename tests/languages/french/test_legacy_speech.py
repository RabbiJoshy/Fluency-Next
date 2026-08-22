import json
from pathlib import Path
import tempfile
import unittest

from fluency.languages.french.legacy_speech import build_legacy_french_deck
from fluency.release.validation import validate_deck
from fluency.sources.legacy.split_speech import load_legacy_split_speech


def _write_source(root: Path) -> tuple[Path, Path]:
    index = [
        {
            "word": "est",
            "lemma": "être",
            "id": "old001",
            "corpus_count": 100,
            "meanings": [
                {"pos": "VERB", "translation": "to be", "source": "wiktionary", "assignment_method": "keyword"}
            ],
        },
        {
            "word": "bonjour",
            "lemma": "bonjour",
            "id": "old002",
            "corpus_count": 80,
            "meanings": [
                {"pos": "INTJ", "translation": "hello", "source": "wiktionary"}
            ],
        },
        {
            "word": "est",
            "lemma": "est",
            "id": "old003",
            "corpus_count": 2,
            "meanings": [
                {"pos": "ADJ", "translation": "east", "source": "wiktionary"},
                {"pos": "VERB", "translation": "to be", "source": "wiktionary", "assignment_method": "keyword"},
            ],
        },
    ]
    examples = {
        "old001": {
            "m": [[{"target": "Il est ici.", "english": "He is here.", "source": "tatoeba", "assignment_method": "keyword"}]]
        },
        "old003": {
            "m": [
                [{"target": "Il regarde vers l’est.", "english": "He looks east.", "source": "tatoeba"}],
                [{"target": "Il est ici.", "english": "He is here.", "source": "tatoeba", "assignment_method": "keyword"}],
            ]
        },
    }
    index_path = root / "index.json"
    examples_path = root / "examples.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    examples_path.write_text(json.dumps(examples, ensure_ascii=False), encoding="utf-8")
    return index_path, examples_path


class LegacyFrenchSpeechTests(unittest.TestCase):
    def test_surface_merge_preserves_senses_assignments_and_missing_examples(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            index_path, examples_path = _write_source(Path(temporary))
            source = load_legacy_split_speech(index_path, examples_path)
            deck, summary, rejections = build_legacy_french_deck(source)

        self.assertEqual([card["surface_key"] for card in deck["cards"]], ["est", "bonjour"])
        est, bonjour = deck["cards"]
        self.assertEqual(est["rank"], 1)
        self.assertEqual(est["frequency"]["primary_count"], 100)
        self.assertEqual(est["frequency"]["aggregate_count"], 102)
        self.assertEqual(len(est["legacy_aliases"]), 2)
        self.assertEqual(len(est["meanings"]), 2)
        self.assertEqual(len(est["examples"]), 2)
        self.assertEqual(len(est["meanings"][0]["legacy_sources"]), 2)
        self.assertEqual(len(est["examples"][0]["legacy_sources"]), 2)
        self.assertEqual(bonjour["examples"], [])
        self.assertEqual(summary["legacy_rows"], 3)
        self.assertEqual(summary["surface_cards"], 2)
        self.assertEqual(summary["deduplicated_meanings"], 1)
        self.assertEqual(summary["deduplicated_examples"], 1)
        self.assertEqual(summary["cards_without_examples"], 1)
        self.assertEqual(rejections, [])
        validate_deck(deck)

    def test_reader_rejects_misaligned_meaning_buckets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            index_path, examples_path = _write_source(Path(temporary))
            examples = json.loads(examples_path.read_text(encoding="utf-8"))
            examples["old003"]["m"].pop()
            examples_path.write_text(json.dumps(examples), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "meanings/examples disagree"):
                load_legacy_split_speech(index_path, examples_path)


if __name__ == "__main__":
    unittest.main()
