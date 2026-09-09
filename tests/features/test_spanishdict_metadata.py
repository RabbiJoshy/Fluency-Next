import unittest

from fluency.features.spanishdict_metadata import metadata_accounting


class SpanishDictMetadataAccountingTests(unittest.TestCase):
    def test_known_fields_are_covered_and_unknown_fields_are_retained(self) -> None:
        accounting = metadata_accounting({
            "context": "used with de",
            "regions": ["Mexico"],
            "examples": [],
            "provider_only_note": {"label": "something new"},
        })
        self.assertEqual(accounting.coverage["context"], "parsed")
        self.assertEqual(accounting.unclassified, ({
            "source_field": "spanishdict.provider_only_note",
            "value": {"label": "something new"},
            "reason": "no canonical SpanishDict mapping",
        },))

    def test_absent_language_specific_fields_need_no_fake_equivalent(self) -> None:
        accounting = metadata_accounting({"context": ""})
        self.assertEqual(accounting.unclassified, ())
        self.assertEqual(accounting.coverage["regions"], "parsed")


if __name__ == "__main__":
    unittest.main()
