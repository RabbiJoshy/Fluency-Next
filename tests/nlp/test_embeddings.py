"""Embeddings are expensive and perfectly reusable; losing them is pure waste.

The behaviour that matters is resumability: a run killed partway must not
re-buy the vectors it already paid for, and a torn checkpoint must never leave
an index entry that no vector backs.
"""

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from fluency.nlp.embeddings import (
    EmbeddingStoreError,
    delta_directory,
    ensure_embeddings,
    load_cache,
    merge_delta,
)


def _write_cache(path: Path, mapping: dict[str, list[float]]) -> None:
    ordered = sorted(mapping)
    np.savez_compressed(
        path,
        keys=np.array(ordered, dtype=object),
        vectors=np.stack([np.asarray(mapping[k], dtype=np.float32) for k in ordered]),
    )


def _write_delta(cache: Path, mapping: dict[str, list[float]], *, torn: int = 0) -> None:
    delta = delta_directory(cache)
    delta.mkdir(parents=True, exist_ok=True)
    ordered = list(mapping)
    matrix = np.stack([np.asarray(mapping[k], dtype=np.float32) for k in ordered])
    if torn:
        matrix = np.vstack([matrix, np.zeros((torn, matrix.shape[1]), dtype=np.float32)])
    np.save(delta / "vec.npy", matrix)
    (delta / "index.json").write_text(
        json.dumps({k: i for i, k in enumerate(ordered)}), encoding="utf-8"
    )


class LoadCacheTests(unittest.TestCase):
    def test_reads_the_shared_cache(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            cache = Path(root) / "exact.npz"
            _write_cache(cache, {"hola": [1.0, 0.0], "adios": [0.0, 1.0]})
            self.assertEqual(set(load_cache(cache)), {"hola", "adios"})

    def test_unmerged_delta_is_visible(self) -> None:
        """Work already paid for counts even before it is merged."""

        with tempfile.TemporaryDirectory() as root:
            cache = Path(root) / "exact.npz"
            _write_cache(cache, {"hola": [1.0, 0.0]})
            _write_delta(cache, {"nuevo": [0.5, 0.5]})
            self.assertEqual(set(load_cache(cache)), {"hola", "nuevo"})

    def test_torn_checkpoint_discards_only_the_uncommitted_tail(self) -> None:
        """Vectors are written before the index, so a tear is a surplus row."""

        with tempfile.TemporaryDirectory() as root:
            cache = Path(root) / "exact.npz"
            _write_cache(cache, {"hola": [1.0, 0.0]})
            _write_delta(cache, {"nuevo": [0.5, 0.5]}, torn=3)
            self.assertEqual(set(load_cache(cache)), {"hola", "nuevo"})

    def test_index_claiming_more_than_the_vectors_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            cache = Path(root) / "exact.npz"
            _write_cache(cache, {"hola": [1.0, 0.0]})
            delta = delta_directory(cache)
            delta.mkdir(parents=True, exist_ok=True)
            np.save(delta / "vec.npy", np.zeros((1, 2), dtype=np.float32))
            (delta / "index.json").write_text(json.dumps({"a": 0, "b": 1}), encoding="utf-8")
            with self.assertRaises(EmbeddingStoreError):
                load_cache(cache)

    def test_missing_cache_is_empty_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(load_cache(Path(root) / "absent.npz"), {})


class EnsureTests(unittest.TestCase):
    def test_no_api_call_when_everything_is_cached(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            cache = Path(root) / "exact.npz"
            _write_cache(cache, {"hola": [1.0, 0.0]})
            got = ensure_embeddings(cache, ["hola"], api_key=None, log=lambda _m: None)
            self.assertEqual(set(got), {"hola"})

    def test_missing_without_a_key_is_refused_rather_than_silently_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            cache = Path(root) / "exact.npz"
            _write_cache(cache, {"hola": [1.0, 0.0]})
            with self.assertRaises(EmbeddingStoreError):
                ensure_embeddings(cache, ["hola", "nuevo"], api_key=None, log=lambda _m: None)


class MergeTests(unittest.TestCase):
    def test_merge_writes_the_cache_and_clears_the_delta(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            cache = Path(root) / "exact.npz"
            _write_cache(cache, {"hola": [1.0, 0.0]})
            _write_delta(cache, {"nuevo": [0.5, 0.5]})
            merge_delta(cache, load_cache(cache))
            self.assertEqual(set(load_cache(cache)), {"hola", "nuevo"})
            self.assertFalse((delta_directory(cache) / "index.json").exists())


if __name__ == "__main__":
    unittest.main()
