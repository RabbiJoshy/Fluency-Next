"""Backwards-compatible re-export of the atomic canonical-JSON writers.

Moved to :mod:`fluency.core.io` because they are generic infrastructure, not
release logic. Existing imports keep working; new code should import from
``fluency.core.io``.
"""

from fluency.core.io import atomic_write, json_bytes

__all__ = ["atomic_write", "json_bytes"]
