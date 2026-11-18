import math

import numpy as np
import pandas as pd
import pytest

from analog_finder.finder import embed, filters, rerank, score

ALL = {f: 1.0 for f in score.FEATURES}


def _setup(finder_tables, target, evidence=None):
    c = filters.candidates(finder_tables, target)
    e = embed.embed(c, evidence, target, finder_tables["analog_features"], embed.TfidfEmbedder())
    return c, e


def test_formula_is_weighted_average_over_available_features(finder_tables, schizo_target):
    c, e = _setup(finder_tables, schizo_target)
    weights = {**ALL, "text": 2.0, "atc4": 1.0, "atc3": 0.5, "area": 0.25}
    s = score.score(c, e, None, schizo_target, weights).set_index("analog_id")
    r = s.loc["o01_oral"]
    expected = (2 * r.s_text + 1 * r.s_atc4 + 0.5 * r.s_atc3 + 0.25 * r.s_area) / 3.75
    assert r.similarity == pytest.approx(expected, abs=1e-6)
    assert r.n_features_used == 4  # no approved evidence, no order of entry


def test_missing_features_are_left_out_not_mismatches(finder_tables, schizo_target):
    c, e = _setup(finder_tables, schizo_target)
    s = score.score(c, e, None, schizo_target, ALL).set_index("analog_id")
    assert np.isnan(s.loc["o11_oral", "s_atc4"])          # o11 has no ATC class
    assert s.loc["o11_oral", "n_features_used"] == 1      # text only
    assert s.loc["o11_oral", "similarity"] == pytest.approx(s.loc["o11_oral", "s_text"], abs=1e-6)


def test_ranking_sorted_and_reproducible(finder_tables, schizo_target):
    c, e = _setup(finder_tables, schizo_target)
    s = score.score(c, e, None, schizo_target, ALL)
    assert list(s["rank"]) == list(range(1, 13))
    assert s.similarity.is_monotonic_decreasing
    assert set(s.analog_id[:4]) == {"o01_oral", "o02_oral", "o03_oral", "o04_oral"}  # the antipsychotics
    assert s.analog_id[0] == "o01_oral"  # same ATC 4 and the closest indication text
    assert s.equals(score.score(c, e, None, schizo_target, ALL))


def test_ties_broken_by_analog_id(finder_tables, schizo_target):
    c, e = _setup(finder_tables, schizo_target)
    e = {**e, "vectors": np.zeros_like(e["vectors"])}  # all text similarities 0
    s = score.score(c, e, None, schizo_target, {"text": 1.0})
    assert list(s.analog_id) == sorted(s.analog_id)


def test_weight_override_changes_the_ranking(finder_tables, schizo_target):
    c, e = _setup(finder_tables, schizo_target)
    base = score.score(c, e, None, schizo_target, {"text": 1.0, "atc4": 0.0})
    atc = score.score(c, e, None, schizo_target, {"text": 0.01, "atc4": 10.0})
    assert set(atc.analog_id[:2]) == {"o01_oral", "o02_oral"}  # the two N05AX analogs
    assert not base.s_atc4.isna().all()  # still computed, just weighted 0
    assert (base.n_features_used == 1).all()  # a 0-weight feature doesn't count as used


def test_approved_evidence_is_scored(finder_tables, schizo_target):
    ev = pd.DataFrame({"line_of_therapy": ["no prior therapy required", "after a generic antipsychotic"],
                       "dosing_frequency": ["twice daily (after titration)", "once daily"],
                       "n_competitors_at_launch": ["2", "6"]},
                      index=pd.Index(["o03_oral", "o04_oral"], name="analog_id"))
    c, e = _setup(finder_tables, schizo_target, ev)
    s = score.score(c, e, ev, schizo_target, ALL).set_index("analog_id")
    assert s.loc["o03_oral", ["s_line_of_therapy", "s_dosing_frequency", "s_n_competitors"]].tolist() == \
        pytest.approx([0.0, 0.5, 1 / 3])
    assert s.loc["o04_oral", ["s_line_of_therapy", "s_dosing_frequency", "s_n_competitors"]].tolist() == [1, 1, 1]
    assert s.loc["o04_oral", "n_features_used"] == 7


def test_bad_weights(finder_tables, schizo_target):
    c, e = _setup(finder_tables, schizo_target)
    with pytest.raises(ValueError, match="unknown feature"):
        score.score(c, e, None, schizo_target, {"txt": 1.0})
    with pytest.raises(ValueError, match="every feature weight is 0"):
        score.score(c, e, None, schizo_target, {"text": 0.0})


@pytest.mark.parametrize("text, group", [
    ("no prior therapy required", "first"),
    ("no prior therapy required (systemic or phototherapy candidates)", "first"),
    ("after other systemic therapy", "later"),
    ("1L metastatic (initial endocrine-based therapy)", "first"),
    ("after at least one generic antipsychotic", "later"),
    ("patients with inadequate response to TNF blockers", "later"),
    ("second line", "later"),
    ("treatment of schizophrenia", None),
    ("", None),
])
def test_line_groups(text, group):
    assert score.line_group(text) == group


@pytest.mark.parametrize("text, per_week", [
    ("once daily", 7), ("twice daily (after 5-day titration)", 14), ("three times daily", 21),
    ("every 4 weeks (weekly loading, weeks 0-4)", 0.25), ("every 8 weeks (after weeks 0 and 4)", 0.125),
    ("every 12 weeks (after weeks 0 and 4)", 1 / 12), ("every 2 weeks (weekly loading, weeks 0-2)", 0.5),
    ("once daily, 21 days on / 7 days off", 7), ("once weekly", 1), ("every other day", 3.5),
    ("monthly", 7 / 30.44), ("as needed", None), (None, None),
])
def test_doses_per_week(text, per_week):
    got = score.doses_per_week(text)
    assert (got is None and per_week is None) or got == pytest.approx(per_week)


def test_similarity_functions():
    assert score.dosing_similarity("once daily", "twice daily") == pytest.approx(0.5)
    assert score.dosing_similarity("once daily", "once daily") == 1
    assert score.count_similarity(6, "8") == pytest.approx(0.5)
    assert math.isnan(score.count_similarity(6, ""))
    assert score.class_match("N05AX", "G03AA; N05AX") == 1.0 and score.class_match("N05AX", "N05AE") == 0.0


def test_rerank_is_a_pass_through(finder_tables, schizo_target):
    c, e = _setup(finder_tables, schizo_target)
    s = score.score(c, e, None, schizo_target, ALL)
    assert rerank.rerank(s) is s
