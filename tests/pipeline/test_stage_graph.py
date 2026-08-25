"""The stage graph is a diamond, not a chain.

STAGE_ORDER is an execution sequence. Read as a dependency chain it implies
sentence_harvest needs sense_menu, which it does not -- both read only the
inventory. The declaration is asserted against what the runners actually open,
so it cannot drift into being decorative.
"""

from pathlib import Path
import re
import unittest

from fluency.pipeline.planning import (
    STAGE_INPUTS,
    STAGE_ORDER,
    PipelineProfileError,
    stage_dependencies,
    stages_invalidated_by,
)


SRC = Path(__file__).resolve().parents[2] / "src" / "fluency"


class StageGraphTests(unittest.TestCase):
    def test_menu_and_harvest_are_siblings(self) -> None:
        self.assertEqual(stage_dependencies("sense_menu"), ("inventory",))
        self.assertEqual(stage_dependencies("sentence_harvest"), ("inventory",))
        self.assertNotIn("sense_menu", stage_dependencies("sentence_harvest"))

    def test_changing_the_menu_does_not_invalidate_the_harvest(self) -> None:
        """The practical payoff: a new dictionary snapshot costs no re-scan."""

        self.assertNotIn("sentence_harvest", stages_invalidated_by("sense_menu"))

    def test_changing_the_inventory_invalidates_everything(self) -> None:
        self.assertEqual(
            stages_invalidated_by("inventory"),
            ("sense_menu", "sentence_harvest", "wsd_assignments",
             "example_selection", "release_build"),
        )

    def test_every_ordered_stage_declares_its_inputs(self) -> None:
        self.assertEqual(set(STAGE_INPUTS), set(STAGE_ORDER))

    def test_inputs_precede_their_stage(self) -> None:
        position = {stage: i for i, stage in enumerate(STAGE_ORDER)}
        for stage, inputs in STAGE_INPUTS.items():
            for dependency in inputs:
                with self.subTest(stage=stage, dependency=dependency):
                    self.assertLess(position[dependency], position[stage])

    def test_unknown_stage_is_refused(self) -> None:
        with self.assertRaises(PipelineProfileError):
            stage_dependencies("not_a_stage")

    def test_declaration_matches_what_the_runners_read(self) -> None:
        """Guards against the declaration and the code drifting apart."""

        harvest = (SRC / "harvest" / "runner.py").read_text()
        menu = (SRC / "sense_menu" / "runner.py").read_text()
        for source, name in ((harvest, "sentence_harvest"), (menu, "sense_menu")):
            read_stages = set(re.findall(r'stages/\d+_(\w+)/output', source))
            declared = {
                {"sentence_harvest": "sentence_harvest"}.get(d, d)
                for d in stage_dependencies(name)
            }
            with self.subTest(stage=name):
                self.assertTrue(
                    read_stages <= declared | {name},
                    f"{name} reads {read_stages - declared - {name}} but does not declare it",
                )


if __name__ == "__main__":
    unittest.main()
