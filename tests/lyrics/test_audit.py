from fluency.lyrics.audit import _normalized_form, _route_for


def test_normalized_form_preserves_multi_unit_order() -> None:
    claim = {"value": {"analysis_units": [{"normalized_form": "para"}, {"normalized_form": "mí"}]}}
    assert _normalized_form(claim, "fallback") == "para + mí"


def test_route_marks_exclusions_before_classifiers() -> None:
    routing = {
        "exclude": {"proper_nouns": ["Bunny"]},
        "classifier": {"normal_vocab": ["bunny"]},
    }
    assert _route_for("BUNNY", routing) == {"status": "excluded", "label": "proper nouns"}


def test_route_keeps_unknowns_visible() -> None:
    assert _route_for("unseen", {}) == {"status": "unresolved", "label": "no preserved route"}
