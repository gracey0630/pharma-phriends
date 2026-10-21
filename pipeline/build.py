"""Build data/processed/analogs.csv: one row per analog_id with exactly the 23 columns of the
team's analog schema (Google Sheet "data schema for analogs"), in the sheet's order.

Steps: FDA files -> candidate pool + ndc_map -> SDUD national rows -> SDUD-only NDCs -> quarterly Rx
       -> generic entry (SDUD) -> ATC class (RxClass) -> label-read values (analog_evidence.csv) -> checks

Outputs (data/processed/, committed):
  analogs.csv          the analog table (analog_id + 23 sheet columns)
  sdud_quarterly.csv   Rx by quarter, long format (the "Rx" column is its total)
  ndc_map.csv          analog_id x ndc9, with how each NDC was matched
  candidate_pool.csv   FDA-side pool before SDUD (intermediate)
  generic_ndcs.csv     possible generic/biosimilar NDCs per brand (for generic / exclusivity date)
  checks.md            validation report

Usage: python -m pipeline.build [--refresh]   (--refresh re-downloads every source)
"""
import argparse

import pandas as pd

from pipeline import checks, fda, ndc, rxclass, sdud
from pipeline.common import PROCESSED, REFERENCE

# Sheet column -> how it's filled. Order is the sheet's order; names are used verbatim as headers.
SCHEMA = [
    "ndc",
    "route of administration",
    "manufacturer/sponsor/company at approval",
    "Rx",
    "generic name",
    "application number",
    "submission classification",
    "line of therapy",
    "approval date",
    "cost per unit",
    "market size",
    "brand name",
    "start marketing date",
    "market category",
    "dosage form",
    "indication",
    "# competitors at launch",
    "novel drugs",
    "launch date",
    "class (narrow)",
    "dosing frequency",
    "fills per patient",
    "generic / exclusivity date",
]
# analog_evidence.csv field -> sheet column (label-read values; agent-extracted, human-approved)
EVIDENCE_FIELDS = {
    "line_of_therapy": "line of therapy",
    "n_competitors_at_launch": "# competitors at launch",
    "launch_date": "launch date",
    "dosing_frequency": "dosing frequency",
}
EVIDENCE_COLS = ["analog_id", "field", "value", "quote", "source_url", "source_type",
                 "extracted_by", "extracted_at", "approved", "approved_by"]


def load_evidence():
    path = REFERENCE / "analog_evidence.csv"
    if not path.exists():
        return pd.DataFrame(columns=EVIDENCE_COLS)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def generic_entry(generics, national, pool):
    """First SDUD quarter in which any generic / biosimilar NDC for the brand was dispensed."""
    hits = national.merge(generics[["brand_key", "ndc9"]], on="ndc9")
    hits["period"] = hits.year + "Q" + hits.quarter
    first = hits.groupby("brand_key").period.min()
    return pool.brand_key.map(first).fillna("")


def assemble(pool, ndc_map, quarterly, generic_q, classes, evidence):
    trx = quarterly[quarterly.metric == "trx"].copy()
    trx["value"] = pd.to_numeric(trx.value, errors="coerce")
    rx_total = trx.groupby("analog_id").value.sum(min_count=1)
    ndcs = ndc_map.groupby("analog_id").ndc9.apply(lambda s: "; ".join(sorted(s)))
    ev = evidence[evidence.field.isin(EVIDENCE_FIELDS)].drop_duplicates(["analog_id", "field"], keep="last")
    ev = ev.pivot(index="analog_id", columns="field", values="value")

    out = pd.DataFrame({"analog_id": pool.analog_id})
    p = pool.set_index("analog_id")
    col = {
        "ndc": out.analog_id.map(ndcs),
        "route of administration": out.analog_id.map(p.route_group),
        "manufacturer/sponsor/company at approval": out.analog_id.map(p.sponsor),
        "Rx": out.analog_id.map(rx_total).map(lambda v: "" if pd.isna(v) else str(int(v))),
        "generic name": out.analog_id.map(p.generic_name),
        "application number": out.analog_id.map(p.application_number),
        "submission classification": out.analog_id.map(p.submission_class),
        "approval date": out.analog_id.map(p.approval_date),
        "cost per unit": "",  # open question (decisions.md)
        "market size": "",  # open question; workstream E (epi funnel)
        "brand name": out.analog_id.map(p.brand_name),
        "start marketing date": out.analog_id.map(p.start_marketing_date),
        "market category": out.analog_id.map(p.market_category),
        "dosage form": out.analog_id.map(p.dosage_form),
        "indication": out.analog_id.map(p.indication),
        "novel drugs": out.analog_id.map(p.novel_drug),
        "class (narrow)": out.analog_id.map(p.generic_name).map(classes),
        "fills per patient": "",  # open question (decisions.md)
        "generic / exclusivity date": generic_q.values,
    }
    for field, sheet_col in EVIDENCE_FIELDS.items():
        col[sheet_col] = out.analog_id.map(ev[field]) if field in ev else ""
    for c in SCHEMA:
        out[c] = col[c]
    return out.fillna("")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download every source")
    args = ap.parse_args()
    PROCESSED.mkdir(parents=True, exist_ok=True)

    fda.download_all(args.refresh)
    pool, ndc_map, generics = fda.build(fda.load_tables())
    sdud.pull(refresh=args.refresh)
    labelers = set(ndc_map.ndc9.str[:5]) | set(generics.ndc9.str[:5])
    national = sdud.load_national(labelers)

    ndc_map = ndc.build(ndc_map, pool, national)
    quarterly = sdud.build(ndc_map, national)
    generic_q = generic_entry(generics, national, pool)
    classes = rxclass.classes(pool.generic_name)
    evidence = load_evidence()
    analogs = assemble(pool, ndc_map, quarterly, generic_q, classes, evidence)

    pool.to_csv(PROCESSED / "candidate_pool.csv", index=False)
    ndc_map.to_csv(PROCESSED / "ndc_map.csv", index=False)
    generics.to_csv(PROCESSED / "generic_ndcs.csv", index=False)
    quarterly.to_csv(PROCESSED / "sdud_quarterly.csv", index=False)
    analogs.to_csv(PROCESSED / "analogs.csv", index=False)
    print(f"analogs.csv: {len(analogs)} analogs x {len(SCHEMA)} schema columns")

    report = checks.run(analogs, ndc_map, quarterly, evidence)
    (PROCESSED / "checks.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
