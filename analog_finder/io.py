"""Loading config, processed tables and approved evidence; writing a scenario's outputs.

Every later step loads through here, so there is one definition of each input
(docs/implementation_plan.md, step 1 and "Shared contracts").

Usage: python -m analog_finder.io --scenario torevia   (prints the merged config and what loads)
"""
import argparse
import copy
from pathlib import Path

import pandas as pd
import yaml

from pipeline.build import EVIDENCE_COLS, EVIDENCE_FIELDS
from pipeline.common import ROOT

PACKAGE = Path(__file__).resolve().parent
CONFIG_DIR = PACKAGE / "config"
SCENARIOS_DIR = PACKAGE / "scenarios"

# Processed tables the finder reads (data/processed/<name>.csv; columns in docs/data_model.md).
TABLES = ["analog_features", "candidate_pool", "launch_curves", "bass_fits", "analogs"]
# Per-forecast outputs (data/scenarios/<scenario>/<name>.csv; columns in docs/data_model.md).
OUTPUTS = ["analog_recommendations", "analog_weights", "uptake_curve"]


# --- config -----------------------------------------------------------------------------------------------

def _read_yaml(path):
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return data


def _merge(base, override, where):
    """Override only the keys named, recursing into nested mappings. Unknown keys are errors (typos)."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if key not in base:
            raise KeyError(f"{where}: unknown key '{key}' (known: {', '.join(base)})")
        if isinstance(base[key], dict):
            if not isinstance(value, dict):
                raise TypeError(f"{where}.{key}: expected a mapping")
            out[key] = _merge(base[key], value, f"{where}.{key}")
        else:
            out[key] = value
    return out


def load_scenario(scenario, scenarios_dir=None):
    """The scenario file as a dict (analog_finder/scenarios/<scenario>.yaml)."""
    return _read_yaml(Path(scenarios_dir or SCENARIOS_DIR) / f"{scenario}.yaml")


def load_config(scenario=None, config_dir=None, scenarios_dir=None, root=None):
    """config/scoring.yaml defaults, merged with the scenario's overrides.

    A scenario's `preferences` override feature weights and its `config` overrides any other key; either way only
    the keys it names change. `paths` come back as absolute Paths (relative to the repo root).
    Returns a dict with `filters`, `weights`, `top_k`, `embedder`, `embedding_models`, `paths` and `scenario`.
    """
    config = _read_yaml(Path(config_dir or CONFIG_DIR) / "scoring.yaml")
    if scenario is not None:
        spec = load_scenario(scenario, scenarios_dir)
        config = _merge(config, spec.get("config") or {}, f"{scenario}.config")
        config["weights"] = _merge(config["weights"], spec.get("preferences") or {}, f"{scenario}.preferences")
    for feature, w in config["weights"].items():
        if not isinstance(w, (int, float)) or isinstance(w, bool) or w < 0:
            raise ValueError(f"weight for '{feature}' must be a number >= 0, got {w!r}")
    root = Path(root or ROOT)
    config["paths"] = {k: (root / v).resolve() for k, v in config["paths"].items()}
    config["scenario"] = scenario
    return config


# --- processed tables -------------------------------------------------------------------------------------

def load_tables(processed=None, names=TABLES):
    """The processed tables the finder reads, as {name: DataFrame}. Raises if one is missing."""
    processed = Path(processed or ROOT / "data" / "processed")
    tables = {}
    for name in names:
        path = processed / f"{name}.csv"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found: run `python -m pipeline.build` or pull data/processed/")
        tables[name] = pd.read_csv(path, dtype={"analog_id": str})
    return tables


# --- evidence ---------------------------------------------------------------------------------------------

def load_evidence(reference=None):
    """data/reference/analog_evidence.csv as strings, every row (approved or not)."""
    path = Path(reference or ROOT / "data" / "reference") / "analog_evidence.csv"
    if not path.exists():
        return pd.DataFrame(columns=EVIDENCE_COLS)
    ev = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in EVIDENCE_COLS if c not in ev.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    return ev


def load_approved_evidence(reference=None, analog_ids=None):
    """Approved label-read values, wide: one row per analog_id (the index).

    Columns: for each field in pipeline.build.EVIDENCE_FIELDS (line_of_therapy, n_competitors_at_launch,
    launch_date, dosing_frequency): `<field>`, `<field>_quote`, `<field>_url`. NaN where no approved value.
    Only rows with approved == true (any case) count; other fields are ignored.
    Two approved rows for the same analog and field: the latest `approved_at` wins; rows without it count as
    oldest, and ties go to the later row in the file (as in pipeline/features.py).
    Rows: analogs with at least one approved value, or exactly `analog_ids` when given.
    """
    ev = load_evidence(reference)
    ev = ev[(ev.approved.str.strip().str.lower() == "true") & ev.field.isin(EVIDENCE_FIELDS)].copy()
    ev["_order"] = range(len(ev))
    stamp = ev["approved_at"] if "approved_at" in ev.columns else pd.Series("", index=ev.index)
    ev["_stamp"] = pd.to_datetime(stamp.where(stamp.str.strip() != ""), errors="coerce")
    ev = ev.sort_values(["_stamp", "_order"], na_position="first").drop_duplicates(["analog_id", "field"], keep="last")

    columns = [f"{f}{suffix}" for f in EVIDENCE_FIELDS for suffix in ("", "_quote", "_url")]
    wide = pd.DataFrame(index=pd.Index(sorted(ev.analog_id.unique()), name="analog_id"), columns=columns, dtype=object)
    for r in ev.itertuples():
        wide.loc[r.analog_id, [r.field, f"{r.field}_quote", f"{r.field}_url"]] = [r.value, r.quote, r.source_url]
    if analog_ids is not None:
        wide = wide.reindex(pd.Index(analog_ids, name="analog_id"))
    return wide


# --- outputs ----------------------------------------------------------------------------------------------

def write_scenario_outputs(scenario, outputs, out_dir=None):
    """Write {name: DataFrame} to data/scenarios/<scenario>/<name>.csv. Returns {name: path}.

    Names must be one of OUTPUTS, so a typo can't create a stray table.
    """
    unknown = set(outputs) - set(OUTPUTS)
    if unknown:
        raise ValueError(f"unknown output(s) {sorted(unknown)}; expected one of {OUTPUTS}")
    folder = Path(out_dir or ROOT / "data" / "scenarios") / scenario
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, df in outputs.items():
        paths[name] = folder / f"{name}.csv"
        df.to_csv(paths[name], index=False)
    return paths


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", default=None)
    args = ap.parse_args()
    cfg = load_config(args.scenario)
    print(f"scenario: {args.scenario or '(defaults only)'}")
    print(f"top_k: {cfg['top_k']}  embedder: {cfg['embedder']}  filters: {cfg['filters']}")
    print("weights:")
    for feature, w in cfg["weights"].items():
        print(f"  {feature:18} {w}")
    tables = load_tables(cfg["paths"]["processed"])
    print("tables: " + ", ".join(f"{k} {len(v)}" for k, v in tables.items()))
    approved = load_approved_evidence(cfg["paths"]["reference"])
    n_values = int(approved[list(EVIDENCE_FIELDS)].notna().sum().sum())
    print(f"approved evidence: {n_values} values for {len(approved)} analogs")
