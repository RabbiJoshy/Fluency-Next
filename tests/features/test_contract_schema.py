"""The serialized feature contract and its JSON schema must evolve together."""

import json
from pathlib import Path
import unittest

from fluency.features.contract import FEATURE_FAMILIES


class FeatureContractSchemaTests(unittest.TestCase):
    def test_sense_menu_schema_accepts_every_runtime_feature_family(self) -> None:
        schema_path = Path(__file__).parents[2] / "schemas" / "sense-menu.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        family = schema["properties"]["cards"]["items"]["properties"]["analyses"][
            "items"
        ]["properties"]["senses"]["items"]["properties"]["specialist_features"][
            "items"
        ]["properties"]["family"]["enum"]

        self.assertTrue(set(FEATURE_FAMILIES).issubset(family))


if __name__ == "__main__":
    unittest.main()
