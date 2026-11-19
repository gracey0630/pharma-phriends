"""The evaluation harness (step 8) on the fixture tables, offline."""
import io as stdio

import numpy as np
import pandas as pd
import pytest

from analog_finder import evaluate as ev
from analog_finder import io


@pytest.fixture
def cfg():
    return io.load_config()


def test_error_formula_matches_the_eda():
    # the EDA (analog_similarity): np.nanmean(np.abs(X[i] - np.nanmedian(X[others], axis=0)))
    X = np.array([[0.1, 0.4, np.nan, 0.9], [0.2, 0.5, 0.7, 1.0], [0.0, 0.3, 0.6, 0.8], [0.3, 0.2, 0.5, np.nan]])
    for i in range(len(X)):
        others = np.arange(len(X)) != i
        eda = np.nanmean(np.abs(X[i] - np.nanmedian(X[others], axis=0)))
        assert ev.mean_abs_error(X[i], np.nanmedian(X[others], axis=0)) == pytest.approx(eda)
    assert np.isnan(ev.mean_abs_error([np.nan], [0.5]))


def test_held_out_are_usable_analogs_with_all_of_q0_q12(finder_tables):
    actual = ev.actual_curves(finder_tables)
    assert list(actual.columns) == list(range(13))
    held = ev.held_out_ids(actual)
    assert "late_oral" not in held and "gen_oral" not in held and "thin_oral" not in held  # not usable
    assert "o04_oral" in held  # provisional only from Q13
    lc = finder_tables["launch_curves"]
    finder_tables["launch_curves"] = lc[~((lc.analog_id == "o05_oral") & (lc.q_since_launch == 5))]
    assert "o05_oral" not in ev.held_out_ids(ev.actual_curves(finder_tables))


def test_target_from_an_analogs_own_data(finder_tables):
    t = ev.target_for("o01_oral", finder_tables)
    assert (t.name, t.atc4, t.atc3, t.area, t.route_group, t.dosage_form) == (
        "Oone", "N05AX", "N05A", "N", "oral", "TABLET")
    assert t.indication_text.startswith("OONE is indicated")
    assert (t.line_of_therapy, t.dosing_frequency, t.n_competitors) == ("", "", None)  # no evidence
    assert (ev.target_for("o11_oral", finder_tables).atc4, ev.target_for("o11_oral", finder_tables).area) == ("", "")
    f = finder_tables["analog_features"]
    f.loc[f.analog_id == "o12_oral", "class_narrow"] = "C10AX Other lipid modifying agents; C10AA Statins"
    assert ev.target_for("o12_oral", finder_tables).atc4 == "C10AX"  # first class of a multi-class analog


def test_baselines_use_the_same_route_group_and_exclude_the_analog(finder_tables, monkeypatch):
    actual = ev.actual_curves(finder_tables)
    base, fallback = ev.baselines("o01_oral", actual, finder_tables["analog_features"])
    others = [f"o{i:02d}_oral" for i in range(2, 13)]  # not o01 itself, not the sc analog
    pd.testing.assert_series_equal(base["all_analog_median"], actual.loc[others].median())
    assert fallback and base["atc4_median"].equals(base["all_analog_median"])  # only o02 shares N05AX
    monkeypatch.setattr(ev, "MIN_CLASS", 1)
    base, fallback = ev.baselines("o01_oral", actual, finder_tables["analog_features"])
    assert not fallback
    pd.testing.assert_series_equal(base["atc4_median"], actual.loc[["o02_oral"]].median())


def test_structured_only_drops_text():
    w = ev.method_weights({"text": 1.0, "atc4": 0.25})
    assert w["tfidf_hybrid"] == {"text": 1.0, "atc4": 0.25}
    assert w["structured_only"] == {"text": 0.0, "atc4": 0.25}


def test_run_leaves_each_analog_out_of_its_own_prediction(finder_tables, cfg):
    errors = ev.run(finder_tables, cfg).set_index("analog_id")
    assert errors.loc["s01_sc", "skipped"]  # alone in its route group: nothing to match
    done = errors[errors.skipped == ""]
    assert len(done) == 12
    for a, r in done.iterrows():
        for m in ev.METHODS:
            assert a not in r[f"top5_{m}"].split("; ")
            assert len(r[f"top5_{m}"].split("; ")) == 5
        for m in ev.METHODS + ev.BASELINES:
            assert 0 <= r[f"error_{m}"] <= 1
    assert done.loc["o01_oral", "top5_tfidf_hybrid"].split("; ")[0] == "o02_oral"  # same class and indication
    assert done.loc["o11_oral", "structured_fallback"]  # no ATC class: structured only has nothing to rank on
    assert done.loc["o11_oral", "error_structured_only"] == pytest.approx(done.loc["o11_oral", "error_all_analog_median"])


def test_run_checks_its_inputs(finder_tables, cfg):
    with pytest.raises(ValueError, match="not evaluated"):
        ev.run(finder_tables, cfg, analogs=["late_oral"])
    with pytest.raises(ValueError, match="use_evidence"):
        ev.run(finder_tables, {**cfg, "use_evidence": True})


def test_summary_rows_and_bootstrap():
    errors = pd.DataFrame({
        "analog_id": list("abcd"), "peak_confirmed": [True, True, False, True], "skipped": "",
        "atc4_fallback": [True, False, True, True], "structured_fallback": [False, False, False, True],
        "error_tfidf_hybrid": [0.1, 0.2, 0.1, 0.3], "error_structured_only": [0.2, 0.2, 0.2, 0.2],
        "error_atc4_median": [0.3, 0.1, 0.2, 0.2], "error_all_analog_median": [0.3, 0.3, 0.2, 0.2]})
    s = ev.summarize(errors, n_boot=200, seed=1)
    assert s.equals(ev.summarize(errors, n_boot=200, seed=1))  # reproducible
    hybrid = s[(s.subset == "all") & (s.method == ev.LABELS["tfidf_hybrid"])].iloc[0]
    assert hybrid.median_error == pytest.approx(0.15) and hybrid.mean_error == pytest.approx(0.175)
    assert hybrid.vs_all_analog == pytest.approx(-0.1)  # median of (-0.2, -0.1, -0.1, +0.1)
    assert hybrid.share_better == pytest.approx(0.75)
    assert hybrid.ci_low <= hybrid.median_error <= hybrid.ci_high
    ref = s[(s.subset == "all") & (s.method == ev.LABELS["all_analog_median"])].iloc[0]
    assert np.isnan(ref.vs_all_analog)
    assert s[(s.subset == "all") & (s.method == ev.LABELS["atc4_median"])].fallbacks.iloc[0] == 3
    assert s[s.subset == "peak confirmed"].analogs.iloc[0] == 3


def test_cli_prints_the_table_and_writes_errors(finder_tables, tmp_path):
    out = stdio.StringIO()
    path = tmp_path / "errors.csv"
    errors, summary = ev.main(["--analogs", "o01_oral", "o02_oral", "o05_oral", "--boot", "50", "--out", str(path)],
                              tables=finder_tables, out=out)
    text = out.getvalue()
    for label in ev.LABELS.values():
        assert label in text
    assert "Measuring-tool check" in text
    assert pd.read_csv(path).analog_id.tolist() == ["o01_oral", "o02_oral", "o05_oral"]
