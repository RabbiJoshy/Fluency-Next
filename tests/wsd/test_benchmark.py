from pathlib import Path
import unittest

from fluency.wsd.benchmark import _pick_rows, _render_review


class WSDBenchmarkTests(unittest.TestCase):
    def _layers(self):
        inventory = []
        menus = []
        candidates = []
        bank = {}
        definitions = (
            (range(1, 41), "function_homograph", False),
            (range(61, 101), "inflected_multi_headword", True),
            (range(141, 181), "ordinary_multi_sense", False),
        )
        for ranks, _stratum, redirected in definitions:
            for rank in ranks:
                card_id = f"card_fr_{rank:032x}"
                sentence_id = f"sentence_{rank:032x}"
                surface = f"surface{rank}"
                inventory.append(
                    {"card_id": card_id, "rank": rank, "display_form": surface}
                )
                menus.append(
                    {
                        "card_id": card_id,
                        "surface_form": surface,
                        "analyses": [
                            {
                                "menu_analysis_id": f"analysis_{rank:032x}",
                                "headword": f"head{rank}",
                                "part_of_speech": "verb",
                                "provider_metadata": {
                                    "resolution": "redirected" if redirected else "direct",
                                    "resolution_path": [surface, f"head{rank}"],
                                },
                                "senses": [
                                    {
                                        "sense_id": f"sense-{rank}-a",
                                        "translation": "first",
                                        "definition": "",
                                        "source_reference": "fixture:a",
                                        "provider_metadata": {"tags": [], "topics": [], "examples": []},
                                    },
                                    {
                                        "sense_id": f"sense-{rank}-b",
                                        "translation": "second",
                                        "definition": "",
                                        "source_reference": "fixture:b",
                                        "provider_metadata": {"tags": [], "topics": [], "examples": []},
                                    },
                                ],
                            }
                        ],
                    }
                )
                candidates.append(
                    {
                        "card_id": card_id,
                        "candidates": [
                            {"sentence_id": sentence_id, "metrics": {"score": 0.0}}
                        ],
                    }
                )
                bank[sentence_id] = {
                    "sentence_id": sentence_id,
                    "source": {"attribution": "fixture"},
                    "target": {"text": f"Une phrase {surface}.", "source_sentence_id": str(rank), "contributor": "fr"},
                    "translation": {"text": "A sentence.", "source_sentence_id": str(rank + 1000), "contributor": "en"},
                }
        return inventory, menus, candidates, bank

    def test_selects_exactly_forty_unique_cards_per_stratum(self) -> None:
        layers = self._layers()
        first = _pick_rows(*layers, per_stratum=40)
        second = _pick_rows(*layers, per_stratum=40)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 120)
        self.assertEqual(len({row["card"]["card_id"] for row in first}), 120)
        counts = {
            name: sum(row["stratum"] == name for row in first)
            for name in (
                "function_homograph",
                "inflected_multi_headword",
                "ordinary_multi_sense",
            )
        }
        self.assertEqual(set(counts.values()), {40})

    def test_review_embeds_the_exact_prediction_blind_payload(self) -> None:
        benchmark = {
            "benchmark_id": "sha256:" + "a" * 64,
            "prediction_blind": True,
            "rows": [],
        }
        template = Path(
            Path(__file__).resolve().parents[2] / "src/fluency/wsd/review.template.html"
        ).read_text(encoding="utf-8")
        rendered = _render_review(template, benchmark)
        self.assertNotIn("__BENCHMARK_JSON__", rendered)
        self.assertIn('"prediction_blind":true', rendered)
        self.assertIn("Export labels.json", rendered)


if __name__ == "__main__":
    unittest.main()
