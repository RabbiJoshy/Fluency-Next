"""Language adapters for Lyrics processing."""

from fluency.lyrics.languages.spanish import SpanishLyricsAdapter
from fluency.lyrics.languages.spanish_routing import SpanishLiveRouter


def load_lyrics_adapter(language: str, **kwargs: object) -> SpanishLyricsAdapter:
    if language == "es":
        return SpanishLyricsAdapter(**kwargs)
    raise ValueError(f"no Lyrics processing adapter is installed for language {language!r}")


def load_live_lyrics_router(language: str, **kwargs: object) -> SpanishLiveRouter:
    if language == "es":
        return SpanishLiveRouter(**kwargs)
    raise ValueError(f"no live Lyrics router is installed for language {language!r}")
