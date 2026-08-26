"""Names and ceilings for the two very different per-card limits.

Two numbers narrow a Speech run and they are not comparable in cost:

``wsd_budget_per_card``
    How many harvested sentences per card are handed to WSD. Every one of these
    may be embedded or sent to a model, so this number is **spent**, not merely
    enforced. Formerly ``candidate_cap_per_surface``.

``display_examples_per_card``
    How many examples the finished card shows. This costs bytes in a JSON file
    and nothing else. Formerly ``examples_per_surface``.

Calling both of them a "cap" invited exactly one mistake: reasoning about the
cheap number while changing the expensive one. Only the spendable number is
called a budget.

The real exposure was never the naming, though — it is that the *product*
(cards x budget) was computed nowhere and bounded by nothing. `projected_wsd_units`
makes it a number you read at plan time, before anything is spent.
"""

from __future__ import annotations

from typing import Any


WSD_BUDGET_KEY = "wsd_budget_per_card"
LEGACY_WSD_BUDGET_KEY = "candidate_cap_per_surface"
DISPLAY_LIMIT_KEY = "display_examples_per_card"
LEGACY_DISPLAY_LIMIT_KEY = "examples_per_surface"
MAX_UNITS_KEY = "max_wsd_units_per_run"
EXECUTION_CAP_KEY = "execution_cap_per_card"

DEFAULT_MAX_WSD_UNITS_PER_RUN = 250_000


class BudgetError(ValueError):
    """Raised when a run would spend an unstated or unbounded amount."""


def wsd_budget_per_card(harvest: dict[str, Any]) -> int:
    """Return the per-card WSD budget, accepting the legacy key name.

    Both names are read so that profiles written against the old contract keep
    working unchanged; new profiles should use ``wsd_budget_per_card``.
    """

    for key in (WSD_BUDGET_KEY, LEGACY_WSD_BUDGET_KEY):
        value = harvest.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    raise BudgetError(
        f"a Speech profile must state {WSD_BUDGET_KEY} (or legacy {LEGACY_WSD_BUDGET_KEY})"
    )


def display_examples_per_card(scope: dict[str, Any]) -> int:
    """Return the per-card display limit, accepting the legacy key name."""

    for key in (DISPLAY_LIMIT_KEY, LEGACY_DISPLAY_LIMIT_KEY):
        value = scope.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    raise BudgetError(
        f"a Speech profile must state {DISPLAY_LIMIT_KEY} (or legacy {LEGACY_DISPLAY_LIMIT_KEY})"
    )


def execution_cap_per_card(profile: dict[str, Any]) -> int:
    """Return how many occurrences per card actually reach the classifier.

    Two different caps narrow a run and only this one governs spend. The harvest
    budget decides how many candidates are RETAINED; the executor then samples
    from them, historically ten per card. Reading the harvest budget as the spend
    over-estimated it roughly sixfold -- safe in direction, but a guard that is
    routinely wrong is one you learn to ignore.
    """

    declared = (profile.get("wsd") or {}).get(EXECUTION_CAP_KEY)
    if isinstance(declared, int) and not isinstance(declared, bool) and declared > 0:
        return declared
    from fluency.wsd.sampling import DEFAULT_EXECUTION_CAP

    return DEFAULT_EXECUTION_CAP


def projected_wsd_units(profile: dict[str, Any]) -> int:
    """Return how many sentences this profile would put through WSD.

    This is the number that costs money: surfaces times whichever of the
    execution cap and the harvest budget binds first. A card cannot have more
    occurrences scored than were retained for it.
    """

    scope = profile.get("scope") or {}
    harvest = profile.get("harvest") or {}
    surfaces = scope.get("surface_limit")
    if not isinstance(surfaces, int) or isinstance(surfaces, bool) or surfaces < 1:
        raise BudgetError("scope.surface_limit must be a positive integer")
    return surfaces * min(execution_cap_per_card(profile), wsd_budget_per_card(harvest))


def max_wsd_units_per_run(profile: dict[str, Any]) -> int:
    """Return the ceiling this profile accepts, falling back to the default."""

    value = (profile.get("wsd") or {}).get(MAX_UNITS_KEY)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return DEFAULT_MAX_WSD_UNITS_PER_RUN


def check_wsd_budget(profile: dict[str, Any]) -> dict[str, int]:
    """Fail before planning if a run would exceed its stated WSD ceiling."""

    projected = projected_wsd_units(profile)
    ceiling = max_wsd_units_per_run(profile)
    if ceiling < 1:
        raise BudgetError(f"{MAX_UNITS_KEY} must be a positive integer")
    if projected > ceiling:
        raise BudgetError(
            f"this run would put {projected:,} sentences through WSD, above the "
            f"{MAX_UNITS_KEY} ceiling of {ceiling:,}. Lower "
            f"scope.surface_limit or harvest.{WSD_BUDGET_KEY}, or raise the ceiling "
            f"deliberately."
        )
    return {"projected_wsd_units": projected, "max_wsd_units_per_run": ceiling}
