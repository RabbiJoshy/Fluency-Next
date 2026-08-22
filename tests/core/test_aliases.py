import unittest

from fluency.core.aliases import (
    AliasEvidence,
    AliasSource,
    ProgressAlias,
    ProgressAliasRegistry,
)
from fluency.core.hashing import content_id
from fluency.core.identity import build_card_id


class ProgressAliasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = AliasEvidence(
            source_id="legacy_deck",
            observation_kind="deck_row",
            observed_surface_key="una",
        )

    def test_resolved_alias_requires_matching_surface_card(self) -> None:
        alias = ProgressAlias(
            alias_key="es0c72b0494",
            language="es",
            mode="speech",
            status="resolved",
            provenance_status="observed",
            evidence=(self.evidence,),
            canonical_card_id=build_card_id("es", "una"),
            surface_key="una",
        )
        self.assertEqual(alias.to_dict()["surface_key"], "una")

        with self.assertRaises(ValueError):
            ProgressAlias(
                alias_key="es0c72b0494",
                language="es",
                mode="speech",
                status="resolved",
                provenance_status="observed",
                evidence=(self.evidence,),
                canonical_card_id=build_card_id("es", "otra"),
                surface_key="una",
            )

    def test_ambiguous_alias_preserves_candidates_without_guessing(self) -> None:
        surfaces = ("atrás", "sientes")
        alias = ProgressAlias(
            alias_key="es0780764",
            language="es",
            mode="speech",
            status="ambiguous",
            provenance_status="observed",
            evidence=(self.evidence,),
            candidate_card_ids=tuple(build_card_id("es", value) for value in surfaces),
            candidate_surface_keys=surfaces,
        )
        self.assertNotIn("canonical_card_id", alias.to_dict())
        self.assertEqual(alias.to_dict()["candidate_surface_keys"], list(surfaces))

    def test_registry_rejects_duplicate_alias_keys(self) -> None:
        alias = ProgressAlias(
            alias_key="es0c72b0494",
            language="es",
            mode="speech",
            status="resolved",
            provenance_status="observed",
            evidence=(self.evidence,),
            canonical_card_id=build_card_id("es", "una"),
            surface_key="una",
        )
        with self.assertRaises(ValueError):
            ProgressAliasRegistry(
                language="es",
                mode="speech",
                aliases=(alias, alias),
                sources={
                    "legacy_deck": AliasSource(
                        source_id="legacy_deck",
                        source_path="/legacy/deck.json",
                        source_content_id=content_id(b"deck"),
                    )
                },
            )

    def test_registry_rejects_unknown_evidence_source(self) -> None:
        alias = ProgressAlias(
            alias_key="es0c72b0494",
            language="es",
            mode="speech",
            status="resolved",
            provenance_status="observed",
            evidence=(self.evidence,),
            canonical_card_id=build_card_id("es", "una"),
            surface_key="una",
        )
        with self.assertRaisesRegex(ValueError, "unknown source"):
            ProgressAliasRegistry(
                language="es",
                mode="speech",
                aliases=(alias,),
                sources={},
            )


if __name__ == "__main__":
    unittest.main()
