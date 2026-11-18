import numpy as np
import pandas as pd
import pytest

from analog_finder.finder import curve

SCORES = pd.DataFrame({"analog_id": ["a", "b", "c"], "similarity": [0.6, 0.3, 0.1]})


def test_weights_are_normalized_similarity():
    w = curve.weights(["a", "b", "c"], SCORES)
    assert w.weight.tolist() == pytest.approx([0.6, 0.3, 0.1])
    assert w.weight.sum() == pytest.approx(1)
    assert list(w.columns) == curve.WEIGHT_COLUMNS and w.override_weight.isna().all()


def test_override_rescales_the_others():
    w = curve.weights(["a", "b", "c"], SCORES, {"c": {"weight": 0.5, "reason": "closest launch setting"}})
    assert w.set_index("analog_id").weight.to_dict() == pytest.approx({"a": 1 / 3, "b": 1 / 6, "c": 0.5}, abs=1e-6)
    assert w.weight.sum() == pytest.approx(1)
    assert w.set_index("analog_id").loc["c", "override_reason"] == "closest launch setting"


@pytest.mark.parametrize("overrides, message", [
    ({"a": {"weight": 0.5}}, "reason is required"),
    ({"a": {"weight": 1.5, "reason": "x"}}, "from 0 to 1"),
    ({"a": {"weight": "half", "reason": "x"}}, "from 0 to 1"),
    ({"a": {"weight": 0.7, "reason": "x"}, "b": {"weight": 0.5, "reason": "x"}}, "sum to 1.2"),
    ({k: {"weight": 0.2, "reason": "x"} for k in "abc"}, "must total 1"),
])
def test_bad_overrides(overrides, message):
    with pytest.raises(curve.CurveError, match=message):
        curve.weights(["a", "b", "c"], SCORES, overrides)


def test_override_for_unconfirmed_analog_is_ignored():
    with pytest.warns(UserWarning, match="not a confirmed analog"):
        w = curve.weights(["a", "b"], SCORES, {"c": {"weight": 0.5, "reason": "x"}})
    assert w.weight.sum() == pytest.approx(1)


def test_no_confirmed_analogs():
    with pytest.raises(curve.CurveError, match="no confirmed"):
        curve.weights([], SCORES)


def _curves():
    rows = [("a", q, min(1, q / 10)) for q in range(21)] + [("b", q, min(1, q / 5)) for q in range(21)]
    rows += [("c", q, q / 20) for q in range(15)]  # short curve: stops at Q14
    df = pd.DataFrame(rows, columns=["analog_id", "q_since_launch", "share_of_peak"])
    df["provisional"] = (df.analog_id == "c") & (df.q_since_launch >= 13)  # Q13-Q14 provisional
    return df


def test_curve_weighted_mean_band_and_short_curves():
    w = curve.weights(["a", "b", "c"], SCORES)
    u = curve.uptake_curve(w, _curves(), upper_bound={"c"}).set_index("quarter")
    assert list(u.reset_index().columns) == curve.CURVE_COLUMNS and len(u) == 21
    assert u.loc[4, "weighted_share_of_peak"] == pytest.approx(0.6 * 0.4 + 0.3 * 0.8 + 0.1 * 0.2)
    assert (u.loc[4, "band_min"], u.loc[4, "band_max"]) == (0.2, 0.8)
    assert (u.loc[4, "n_analogs"], u.loc[4, "n_upper_bound"]) == (3, 1)
    # c's provisional quarters drop out: Q13 onward averages a and b, renormalized
    assert u.loc[13, "n_analogs"] == 2 and u.loc[13, "n_upper_bound"] == 0
    assert u.loc[13, "weighted_share_of_peak"] == pytest.approx((0.6 * 1 + 0.3 * 1) / 0.9)
    assert ((u.band_min <= u.weighted_share_of_peak + 1e-9) & (u.weighted_share_of_peak <= u.band_max + 1e-9)).all()


def test_bass_table(finder_tables):
    from analog_finder.finder import filters, target
    c = filters.candidates(finder_tables, target.from_dict(
        {"name": "T", "indication": "x", "class_narrow": "N05AX", "route_group": "oral"}))
    w = curve.weights(["o01_oral", "o05_oral"], pd.DataFrame({"analog_id": ["o01_oral", "o05_oral"],
                                                              "similarity": [0.5, 0.5]}))
    b = curve.bass_table(w, finder_tables["bass_fits"], c).set_index("analog_id")
    assert b.loc["o01_oral", "drug_name"] == "Oone" and b.loc["o01_oral", "p"] == 0.02
    assert np.isnan(b.loc["o05_oral", "p"])  # no fit
