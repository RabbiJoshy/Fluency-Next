import unittest

from fluency.core.identity import create_card_record
from fluency.speech.wsd_execute import build_analyses
from fluency.wsd.menus import (
    MenuAnalysis,
    SenseLeaf,
    build_analysis_id,
    require_analysis,
)


def analysis(card_id: str, source_key: str, headword: str) -> MenuAnalysis:
    return MenuAnalysis(
        menu_analysis_id=build_analysis_id(
            card_id=card_id,
            source_adapter="wiktionary-sense-menu/v1",
            source_analysis_key=source_key,
        ),
        card_id=card_id,
        surface_form="suis",
        headword=headword,
        part_of_speech="verb",
        source_adapter="wiktionary-sense-menu/v1",
        source_analysis_key=source_key,
        senses=(SenseLeaf(source_key, "to be", "", f"kaikki:{source_key}", {}),),
        provider_metadata={},
    )


class MenuIdentityTests(unittest.TestCase):
    def test_analysis_identity_is_deterministic_and_source_scoped(self) -> None:
        card_id = create_card_record("fr", "suis").card_id
        first = analysis(card_id, "être:verb", "être")
        repeated = analysis(card_id, "être:verb", "être")
        other = analysis(card_id, "suivre:verb", "suivre")
        self.assertEqual(first.menu_analysis_id, repeated.menu_analysis_id)
        self.assertNotEqual(first.menu_analysis_id, other.menu_analysis_id)

    def test_resolution_never_falls_back_to_first_analysis(self) -> None:
        card_id = create_card_record("fr", "suis").card_id
        analyses = (
            analysis(card_id, "être:verb", "être"),
            analysis(card_id, "suivre:verb", "suivre"),
        )
        with self.assertRaises(KeyError):
            require_analysis(analyses, "analysis_" + "0" * 32)

    def test_source_adapter_survives_menu_serialization_and_reconstruction(self) -> None:
        card_id = create_card_record("fr", "suis").card_id
        original = analysis(card_id, "être:verb", "être")
        serialized = original.to_dict()
        self.assertEqual(serialized["source_adapter"], "wiktionary-sense-menu/v1")

        rebuilt = build_analyses(
            {
                "card_id": card_id,
                "surface_form": "suis",
                "analyses": [serialized],
            },
            menu_source_adapter="spanishdict-sense-menu/v1",
        )
        self.assertEqual(rebuilt[0].source_adapter, "wiktionary-sense-menu/v1")
        self.assertEqual(rebuilt[0].menu_analysis_id, original.menu_analysis_id)

    def test_legacy_analysis_uses_the_menu_adapter_not_a_spanishdict_default(self) -> None:
        card_id = create_card_record("fr", "suis").card_id
        original = analysis(card_id, "être:verb", "être")
        serialized = original.to_dict()
        del serialized["source_adapter"]

        rebuilt = build_analyses(
            {
                "card_id": card_id,
                "surface_form": "suis",
                "analyses": [serialized],
            },
            menu_source_adapter="wiktionary-sense-menu/v1",
        )
        self.assertEqual(rebuilt[0].source_adapter, "wiktionary-sense-menu/v1")
        self.assertEqual(rebuilt[0].menu_analysis_id, original.menu_analysis_id)


if __name__ == "__main__":
    unittest.main()
