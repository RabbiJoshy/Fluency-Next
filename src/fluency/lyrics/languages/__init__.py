"""Language adapters for Lyrics processing."""

from fluency.lyrics.languages.spanish import SpanishLyricsAdapter


def load_lyrics_adapter(language: str, **kwargs: object) -> SpanishLyricsAdapter:
    if language == "es":
        return SpanishLyricsAdapter(**kwargs)
    raise ValueError(f"no Lyrics processing adapter is installed for language {language!r}")

