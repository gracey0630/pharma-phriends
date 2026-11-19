import math

import pandas as pd
import pytest

from analog_finder import io
from analog_finder.tests.conftest import ANALOGS


# --- config -----------------------------------------------------------------------------------------------

def test_defaults_without_scenario(config_dir, tmp_path):
    cfg = io.load_config(config_dir=config_dir, root=tmp_path)
    assert cfg["top_k"] == 5
    assert cfg["weights"] == {"text": 1.0, "atc4": 0.25, "area": 0.1, "line_of_therapy": 1.0}
    assert cfg["paths"]["processed"] == (tmp_path / "data" / "processed").resolve()
    assert cfg["scenario"] is None


def test_preferences_override_only_named_weights(config_dir, scenarios_dir, tmp_path):
    scen = scenarios_dir({"s": "name: S\npreferences: {atc4: 0.5}\n"})
    cfg = io.load_config("s", config_dir=config_dir, scenarios_dir=scen, root=tmp_path)
    assert cfg["weights"] == {"text": 1.0, "atc4": 0.5, "area": 0.1, "line_of_therapy": 1.0}


def test_config_override_merges_nested_keys(config_dir, scenarios_dir, tmp_path):
    scen = scenarios_dir({"s": "config: {top_k: 3, filters: {usable_only: false}}\n"})
    cfg = io.load_config("s", config_dir=config_dir, scenarios_dir=scen, root=tmp_path)
    assert cfg["top_k"] == 3
    assert cfg["filters"] == {"usable_only": False, "match_route_group": True}


def test_scenario_without_overrides_keeps_defaults(config_dir, scenarios_dir, tmp_path):
    scen = scenarios_dir({"s": "name: S\n"})
    assert io.load_config("s", config_dir=config_dir, scenarios_dir=scen, root=tmp_path)["weights"] == \
        io.load_config(config_dir=config_dir, root=tmp_path)["weights"]


@pytest.mark.parametrize("text, error", [
    ("preferences: {atc_4: 0.5}\n", KeyError),        # typo in a feature name
    ("config: {topk: 3}\n", KeyError),                # typo in a config key
    ("config: {filters: true}\n", TypeError),         # a block replaced by a scalar
    ("preferences: {atc4: -1}\n", ValueError),        # negative weight
    ("preferences: {atc4: high}\n", ValueError),      # not a number
])
def test_bad_overrides_fail_clearly(config_dir, scenarios_dir, tmp_path, text, error):
    scen = scenarios_dir({"s": text})
    with pytest.raises(error):
        io.load_config("s", config_dir=config_dir, scenarios_dir=scen, root=tmp_path)


def test_missing_scenario(config_dir, scenarios_dir, tmp_path):
    with pytest.raises(FileNotFoundError, match="nope.yaml"):
        io.load_config("nope", config_dir=config_dir, scenarios_dir=scenarios_dir({}), root=tmp_path)


def test_repo_config_and_torevia_load():
    """The committed scoring.yaml and torevia.yaml are valid together."""
    cfg = io.load_config("torevia")
    assert cfg["top_k"] == 5
    assert cfg["embedder"] in {"tfidf", "rxbert"}
    assert cfg["use_evidence"] is False  # off until an evaluation shows it helps (decisions.md 2026-11-18)
    assert {"text", "atc4", "atc3", "area", "line_of_therapy", "dosing_frequency", "n_competitors",
            "order_of_entry"} == set(cfg["weights"])


# --- tables -----------------------------------------------------------------------------------------------

def test_load_tables(processed_dir):
    tables = io.load_tables(processed_dir)
    assert set(tables) == set(io.TABLES)
    assert list(tables["analog_features"].analog_id) == ANALOGS
    assert len(tables["launch_curves"]) == 9


def test_load_tables_missing_file(processed_dir):
    (processed_dir / "bass_fits.csv").unlink()
    with pytest.raises(FileNotFoundError, match="pipeline.build"):
        io.load_tables(processed_dir)


# --- approved evidence ------------------------------------------------------------------------------------

