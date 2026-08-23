import unittest

from fluency.core.hashing import canonical_content_id
from fluency.core.identity import build_card_id, create_card_record
from fluency.lyrics.lexical import build_lexical_candidate_records


INPUT_ID = "sha256:" + "1" * 64
SNAPSHOT_ID = "sha256:" + "2" * 64


def unit(index: int, surface: str, normalized: str | None = None) -> dict:
    normalized = surface.lower() if normalized is None else normalized
    return {
        "analysis_unit_id": f"unit_{index:032x}",
        "occurrence_id": f"occurrence_{index:032x}",
        "source_surface": surface,
        "normalized_form": normalized,
    }


def route(index: int, *, status: str, bucket: str, target: str | None = None) -> dict:
    return {
        "analysis_unit_id": f"unit_{index:032x}",
        "route_id": f"route_{index:032x}",
        "status": status,
        "bucket": bucket,
        "target": target,
        "input_artifact_ids": [INPUT_ID],
    }


def menu(language: str, provider: str, cards: list[dict]) -> dict:
    return {
        "language": language,
        "source_adapter": provider,
        "source_edition": "fixture-edition",
        "snapshot_id": "fixture-snapshot",
        "snapshot_content_id": SNAPSHOT_ID,
        "gloss_language": "en",
        "cards": cards,
    }


def menu_card(language: str, surface: str, headword: str, pos: str) -> dict:
    card = create_card_record(language, surface).to_dict()
    analysis_key = f"{headword}:{pos}"
    return {
        **card,
        "surface_form": surface,
        "analyses": [{
            "menu_analysis_id": "analysis_" + canonical_content_id(analysis_key).removeprefix("sha256:")[:32],
            "headword": headword,
            "part_of_speech": pos,
            "source_analysis_key": analysis_key,
            "senses": [{
                "sense_id": "1",
                "translation": "fixture translation",
                "definition": "fixture definition",
                "source_reference": f"fixture:{headword}:1",
                "provider_metadata": {},
            }],
            "provider_metadata": {},
        }],
    }


class LyricsLexicalCandidateTests(unittest.TestCase):
    def test_spanishdict_and_wiktionary_share_one_nullable_contract(self):
        fixtures = (
            ("es", "spanishdict-snapshot-v1", "está", "estar", "VERB"),
            ("fr", "kaikki-jsonl-v1", "amour", "amour", "noun"),
        )
        for language, provider, surface, headword, pos in fixtures:
            with self.subTest(provider=provider):
                records, events, report = build_lexical_candidate_records(
                    run_id="fixture-run",
                    language=language,
                    units=[unit(1, surface)],
                    routes=[route(1, status="classified", bucket="classifier.normal_vocab")],
                    menu=menu(language, provider, [menu_card(language, surface, headword, pos)]),
                    process_input_ids=[INPUT_ID],
                )
                self.assertEqual(records[0]["status"], "ready")
                self.assertEqual(records[0]["menu_analysis_count"], 1)
                self.assertEqual(records[0]["menu_sense_count"], 1)
                self.assertNotIn("analyses", records[0])
                self.assertEqual(events[0]["operation"], "lookup")
                self.assertEqual(report["wsd_status"], "not_run")

    def test_route_target_is_lookup_metadata_not_surface_identity(self):
        records, _events, _report = build_lexical_candidate_records(
            run_id="fixture-run",
            language="es",
            units=[unit(1, "Líbrame", "líbrame")],
            routes=[route(1, status="classified", bucket="clitic_merge", target="librar")],
            menu=menu("es", "spanishdict-snapshot-v1", [menu_card("es", "librar", "librar", "VERB")]),
            process_input_ids=[INPUT_ID],
        )
        record = records[0]
        self.assertEqual(record["surface_card_id"], build_card_id("es", "líbrame"))
        self.assertEqual(record["lookup_card_id"], build_card_id("es", "librar"))
        self.assertNotEqual(record["surface_card_id"], record["lookup_card_id"])

    def test_missing_menus_and_non_lexical_routes_remain_visible(self):
        records, events, report = build_lexical_candidate_records(
            run_id="fixture-run",
            language="es",
            units=[unit(1, "jerga"), unit(2, "yeh"), unit(3, "Dios")],
            routes=[
                route(1, status="unresolved", bucket="sense_discovery"),
                route(2, status="excluded", bucket="exclude.noise"),
                route(3, status="review", bucket="review.proper_noun_candidate"),
            ],
            menu=menu("es", "spanishdict-snapshot-v1", []),
            process_input_ids=[INPUT_ID],
        )
        self.assertEqual([record["status"] for record in records], ["no_menu", "ineligible", "review"])
        self.assertEqual(records[0]["lookup_form"], "jerga")
        self.assertIn("provider_menu_unavailable", records[0]["reason_codes"])
        self.assertIsNone(records[1]["lookup_form"])
        self.assertIsNone(records[2]["lookup_form"])
        self.assertEqual([event["operation"] for event in events], ["lookup", "abstain", "abstain"])
        self.assertEqual(report["candidate_count"], 3)


if __name__ == "__main__":
    unittest.main()
