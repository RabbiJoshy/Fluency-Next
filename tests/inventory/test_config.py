from pathlib import Path
import unittest

from fluency.inventory.config import load_inventory_language_policy


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class InventoryPolicyTests(unittest.TestCase):
    def test_spanish_policy_uses_registered_spanish_normalizer(self):
        policy = load_inventory_language_policy(
            REPOSITORY_ROOT, policy_id="es-v1", language="es"
        )
        self.assertEqual(policy["surface_exclusions"], {})


if __name__ == "__main__":
    unittest.main()
