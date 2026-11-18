import pandas as pd
import pytest

from analog_finder import io
from analog_finder.finder import filters
from analog_finder.finder.target import load_target
from analog_finder.tests.conftest import FINDER_USABLE_ORAL


def test_usable_oral_candidates_only(finder_tables, schizo_target):
    c = filters.candidates(finder_tables, schizo_target)
    assert list(c.analog_id) == FINDER_USABLE_ORAL  # no sc, no late launch, no generic entry, no thin data
    assert list(c.columns) == filters.COLUMNS


def test_filters_can_be_switched_off(finder_tables, schizo_target):
    c = filters.candidates(finder_tables, schizo_target, filters={"usable_only": False, "match_route_group": False},
                           top_k=1)
    assert len(c) == 16


def test_holdout_removed_before_filtering(finder_tables, schizo_target):
    c = filters.candidates(finder_tables, schizo_target, holdout="o01_oral")
    assert "o01_oral" not in set(c.analog_id) and len(c) == 11


def test_unknown_holdout_is_an_error(finder_tables, schizo_target):
    with pytest.raises(filters.FilterError, match="not in analog_features"):
        filters.candidates(finder_tables, schizo_target, holdout="nope_oral")


def test_warning_flags(finder_tables, schizo_target):
    c = filters.candidates(finder_tables, schizo_target).set_index("analog_id")
    assert set(c.index[c.warn_label_expansion]) == {"o02_oral", "o03_oral"}
    assert set(c.index[c.warn_multi_route]) == {"o04_oral"}
    assert set(c.index[c.low_volume]) == {"o06_oral"}
    assert set(c.index[c.peak_not_confirmed]) == {"o04_oral"}
    assert set(c.index[c.weak_bass_fit]) == {"o05_oral", "o06_oral"}  # o05 has no fit: counts as weak


def test_class_codes_and_names(finder_tables, schizo_target):
    c = filters.candidates(finder_tables, schizo_target).set_index("analog_id")
    assert (c.loc["o01_oral", "atc4"], c.loc["o01_oral", "atc3"], c.loc["o01_oral", "area"]) == ("N05AX", "N05A", "N")
    assert c.loc["o01_oral", "atc4_name"] == "N05AX Other antipsychotics"
    assert c.loc["o11_oral", "atc4"] == ""  # no ATC class
    assert filters.codes("G03AA Progestogens; G03CA Natural estrogens") == "G03AA; G03CA"


def test_few_candidates_warn_and_none_raise(finder_tables, schizo_target):
    with pytest.warns(UserWarning, match="only 12 candidates"):
        filters.candidates(finder_tables, schizo_target, top_k=7)
    sc = schizo_target.__class__(**{**schizo_target.__dict__, "route_group": "sc"})
    finder_tables["analog_features"].loc[finder_tables["analog_features"].route_group == "sc", "enough_data"] = False
    with pytest.raises(filters.FilterError, match="no analogs"):
        filters.candidates(finder_tables, sc)


def test_committed_data_torevia_analogs_pass():
    """On data/processed: 213 usable oral analogs, and Torevia's 5 expected analogs are among them."""
    tables = io.load_tables()
    c = filters.candidates(tables, load_target("torevia"))
    assert len(c) == 213
    assert {"latuda_oral", "rexulti_oral", "vraylar_oral", "caplyta_oral", "lybalvi_oral"} <= set(c.analog_id)
    held = filters.candidates(tables, load_target("torevia"), holdout="latuda_oral")
    assert "latuda_oral" not in set(held.analog_id) and len(held) == 212
