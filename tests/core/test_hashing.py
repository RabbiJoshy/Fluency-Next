from pathlib import Path
import tempfile
import unittest

from fluency.core.canonical_json import canonical_json
from fluency.core.hashing import (
    canonical_content_id,
    content_id,
    file_content_id,
    validate_content_id,
)


class HashingTests(unittest.TestCase):
    def test_canonical_json_is_order_independent(self) -> None:
        first = {"b": 2, "a": {"z": 3, "y": 4}}
        second = {"a": {"y": 4, "z": 3}, "b": 2}
        self.assertEqual(canonical_json(first), canonical_json(second))
        self.assertEqual(canonical_content_id(first), canonical_content_id(second))

    def test_non_standard_numbers_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            canonical_json({"invalid": float("nan")})

    def test_file_and_byte_hashes_agree(self) -> None:
        data = b"immutable artifact\n"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "artifact.bin"
            path.write_bytes(data)
            self.assertEqual(file_content_id(path), content_id(data))

    def test_content_id_validation_is_strict(self) -> None:
        valid = content_id(b"valid")
        self.assertEqual(len(validate_content_id(valid)), 64)
        for invalid in ("", "md5:abc", "sha256:ABC", "sha256:123"):
            with self.subTest(value=invalid):
                with self.assertRaises(ValueError):
                    validate_content_id(invalid)


if __name__ == "__main__":
    unittest.main()

