from __future__ import annotations

import json

import spacy

from research.wsd_v9.profiles import find_target_token, load_menu
from research.wsd_v9.wsi_probe import _sample_corpus


def test_load_menu_normalizes_spanishdict_and_wiktionary_examples(tmp_path):
    path = tmp_path / "menu.json"
    path.write_text(
        json.dumps(
            {
                "source_adapter": "wiktionary-sense-menu/v1",
                "cards": [
                    {
                        "surface_form": "sair",
                        "analyses": [
                            {
                                "headword": "sair",
                                "part_of_speech": "verb",
                                "senses": [
                                    {
                                        "sense_id": "leave",
                                        "translation": "to leave",
                                        "provider_metadata": {
                                            "examples": [
                                                {
                                                    "text": "Quero sair.",
                                                    "bold_text_offsets": [[6, 10]],
                                                }
                                            ]
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )
    )

    candidate = load_menu(path)["sair"][0]

    assert candidate.provider == "wiktionary"
    assert candidate.meaning == ("VERB", "to leave", "sair")
    assert candidate.examples[0].text == "Quero sair."
    assert (candidate.examples[0].target_start, candidate.examples[0].target_end) == (6, 10)


def test_load_legacy_spanishdict_menu(tmp_path):
    path = tmp_path / "spanishdict.json"
    path.write_text(
        json.dumps(
            {
                "salir": [
                    {
                        "senses": {
                            "abc": {
                                "pos": "VERB",
                                "headword": "salir",
                                "translation": "to leave",
                                "context": "to depart",
                                "examples": [{"original": "Tengo que salir."}],
                            }
                        }
                    }
                ]
            }
        )
    )

    candidate = load_menu(path)["salir"][0]

    assert candidate.provider == "spanishdict"
    assert candidate.sense_id == "abc"
    assert candidate.examples[0].text == "Tengo que salir."


def test_wiktionary_offset_wins_over_surface_lookup():
    doc = spacy.blank("pt")("Quero sair, mas sair cedo.")

    target = find_target_token(
        doc,
        surface_form="sair",
        headword="sair",
        target_start=16,
        target_end=20,
    )

    assert target is not None
    assert target.idx == 16


def test_corpus_reservoir_keeps_metadata_for_duplicate_text(tmp_path):
    corpus = tmp_path / "sentences.jsonl"
    rows = [
        {
            "id": f"row-{index}",
            "es": "Esta parte importa.",
            "provenance": {"title_id": f"title-{index}"},
        }
        for index in range(6)
    ]
    corpus.write_text("".join(json.dumps(row) + "\n" for row in rows))

    reservoirs, metadata = _sample_corpus(corpus, ["parte"], per_surface=3)

    assert len(reservoirs["parte"]) == 3
    assert all(fingerprint in metadata for fingerprint in reservoirs["parte"])