def test_only_approved_values(reference_dir, evidence_rows):
    ref = reference_dir([
        evidence_rows("alpha_oral", "line_of_therapy", "second line", approved="true"),
        evidence_rows("alpha_oral", "dosing_frequency", "once daily", approved="false"),
        evidence_rows("beta_oral", "launch_date", "2015-08", approved="TRUE"),
        evidence_rows("gamma_sc", "line_of_therapy", "first line", approved=""),
    ])
    wide = io.load_approved_evidence(ref)
    assert list(wide.index) == ["alpha_oral", "beta_oral"]
    assert wide.loc["alpha_oral", "line_of_therapy"] == "second line"
    assert wide.loc["alpha_oral", "line_of_therapy_quote"] == "quote for second line"
    assert wide.loc["alpha_oral", "line_of_therapy_url"] == "https://www.accessdata.fda.gov/alpha_oral.pdf"
    assert pd.isna(wide.loc["alpha_oral", "dosing_frequency"])
    assert wide.loc["beta_oral", "launch_date"] == "2015-08"


def test_columns_follow_pipeline_fields(reference_dir, evidence_rows):
    wide = io.load_approved_evidence(reference_dir([]))
    assert list(wide.columns) == [f"{f}{s}" for f in io.EVIDENCE_FIELDS for s in ("", "_quote", "_url")]
    assert wide.empty


def test_fields_outside_the_four_are_ignored(reference_dir, evidence_rows):
    ref = reference_dir([evidence_rows("alpha_oral", "boxed_warning", "yes", approved="true")])
    assert io.load_approved_evidence(ref).empty


def test_latest_approved_at_wins(reference_dir, evidence_rows):
    ref = reference_dir([
        evidence_rows("alpha_oral", "dosing_frequency", "twice daily", approved="true", approved_at="2026-11-20"),
        evidence_rows("alpha_oral", "dosing_frequency", "once daily", approved="true", approved_at="2026-11-10"),
    ], extra_columns=["approved_at"])
    assert io.load_approved_evidence(ref).loc["alpha_oral", "dosing_frequency"] == "twice daily"


def test_without_approved_at_the_later_row_wins(reference_dir, evidence_rows):
    ref = reference_dir([
        evidence_rows("alpha_oral", "dosing_frequency", "twice daily", approved="true"),
        evidence_rows("alpha_oral", "dosing_frequency", "once daily", approved="true"),
    ])
    assert io.load_approved_evidence(ref).loc["alpha_oral", "dosing_frequency"] == "once daily"


def test_dated_row_beats_undated_row(reference_dir, evidence_rows):
    ref = reference_dir([
        evidence_rows("alpha_oral", "dosing_frequency", "twice daily", approved="true", approved_at="2026-11-20"),
        evidence_rows("alpha_oral", "dosing_frequency", "once daily", approved="true", approved_at=""),
    ], extra_columns=["approved_at"])
    assert io.load_approved_evidence(ref).loc["alpha_oral", "dosing_frequency"] == "twice daily"


def test_reindex_to_candidates(reference_dir, evidence_rows):
    ref = reference_dir([evidence_rows("alpha_oral", "line_of_therapy", "second line", approved="true")])
    wide = io.load_approved_evidence(ref, analog_ids=ANALOGS)
    assert list(wide.index) == ANALOGS
    assert pd.isna(wide.loc["gamma_sc", "line_of_therapy"])


def test_missing_evidence_file_means_no_evidence(tmp_path):
    assert io.load_approved_evidence(tmp_path).empty


def test_evidence_missing_a_column_fails(tmp_path):
    (tmp_path / "analog_evidence.csv").write_text("analog_id,field,value\nalpha_oral,launch_date,2015\n")
    with pytest.raises(ValueError, match="missing columns"):
        io.load_evidence(tmp_path)


def test_repo_evidence_loads():
    """The committed analog_evidence.csv parses; approved values only come from the four fields."""
    wide = io.load_approved_evidence()
    assert set(wide.columns) >= set(io.EVIDENCE_FIELDS)
    assert wide.index.is_unique


# --- outputs ----------------------------------------------------------------------------------------------

def test_write_scenario_outputs(tmp_path):
    weights = pd.DataFrame({"analog_id": ["alpha_oral"], "weight": [1.0]})
    paths = io.write_scenario_outputs("demo", {"analog_weights": weights}, out_dir=tmp_path)
    assert paths["analog_weights"] == tmp_path / "demo" / "analog_weights.csv"
    back = pd.read_csv(paths["analog_weights"])
    assert math.isclose(back.weight.sum(), 1.0)


def test_write_rejects_unknown_output(tmp_path):
    with pytest.raises(ValueError, match="unknown output"):
        io.write_scenario_outputs("demo", {"analog_weight": pd.DataFrame()}, out_dir=tmp_path)
