"""Small parsers for metadata embedded in dictionary prose."""

from __future__ import annotations


def leading_parenthetical(text: object, *, max_length: int | None = None) -> str | None:
    """Return a balanced leading parenthetical followed by real text.

    A regular expression cannot correctly read Wiktionary labels such as
    ``(transitive (Portugal) or intransitive (Brazil), colloquial)``. This
    deliberately tiny scanner handles nested parentheses without attempting
    to parse the definition that follows them.
    """

    if not isinstance(text, str) or not text.startswith("("):
        return None
    depth = 0
    for index, character in enumerate(text):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return None
            if depth == 0:
                value = text[1:index].strip()
                if not value or not text[index + 1 :].strip():
                    return None
                if max_length is not None and len(value) > max_length:
                    return None
                return value
    return None


def split_top_level_commas(value: str) -> list[str]:
    """Split comma-delimited labels while preserving nested clauses."""

    parts: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(value):
        if character in "([{":
            depth += 1
        elif character in ")]}" and depth:
            depth -= 1
        elif character == "," and depth == 0:
            part = value[start:index].strip()
            if part:
                parts.append(part)
            start = index + 1
    final = value[start:].strip()
    if final:
        parts.append(final)
    return parts
