"""The one place a language's names are written down.

A language previously had to be named in several unrelated files -- the CLI's
app-asset route table, the static deployment's key map, and the app's own
config -- each restating the same code/directory correspondence in a different
shape. Two sessions adding two languages collided in all of them.

Everything derivable is now derived from :data:`LANGUAGE_DIRECTORIES`. Codes for
which a ``fluency.languages.<name>`` package exists are discovered from the
package itself; this table only has to name languages the app serves that have
no pipeline support yet.
"""

from __future__ import annotations

from functools import lru_cache

from fluency.languages.surfaces import _packages_by_code


# Languages served by the app that have no pipeline package of their own.
# Anything with a package is discovered and does not belong here.
APP_ONLY_LANGUAGES = {"nl": "dutch"}

# The per-language files the app requests, and the release field each maps to.
APP_DATA_FILES = (
    ("vocabulary.index.json", "index_path"),
    ("vocabulary.examples.json", "examples_path"),
    ("study-structure.json", "study_structure_path"),
    ("release-manifest.json", "__manifest__"),
    ("release-composition.json", "__composition__"),
    ("conjugations.json", "conjugations_path"),
)


@lru_cache(maxsize=None)
def language_keys() -> dict[str, str]:
    """Return {code: lowercase config key}, discovered plus app-only."""

    keys = dict(APP_ONLY_LANGUAGES)
    keys.update(_packages_by_code())
    return dict(sorted(keys.items()))


@lru_cache(maxsize=None)
def language_directories() -> dict[str, str]:
    """Return {code: capitalised Data/ directory name}."""

    return {code: key.capitalize() for code, key in language_keys().items()}


@lru_cache(maxsize=None)
def app_data_routes() -> dict[str, tuple[str, str]]:
    """Return {request path: (language code, release field)} for every language.

    Replaces a hand-maintained table of six rows per language, which is the kind
    of thing that is correct until precisely the moment someone adds a language.
    """

    routes: dict[str, tuple[str, str]] = {}
    for code, directory in language_directories().items():
        for filename, field in APP_DATA_FILES:
            routes[f"/Data/{directory}/{filename}"] = (code, field)
    return routes
