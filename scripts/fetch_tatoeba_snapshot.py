#!/usr/bin/env python3
"""Download one explicit official Tatoeba language-pair snapshot."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


LANGUAGE_CODES = {
    "en": "eng",
    "es": "spa",
    "fr": "fra",
    "nl": "nld",
    "pt": "por",
}
BASE_URL = "https://downloads.tatoeba.org/exports/per_language"


def _download(url: str, destination: Path) -> dict[str, str | None]:
    partial = destination.with_suffix(destination.suffix + ".partial")
    headers_path = destination.with_suffix(destination.suffix + ".headers.partial")
    try:
        subprocess.run(
            [
                "curl",
                "--fail",
                "--location",
                "--continue-at",
                "-",
                "--show-error",
                "--user-agent",
                "Fluency-Next snapshot fetcher/1",
                "--dump-header",
                str(headers_path),
                "--output",
                str(partial),
                url,
            ],
            check=True,
        )
    except FileNotFoundError as error:
        raise OSError("system curl is required to fetch Tatoeba snapshots") from error
    except subprocess.CalledProcessError as error:
        raise OSError(f"curl failed with exit code {error.returncode}: {url}") from error
    headers: dict[str, str | None] = {"last_modified": None, "etag": None}
    for raw_line in headers_path.read_text(encoding="iso-8859-1").splitlines():
        name, separator, value = raw_line.partition(":")
        if not separator:
            continue
        normalized = name.strip().casefold()
        if normalized == "last-modified":
            headers["last_modified"] = value.strip()
        elif normalized == "etag":
            headers["etag"] = value.strip()
    os.replace(partial, destination)
    headers_path.unlink()
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
                "last_modified": headers["last_modified"],
                "etag": headers["etag"],
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
