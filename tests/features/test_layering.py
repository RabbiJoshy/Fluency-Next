"""Stages that run without WSD must not depend on the WSD package.

WSD is optional enrichment that runs two stages after the menu is built, so a
menu that cannot be built without it is a layering error, not a convenience.
This guards the direction of the dependency rather than any particular symbol:

    extractors (adapters)  ->  features / menus  <-  specialists (WSD)
"""

import importlib
import importlib.abc
import sys
import unittest


class _BlockWsd(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "fluency.wsd" or name.startswith("fluency.wsd."):
            raise ImportError("fluency.wsd is unavailable")
        return None


class StageLayeringTests(unittest.TestCase):
    MENU_SIDE = (
        "fluency.menus",
        "fluency.projections",
        "fluency.release.run_candidate",
        "fluency.release.composition",
        "fluency.features",
        "fluency.features.contract",
        "fluency.features.wiktionary",
        "fluency.sense_menu.kaikki",
        "fluency.sense_menu.spanishdict",
    )

    def test_menu_side_imports_without_the_wsd_package(self) -> None:
        blocker = _BlockWsd()
        saved = {name: sys.modules.pop(name) for name in list(sys.modules)
                 if name == "fluency.wsd" or name.startswith("fluency.wsd.")}
        for name in self.MENU_SIDE:
            sys.modules.pop(name, None)
        sys.meta_path.insert(0, blocker)
        try:
            for name in self.MENU_SIDE:
                with self.subTest(module=name):
                    importlib.import_module(name)
        finally:
            sys.meta_path.remove(blocker)
            sys.modules.update(saved)

    def test_legacy_import_paths_still_resolve(self) -> None:
        """Existing `fluency.wsd.*` imports keep working via re-export."""

        from fluency.features import SpecialistFeature
        from fluency.menus import MenuAnalysis, SenseLeaf
        from fluency.wsd.features import SpecialistFeature as LegacyFeature
        from fluency.wsd.menus import MenuAnalysis as LegacyAnalysis, SenseLeaf as LegacyLeaf

        self.assertIs(SpecialistFeature, LegacyFeature)
        self.assertIs(MenuAnalysis, LegacyAnalysis)
        self.assertIs(SenseLeaf, LegacyLeaf)


if __name__ == "__main__":
    unittest.main()
