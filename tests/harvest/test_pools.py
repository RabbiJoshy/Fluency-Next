"""Pools are flat, described, reusable, and never card-indexed."""

from datetime import UTC, datetime
from pathlib import Path
import tempfile
import unittest

from fluency.harvest.pools import (
    PoolError,
    build_pool_descriptor,
    read_pool,
    rebuild_catalog,
    write_pool,
    year_histogram,
)


def _descriptor(pool_id="pt-opensubtitles-european", **overrides):
    kwargs = dict(
        pool_id=pool_id,
        language="pt",
        description="European Portuguese subtitles for a learner moving to Portugal.",
        intent="Avoid the Brazilian progressive that dominates Tatoeba.",
        variety="european",
        sources=[{
            "name": "opensubtitles",
            "adapter": "opensubtitles-aligned/v1",
            "snapshot_id": "opensubtitles-v2018-en-pt",
            "snapshot_content_id": "sha256:" + "a" * 64,
        }],
        config={"shared_policy": "speech-v1", "language_policy": "pt-v1"},
        coverage={"sentences": 7973},
        created_at=datetime(2026, 8, 24, tzinfo=UTC),
    )
    kwargs.update(overrides)
    return build_pool_descriptor(**kwargs)


class PoolDescriptorTests(unittest.TestCase):
    def test_descriptor_carries_free_text_and_hashes(self) -> None:
        d = _descriptor()
        self.assertEqual(d["pool_version"], "harvest-pool/v1")
        self.assertIn("moving to Portugal", d["description"])
        self.assertEqual(d["variety"], "european")
        self.assertTrue(d["content_id"].startswith("sha256:"))

    def test_pool_holds_no_cards(self) -> None:
        """Card-indexing would weld a pool to one inventory."""

        self.assertNotIn("cards", _descriptor())

    def test_description_is_required(self) -> None:
        with self.assertRaises(PoolError):
            _descriptor(description="   ")

    def test_source_is_required(self) -> None:
        with self.assertRaises(PoolError):
            _descriptor(sources=[])

    def test_invalid_pool_id_refused(self) -> None:
        with self.assertRaises(PoolError):
            _descriptor(pool_id="Not A Pool")

    def test_content_id_ignores_creation_time(self) -> None:
        a = _descriptor(created_at=datetime(2026, 1, 1, tzinfo=UTC))
        b = _descriptor(created_at=datetime(2026, 9, 9, tzinfo=UTC))
        self.assertEqual(a["content_id"], b["content_id"])

    def test_differing_description_changes_content_id(self) -> None:
        self.assertNotEqual(
            _descriptor()["content_id"],
            _descriptor(description="something else")["content_id"],
        )


class PoolStoreTests(unittest.TestCase):
    def test_write_read_and_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root)
            write_pool(workspace, _descriptor())
            write_pool(
                workspace,
                _descriptor(
                    pool_id="pt-tatoeba-brazilian",
                    description="Tatoeba pairs; overwhelmingly Brazilian.",
                    variety="brazilian",
                    coverage={"sentences": 100},
                ),
            )
            restored = read_pool(workspace, "pt", "pt-opensubtitles-european")
            self.assertEqual(restored["variety"], "european")

            catalog = rebuild_catalog(workspace, "pt")
            self.assertEqual(set(catalog["pools"]), {
                "pt-opensubtitles-european", "pt-tatoeba-brazilian",
            })
            self.assertEqual(
                catalog["pools"]["pt-opensubtitles-european"]["sentences"], 7973
            )

    def test_existing_pool_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root)
            write_pool(workspace, _descriptor())
            with self.assertRaises(PoolError):
                write_pool(workspace, _descriptor())

    def test_catalog_is_empty_when_no_pools_exist(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(rebuild_catalog(Path(root), "pt")["pools"], {})


class YearHistogramTests(unittest.TestCase):
    def test_counts_years_from_document_provenance(self) -> None:
        records = [
            {"source": {"document": {"year": "2019"}}},
            {"source": {"document": {"year": "2019"}}},
            {"source": {"document": {"year": "1998"}}},
            {"source": {"document": {}}},
            {"source": {}},
            {},
        ]
        self.assertEqual(year_histogram(records), {"1998": 1, "2019": 2})


if __name__ == "__main__":
    unittest.main()
