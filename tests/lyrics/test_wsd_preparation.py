import unittest

from fluency.lyrics.wsd import LyricsWSDPreparationError, build_wsd_request_records


CONTENT_ID = "sha256:" + "1" * 64
MENU_ID = "sha256:" + "2" * 64


def candidate(index: int, status: str, analyses: list[dict] | None = None) -> dict:
    analyses = [] if analyses is None else analyses
    return {
        "analysis_unit_id": f"unit_{index:032x}",
        "occurrence_id": f"occurrence_{index:032x}",
        "surface_card_id": "card_es_" + f"{index:032x}",
        "surface_form": "Arriba" if index == 1 else "Yeh",
        "status": status,
        "lexical_candidate_id": f"lexical_{index:032x}",
        "lookup_card_id": "card_es_" + f"{index + 10:032x}" if status == "ready" else None,
        "lookup_form": "arriba" if status == "ready" else None,
        "menu_analysis_ids": [analysis["menu_analysis_id"] for analysis in analyses],
        "menu_analysis_count": len(analyses),
        "menu_sense_count": sum(len(analysis["senses"]) for analysis in analyses),
        "input_artifact_ids": [CONTENT_ID],
    }


class LyricsWSDPreparationTests(unittest.TestCase):
    def inputs(self):
        line = {
            "line_id": "line_" + "a" * 32,
            "song_id": "song_" + "b" * 32,
            "text": "Arriba Yeh",
        }
        occurrences = [
            {"occurrence_id": f"occurrence_{1:032x}", "line_id": line["line_id"], "surface": "Arriba", "span": [0, 6]},
            {"occurrence_id": f"occurrence_{2:032x}", "line_id": line["line_id"], "surface": "Yeh", "span": [7, 10]},
        ]
        units = [
            {"analysis_unit_id": f"unit_{1:032x}", "occurrence_id": occurrences[0]["occurrence_id"], "normalized_form": "arriba"},
            {"analysis_unit_id": f"unit_{2:032x}", "occurrence_id": occurrences[1]["occurrence_id"], "normalized_form": "yeh"},
        ]
        alignments = [{
            "alignment_id": "alignment_fixture",
            "line_id": line["line_id"],
            "target": {"language": "en", "text": "Up, yeah"},
            "source": {"snapshot_content_id": CONTENT_ID},
        }]
        analyses = [{"menu_analysis_id": "analysis_" + "c" * 32, "senses": [{"sense_id": "1"}]}]
        candidates = [candidate(1, "ready", analyses), candidate(2, "ineligible")]
        sense_menu = {"cards": [{
            "card_id": candidates[0]["lookup_card_id"],
            "analyses": analyses,
        }]}
        return [line], alignments, occurrences, units, candidates, sense_menu

    def test_preparation_covers_executable_and_non_executable_targets(self):
        lines, alignments, occurrences, units, candidates, sense_menu = self.inputs()
        requests, events, report = build_wsd_request_records(
            run_id="fixture-run",
            language="es",
            lines=lines,
            alignments=alignments,
            occurrences=occurrences,
            units=units,
            lexical_candidates=candidates,
            sense_menu=sense_menu,
            sense_menu_content_id=MENU_ID,
            input_artifact_ids=[CONTENT_ID],
        )
        self.assertEqual([request["eligibility"] for request in requests], ["ready", "ineligible"])
        self.assertEqual(requests[0]["context"]["target_span"], [0, 6])
        self.assertEqual(requests[0]["context"]["translation"]["text"], "Up, yeah")
        self.assertEqual(requests[0]["menu_reference"]["analysis_count"], 1)
        self.assertIsNone(requests[1]["menu_reference"])
        self.assertEqual(len(events), 2)
        self.assertEqual(report["execution_status"], "not_run")
        self.assertEqual(report["executable_request_count"], 1)

    def test_missing_translation_is_valid_but_span_drift_fails(self):
        lines, _alignments, occurrences, units, candidates, sense_menu = self.inputs()
        requests, _events, report = build_wsd_request_records(
            run_id="fixture-run",
            language="es",
            lines=lines,
            alignments=[],
            occurrences=occurrences,
            units=units,
            lexical_candidates=candidates,
            sense_menu=sense_menu,
            sense_menu_content_id=MENU_ID,
            input_artifact_ids=[CONTENT_ID],
        )
        self.assertIsNone(requests[0]["context"]["translation"])
        self.assertEqual(report["translation_available_count"], 0)
        occurrences[0]["span"] = [1, 6]
        with self.assertRaises(LyricsWSDPreparationError):
            build_wsd_request_records(
                run_id="fixture-run", language="es", lines=lines, alignments=[],
                occurrences=occurrences, units=units, lexical_candidates=candidates,
                sense_menu=sense_menu,
                sense_menu_content_id=MENU_ID, input_artifact_ids=[CONTENT_ID],
            )


if __name__ == "__main__":
    unittest.main()
