import pytest

from analog_finder.finder import target as tg
from analog_finder.finder.score import line_category

BASE = {"name": "X", "indication": "X is indicated for schizophrenia.", "class_narrow": "N05AX", "route_group": "oral"}


def test_minimal_target_derives_class_codes():
    t = tg.from_dict(BASE)
    assert (t.atc4, t.atc3, t.area) == ("N05AX", "N05A", "N")
    assert t.n_competitors is None and t.order_of_entry is None
    assert t.is_estimate is True


def test_labels_with_names_are_reduced_to_codes():
    t = tg.from_dict({**BASE, "class_narrow": "N05AX Other antipsychotics", "class_broad": "N05A Antipsychotics",
                      "therapeutic_area": "N Nervous system"})
    assert (t.atc4, t.atc3, t.area) == ("N05AX", "N05A", "N")


def test_numbers_and_preferences():
    t = tg.from_dict({**BASE, "n_competitors_at_launch": 6, "entry_order": 7}, preferences={"atc4": 0.5})
    assert t.n_competitors == 6.0 and t.order_of_entry == 7
    assert t.preferences == {"atc4": 0.5}


@pytest.mark.parametrize("change, message", [
    ({"route_group": None}, "missing required"),
    ({"indication": "  "}, "missing required"),
    ({"route_group": "iv"}, "route_group"),
    ({"class_narrow": "N05A"}, "ATC level 4"),
    ({"class_narrow": "antipsychotic"}, "ATC level 4"),
    ({"class_broad": "L04A"}, "don't contain"),
    ({"n_competitors_at_launch": "six"}, "expected a number"),
    ({"entry_order": -1}, ">= 0"),
    ({"is_estimate": "yes"}, "is_estimate"),
    ({"clas_narrow": "N05AX"}, "unknown field"),
])
def test_bad_target_fails_with_a_clear_message(change, message):
    with pytest.raises(tg.TargetError, match=message):
        tg.from_dict({**BASE, **change})


def test_scenario_without_target_block(scenarios_dir):
    d = scenarios_dir({"s": "name: S\n"})
    with pytest.raises(tg.TargetError, match="s.yaml: scenario has no `target:` block"):
        tg.load_target("s", d)


def test_committed_torevia_loads():
    t = tg.load_target("torevia")
    assert (t.name, t.atc4, t.route_group, t.dosing_frequency) == ("Torevia", "N05AX", "oral", "once daily")
    assert t.n_competitors == 5 and t.order_of_entry == 7 and t.is_estimate
    assert t.extra["launch_date"] == "2027-01"


def test_torevia_line_of_therapy_is_on_a_label_basis():
    # Label basis (decisions.md 2026-11-18): the label sets no prior-therapy requirement, so "any", which is
    # scored now that line of therapy is a category (decisions.md 2026-11-19).
    t = tg.load_target("torevia")
    assert t.line_of_therapy == "any" and line_category(t.line_of_therapy) == "any"


@pytest.mark.parametrize("value, stored", [("later", "later"), ("Any", "any"), (" not stated ", "not stated"),
                                           ("", ""), (None, "")])
def test_line_of_therapy_categories(value, stored):
    spec = {"name": "X", "indication": "X treats Y.", "class_narrow": "N05AX", "route_group": "oral",
            "line_of_therapy": value}
    assert tg.from_dict(spec).line_of_therapy == stored


def test_line_of_therapy_free_text_is_refused():
    spec = {"name": "X", "indication": "X treats Y.", "class_narrow": "N05AX", "route_group": "oral",
            "line_of_therapy": "after at least one generic antipsychotic"}
    with pytest.raises(tg.TargetError, match="line_of_therapy.*target_patient_definition"):
        tg.from_dict(spec)
