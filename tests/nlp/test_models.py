"""Model identity is configuration, and the manifests must read the same copy.

gemini-embedding-001, SEMANTIC_SIMILARITY and es_dep_news_trf@3.8.0 were each
written into several modules independently, so a run manifest recorded whichever
copy its code path happened to read and two modes could disagree about what they
had just used.
"""

import unittest

from fluency.nlp.models import ModelRegistryError, model, pin, setting


class RegistryTests(unittest.TestCase):
    def test_embedding_model_is_declared(self) -> None:
        declared = model("exact-text-embedding")
        self.assertEqual(declared["name"], "gemini-embedding-001")
        self.assertEqual(declared["task_type"], "SEMANTIC_SIMILARITY")

    def test_pos_pin_is_name_at_revision(self) -> None:
        self.assertEqual(pin("occurrence-pos"), "es_dep_news_trf@3.8.0")

    def test_unknown_role_lists_what_exists(self) -> None:
        with self.assertRaises(ModelRegistryError) as caught:
            model("not-a-role")
        self.assertIn("available:", str(caught.exception))

    def test_role_without_a_revision_cannot_be_pinned(self) -> None:
        with self.assertRaises(ModelRegistryError):
            pin("exact-text-embedding")

    def test_settings_fall_back_when_unstated(self) -> None:
        self.assertEqual(setting("occurrence-pos", "batch_size", 7), 7)


class SingleSourceTests(unittest.TestCase):
    def test_both_modes_agree_on_the_pos_pin(self) -> None:
        """Two modes disagreeing about the model they just used is the bug."""

        from fluency.lyrics.wsd_execute import SPACY_POS_MODEL as lyrics_pin
        from fluency.speech.wsd_execute import SPACY_POS_MODEL as speech_pin

        self.assertEqual(lyrics_pin, speech_pin)
        self.assertEqual(speech_pin, pin("occurrence-pos"))

    def test_the_embedding_store_agrees_with_the_registry(self) -> None:
        from fluency.nlp import embeddings

        self.assertEqual(embeddings.EMBED_MODEL, setting("exact-text-embedding", "name"))
        self.assertEqual(embeddings.TASK_TYPE, setting("exact-text-embedding", "task_type"))

    def test_no_execution_module_restates_a_model_identifier(self) -> None:
        """A second copy is how the manifests drifted from the code."""

        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "src" / "fluency"
        for relative in ("speech/wsd_execute.py", "lyrics/wsd_execute.py"):
            source = (root / relative).read_text()
            body = "\n".join(
                line for line in source.splitlines()
                if "raw/embeddings" not in line  # a recorded snapshot location, not a choice
            )
            with self.subTest(module=relative):
                self.assertNotIn('"gemini-embedding-001"', body)
                self.assertNotIn('"SEMANTIC_SIMILARITY"', body)
                self.assertNotIn('"es_dep_news_trf@3.8.0"', body)


if __name__ == "__main__":
    unittest.main()
