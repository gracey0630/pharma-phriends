"""Small fixture tables, so tests run offline in milliseconds and don't move when data/processed is rebuilt.

Column names match data/processed/ and data/reference/analog_evidence.csv (docs/data_model.md); only the columns
the tests need carry values.
"""
import textwrap

import pandas as pd
import pytest

from pipeline.build import EVIDENCE_COLS

ANALOGS = ["alpha_oral", "beta_oral", "gamma_sc"]


@pytest.fixture
def processed_dir(tmp_path):
    """data/processed with 3 analogs: alpha and beta oral, gamma sc."""
    d = tmp_path / "processed"
    d.mkdir()
    pd.DataFrame({
        "analog_id": ANALOGS, "route_group": ["oral", "oral", "sc"],
        "therapeutic_area": ["N NERVOUS SYSTEM", "N NERVOUS SYSTEM", "L ANTINEOPLASTIC AND IMMUNOMODULATING AGENTS"],
        "class_narrow": ["N05AX Other antipsychotics", "N05AE Indole derivatives", "L04AC Interleukin inhibitors"],
        "enough_data": [True, True, False],
    }).to_csv(d / "analog_features.csv", index=False)
    pd.DataFrame({"analog_id": ANALOGS, "brand_name": ["Alpha", "Beta", "Gamma"],
                  "route_group": ["oral", "oral", "sc"]}).to_csv(d / "candidate_pool.csv", index=False)
    pd.DataFrame({"analog_id": [a for a in ANALOGS for _ in range(3)], "q_since_launch": [0, 1, 2] * 3,
                  "share_of_peak": [0.1, 0.3, 0.5, 0.2, 0.4, 0.6, 0.0, 0.1, 0.2]}).to_csv(d / "launch_curves.csv", index=False)
    pd.DataFrame({"analog_id": ANALOGS[:2], "p": [0.01, 0.02], "q": [0.3, 0.4], "m": [1.0, 0.9],
                  "weak_fit_flag": [False, True]}).to_csv(d / "bass_fits.csv", index=False)
    pd.DataFrame({"analog_id": ANALOGS, "brand name": ["Alpha", "Beta", "Gamma"]}).to_csv(d / "analogs.csv", index=False)
    return d


def _evidence_row(analog_id, field, value, approved="false", **extra):
    row = dict.fromkeys(EVIDENCE_COLS, "")
    row.update(analog_id=analog_id, field=field, value=value, quote=f"quote for {value}",
               source_url=f"https://www.accessdata.fda.gov/{analog_id}.pdf", source_type="ORIG label",
               approved=approved, **extra)
    return row


@pytest.fixture
def evidence_rows():
    """Builder for analog_evidence rows: evidence_rows(analog_id, field, value, approved=..., approved_at=...)."""
    return _evidence_row


@pytest.fixture
def reference_dir(tmp_path):
    """data/reference holding a given list of evidence rows: reference_dir(rows) -> folder."""
    def make(rows, extra_columns=()):
        d = tmp_path / "reference"
        d.mkdir(exist_ok=True)
        pd.DataFrame(rows, columns=list(EVIDENCE_COLS) + list(extra_columns)).to_csv(
            d / "analog_evidence.csv", index=False)
        return d
    return make


@pytest.fixture
def config_dir(tmp_path):
    """A scoring.yaml with fixed weights, so config tests don't move when the real defaults are tuned."""
    d = tmp_path / "config"
    d.mkdir()
    (d / "scoring.yaml").write_text(textwrap.dedent("""\
        top_k: 5
        embedder: tfidf
        embedding_models: {rxbert: seldas/rxbert-v1}
        filters: {usable_only: true, match_route_group: true}
        weights: {text: 1.0, atc4: 0.25, area: 0.1, line_of_therapy: 1.0}
        paths: {processed: data/processed, reference: data/reference, scenarios_out: data/scenarios, cache: data/cache}
        """))
    return d


@pytest.fixture
def scenarios_dir(tmp_path):
    """Folder for scenario YAMLs: scenarios_dir({name: yaml_text}) -> folder."""
    def make(files):
        d = tmp_path / "scenarios"
        d.mkdir(exist_ok=True)
        for name, text in files.items():
            (d / f"{name}.yaml").write_text(textwrap.dedent(text))
        return d
    return make
