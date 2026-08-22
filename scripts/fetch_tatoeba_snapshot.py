#!/usr/bin/env python3
"""Download one explicit official Tatoeba language-pair snapshot."""

from __future__ import annotations

import argparse
from email.message import Message
import json
import os
from pathlib import Path
import shutil
import sys
from urllib.request import Request, urlopen


LANGUAGE_CODES = {
    "en": "eng",
    "es": "spa",
    "fr": "fra",
    "nl": "nld",
    "pt": "por",
}
BASE_URL = "https://downloads.tatoeba.org/exports/per_language"


def _download(url: str, destination: Path) -> Message:
    partial = destination.with_suffix(destination.suffix + ".partial")
    request = Request(url, headers={"User-Agent": "Fluency-Next snapshot fetcher/1"})
    with urlopen(request) as response, partial.open("wb") as stream:
        total = int(response.headers.get("Content-Length", "0"))
        copied = 0
        while chunk := response.read(1024 * 1024):
            stream.write(chunk)
            copied += len(chunk)
            if total:
                print(
                    f"\r{destination.name}: {copied / 1_048_576:.1f}/"
                    f"{total / 1_048_576:.1f} MiB",
                    end="",
                    flush=True,
                )
        if total:
            print()
        headers = response.headers
    os.replace(partial, destination)
    return headers


def fetch_snapshot(
    workspace: Path,
    *,
    snapshot_id: str,
    target_language: str,
    translation_language: str,
) -> Path:
    try:
        target_code = LANGUAGE_CODES[target_language]
        translation_code = LANGUAGE_CODES[translation_language]
    except KeyError as error:
        raise ValueError(f"unsupported Tatoeba language: {error.args[0]}") from error
    if not snapshot_id or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-." for character in snapshot_id):
        raise ValueError("snapshot ID must contain only lowercase letters, digits, dots, and hyphens")

    destination = (
        workspace.expanduser().resolve()
        / "raw"
        / "tatoeba"
        / f"{target_language}-{translation_language}"
        / snapshot_id
    )
    if destination.exists():
        raise FileExistsError(
            f"snapshot destination already exists; choose a new immutable ID: {destination}"
        )
    destination.mkdir(parents=True)
    downloads = {
        "target_sentences": (
            f"{BASE_URL}/{target_code}/{target_code}_sentences_detailed.tsv.bz2",
            f"{target_code}_sentences_detailed.tsv.bz2",
        ),
        "translation_sentences": (
            f"{BASE_URL}/{translation_code}/{translation_code}_sentences_detailed.tsv.bz2",
            f"{translation_code}_sentences_detailed.tsv.bz2",
        ),
        "links": (
            f"{BASE_URL}/{translation_code}/"
            f"{translation_code}-{target_code}_links.tsv.bz2",
            f"{translation_code}-{target_code}_links.tsv.bz2",
        ),
    }
    source_files: dict[str, dict[str, str | None]] = {}
    try:
        for role, (url, filename) in downloads.items():
            print(f"Downloading {url}")
            headers = _download(url, destination / filename)
            source_files[role] = {
                "filename": filename,
                "url": url,
                "last_modified": headers.get("Last-Modified"),
                "etag": headers.get("ETag"),
            }
        metadata = {
            "snapshot_version": "tatoeba-weekly-snapshot/v1",
            "snapshot_id": snapshot_id,
            "target_language": target_language,
            "target_code": target_code,
            "translation_language": translation_language,
            "translation_code": translation_code,
            "license": "CC BY 2.0 FR",
            "license_url": "https://creativecommons.org/licenses/by/2.0/fr/",
            "attribution": "Tatoeba contributors",
            "source_url": "https://tatoeba.org/en/downloads",
            "source_files": source_files,
        }
        (destination / "snapshot.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(destination)
        raise
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--language", default="fr")
    parser.add_argument("--translation-language", default="en")
    args = parser.parse_args()
    try:
        destination = fetch_snapshot(
            args.workspace,
            snapshot_id=args.snapshot_id,
            target_language=args.language,
            translation_language=args.translation_language,
        )
    except (FileExistsError, OSError, ValueError) as error:
        print(f"Tatoeba snapshot failed: {error}", file=sys.stderr)
        return 1
    print(f"Pinned official Tatoeba snapshot: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
