"""Corpus adapters available to the harvesting engine."""

from fluency.harvest.sources.base import CorpusAdapter
from fluency.harvest.sources.opensubtitles import OpenSubtitlesAdapter
from fluency.harvest.sources.tatoeba import TatoebaAdapter

__all__ = ["CorpusAdapter", "OpenSubtitlesAdapter", "TatoebaAdapter"]
