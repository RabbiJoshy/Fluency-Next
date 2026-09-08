import unittest

from fluency.features import METADATA_CONTRACT_VERSION, MetadataAccounting, SpecialistFeature


class MetadataContractTests(unittest.TestCase):
    def test_envelope_has_a_stable_shape_even_when_a_language_has_no_features(self):
        envelope = MetadataAccounting(
            coverage={"tags": "parsed", "regions": "unavailable"}
        ).envelope(source_metadata={"tags": []}, features=())

        self.assertEqual(envelope["contract_version"], METADATA_CONTRACT_VERSION)
        self.assertEqual(envelope["features"], [])
        self.assertEqual(envelope["unclassified"], [])
        self.assertEqual(envelope["ignored"], [])
        self.assertEqual(envelope["source_metadata"], {"tags": []})

    def test_language_specific_feature_needs_no_equivalent_in_other_languages(self):
        feature = SpecialistFeature(
            "grammar", "aspect", "aspect=perfective", "perfective"
        )
        envelope = MetadataAccounting(coverage={"tags": "parsed"}).envelope(
            source_metadata={"tags": ["perfective"]}, features=(feature,)
        )
        self.assertEqual(envelope["features"], [feature.to_dict()])

    def test_unclassified_material_is_retained_with_its_source_field(self):
        accounting = MetadataAccounting(
            coverage={"tags": "parsed"},
            unclassified=({
                "source_field": "tags",
                "value": "language-specific-mark",
                "reason": "no canonical mapping",
            },),
        )
        rebuilt = MetadataAccounting.from_envelope(
            accounting.envelope(source_metadata={}, features=())
        )
        self.assertEqual(rebuilt.unclassified, accounting.unclassified)

    def test_accounting_rejects_silent_reasonless_discard(self):
        with self.assertRaisesRegex(ValueError, "requires reason"):
            MetadataAccounting(
                ignored=({"source_field": "raw_glosses", "value": "x"},)
            )


if __name__ == "__main__":
    unittest.main()
