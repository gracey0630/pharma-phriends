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


# --- finder fixtures (steps 3-7) ----------------------------------------------------------------------------

# 12 usable oral analogs (o01-o12), 1 usable sc analog, and 3 oral analogs each dropped by one funnel rule.
# o01-o04 are antipsychotics for schizophrenia (o01, o02 share ATC 4 N05AX), so a schizophrenia target ranks them first.
_FINDER = [
    # analog_id, brand, ATC 4 label, ATC 3 label, area label, indication
    ("o01_oral", "Oone", "N05AX Other antipsychotics", "N05A ANTIPSYCHOTICS", "N NERVOUS SYSTEM",
     "OONE is indicated for the treatment of schizophrenia in adults."),
    ("o02_oral", "Otwo", "N05AX Other antipsychotics", "N05A ANTIPSYCHOTICS", "N NERVOUS SYSTEM",
     "OTWO is indicated for the treatment of schizophrenia and bipolar I disorder."),
    ("o03_oral", "Othree", "N05AE Indole derivatives", "N05A ANTIPSYCHOTICS", "N NERVOUS SYSTEM",
     "OTHREE is indicated for the treatment of patients with schizophrenia."),
    ("o04_oral", "Ofour", "N05AH Diazepines, oxazepines", "N05A ANTIPSYCHOTICS", "N NERVOUS SYSTEM",
     "OFOUR is indicated for schizophrenia in adults."),
    ("o05_oral", "Ofive", "N06AX Other antidepressants", "N06A ANTIDEPRESSANTS", "N NERVOUS SYSTEM",
     "OFIVE is indicated for major depressive disorder in adults."),
    ("o06_oral", "Osix", "N02CD CGRP antagonists", "N02C ANTIMIGRAINE PREPARATIONS", "N NERVOUS SYSTEM",
     "OSIX is indicated for the acute treatment of migraine."),
    ("o07_oral", "Oseven", "A10BK SGLT2 inhibitors", "A10B BLOOD GLUCOSE LOWERING DRUGS", "A ALIMENTARY TRACT",
     "OSEVEN is indicated to improve glycemic control in adults with type 2 diabetes mellitus."),
    ("o08_oral", "Oeight", "A10BH DPP-4 inhibitors", "A10B BLOOD GLUCOSE LOWERING DRUGS", "A ALIMENTARY TRACT",
     "OEIGHT is indicated as an adjunct to diet and exercise in type 2 diabetes mellitus."),
    ("o09_oral", "Onine", "L01EF CDK inhibitors", "L01E PROTEIN KINASE INHIBITORS", "L ANTINEOPLASTIC",
     "ONINE is indicated for HR-positive, HER2-negative advanced breast cancer."),
    ("o10_oral", "Oten", "L04AF JAK inhibitors", "L04A IMMUNOSUPPRESSANTS", "L ANTINEOPLASTIC",
     "OTEN is indicated for moderately to severely active rheumatoid arthritis."),
    ("o11_oral", "Oeleven", "", "", "",
     "OELEVEN is indicated for chronic hepatitis C infection."),
    ("o12_oral", "Otwelve", "C10AX Other lipid modifying agents", "C10A LIPID MODIFYING AGENTS", "C CARDIOVASCULAR",
     "OTWELVE is indicated to reduce LDL cholesterol."),
    ("s01_sc", "Sone", "L04AC Interleukin inhibitors", "L04A IMMUNOSUPPRESSANTS", "L ANTINEOPLASTIC",
     "SONE is indicated for moderate to severe plaque psoriasis."),
    ("late_oral", "Late", "N05AX Other antipsychotics", "N05A ANTIPSYCHOTICS", "N NERVOUS SYSTEM",
     "LATE is indicated for schizophrenia."),
    ("gen_oral", "Gen", "N05AX Other antipsychotics", "N05A ANTIPSYCHOTICS", "N NERVOUS SYSTEM",
     "GEN is indicated for schizophrenia."),
    ("thin_oral", "Thin", "N05AX Other antipsychotics", "N05A ANTIPSYCHOTICS", "N NERVOUS SYSTEM",
     "THIN is indicated for schizophrenia."),
]
FINDER_USABLE_ORAL = [f"o{i:02d}_oral" for i in range(1, 13)]


@pytest.fixture
def finder_tables():
    """io.load_tables()-shaped dict for the finder: 16 analogs, Q0-Q20 curves, Bass fits."""
    ids = [r[0] for r in _FINDER]
    n = len(ids)
    feats = pd.DataFrame({
        "analog_id": ids,
        "route_group": [i.rsplit("_", 1)[1] for i in ids],
        "class_narrow": [r[2] or None for r in _FINDER],
        "class_broad": [r[3] or None for r in _FINDER],
        "therapeutic_area": [r[4] or None for r in _FINDER],
        "launch_quarter": ["2015Q1"] * n,
        "late_launch": [i == "late_oral" for i in ids],
        "generic_entry_in_window": [i == "gen_oral" for i in ids],
        "enough_data": [i != "thin_oral" for i in ids],
        "label_expansion_in_window": [i in ("o02_oral", "o03_oral") for i in ids],
        "multi_route": [i == "o04_oral" for i in ids],
        "low_volume": [i == "o06_oral" for i in ids],
        "peak_confirmed": [i not in ("o04_oral",) for i in ids],
    })
    pool = pd.DataFrame({"analog_id": ids, "brand_name": [r[1] for r in _FINDER]})
    analogs = pd.DataFrame({"analog_id": ids, "brand name": [r[1] for r in _FINDER],
                            "dosage form": ["TABLET"] * (n - 4) + ["INJECTION"] + ["TABLET"] * 3,
                            "indication": [r[5] for r in _FINDER]})
    fits = pd.DataFrame({"analog_id": [i for i in ids if i != "o05_oral"]})
    fits["p"], fits["q"], fits["m"], fits["fit_quality"] = 0.02, 0.3, 1.0, 0.98
    fits["weak_fit_flag"] = fits.analog_id == "o06_oral"
    fits["low_volume"] = fits.analog_id == "o06_oral"
    rows = []
    for k, a in enumerate(ids):
        last = 14 if a == "o04_oral" else 20  # o04 has a short curve (recent launch)
        for q in range(last + 1):
            share = min(1.0, (q + 1) / (10 + k))
            rows.append({"analog_id": a, "q_since_launch": q, "share_of_peak": round(share, 4),
                         "provisional": a == "o04_oral" and q >= 13})
    curves = pd.DataFrame(rows)
    return {"analog_features": feats, "candidate_pool": pool, "analogs": analogs, "bass_fits": fits,
            "launch_curves": curves}


@pytest.fixture
def schizo_target():
    from analog_finder.finder.target import from_dict
    return from_dict({"name": "Tgt", "indication": "TGT is indicated for the treatment of schizophrenia in adults.",
                      "class_narrow": "N05AX", "route_group": "oral", "dosage_form": "TABLET",
                      "line_of_therapy": "later", "dosing_frequency": "once daily",
                      "n_competitors_at_launch": 6})
