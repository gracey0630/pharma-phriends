"""Pull national quarterly Medicaid TRx (SDUD) for brands in drug_master.csv.

Rules (see docs/data_collection_plan.md §2.1):
  - national rows only (state == "XX"): totals, never suppressed
  - sum FFSU + MCOU
  - match brands by NDC (labeler + product), not by the truncated product_name

Output: data/processed/sdud_quarterly.csv in the shared long format
        brand_key, source, payer, period, metric, value, pulled_at
        plus data/processed/sdud_ndc_audit.csv for checking NDC coverage.

Usage: python -m scrapers.sdud [--start-year 2011] [--end-year 2026]
"""
import argparse
from datetime import date

import pandas as pd

from scrapers.common import PROCESSED, REFERENCE, get_json

CATALOG = "https://data.medicaid.gov/api/1/search"
QUERY = "https://data.medicaid.gov/api/1/datastore/query/{id}/0"
PAGE = 5000


def dataset_ids():
    """Map year -> SDUD dataset id, looked up from the catalog (ids change when CMS republishes)."""
    data = get_json(CATALOG, {"fulltext": "State Drug Utilization Data", "page-size": 100}, source="sdud", refresh=True)
    ids = {}
    for v in data["results"].values():
        title = v.get("title", "")
        if title.startswith("State Drug Utilization Data ") and title[-4:].isdigit():
            ids[int(title[-4:])] = v["identifier"]
    return ids


def query_all(dataset_id, conditions):
    """Page through a DKAN datastore query."""
    params = {"limit": PAGE}
    for i, (prop, op, val) in enumerate(conditions):
        params[f"conditions[{i}][property]"] = prop
        params[f"conditions[{i}][operator]"] = op
        params[f"conditions[{i}][value]"] = val
    rows, offset = [], 0
    while True:
        data = get_json(QUERY.format(id=dataset_id), {**params, "offset": offset}, source="sdud")
        batch = data.get("results", [])
        rows.extend(batch)
        if len(batch) < PAGE:
            return rows
        offset += PAGE


def pull_brand(brand, ids, start_year, end_year):
    """National rows whose product_name starts with the brand's first 10 chars (SDUD truncation)."""
    prefix = brand[:10].upper()
    rows = []
    for year in range(start_year, end_year + 1):
        if year not in ids:
            continue
        rows += query_all(ids[year], [("state", "=", "XX"), ("product_name", "like", f"{prefix}%")])
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=None, help="default: each brand's approval year")
    ap.add_argument("--end-year", type=int, default=date.today().year)
    args = ap.parse_args()

    master = pd.read_csv(REFERENCE / "drug_master.csv", dtype=str)
    ids = dataset_ids()
    print(f"SDUD years available: {min(ids)}-{max(ids)}")

    long_rows, audit_rows = [], []
    for d in master.itertuples():
        start = args.start_year or int(d.approval_date[:4])
        df = pull_brand(d.brand_name, ids, start, args.end_year)
        if df.empty:
            print(f"{d.brand_key}: no SDUD rows")
            continue
        df["ndc9"] = df["labeler_code"].str.zfill(5) + df["product_code"].str.zfill(4)
        fda_ndc9 = set(str(d.ndc9_list).split("; "))

        # Audit: every NDC found by name, and whether FDA lists it. Name matches outside the
        # FDA list are usually old/discontinued packages (e.g. pre-acquisition labelers).
        for ndc9, g in df.groupby("ndc9"):
            audit_rows.append({
                "brand_key": d.brand_key, "ndc9": ndc9, "product_names": "; ".join(sorted(g["product_name"].str.strip().unique())),
                "in_fda_list": ndc9 in fda_ndc9, "first_period": f"{g.year.min()}", "rx_total": pd.to_numeric(g.number_of_prescriptions, errors="coerce").sum(),
            })

        num = ["number_of_prescriptions", "units_reimbursed", "total_amount_reimbursed"]
        df[num] = df[num].apply(pd.to_numeric, errors="coerce")
        df["period"] = df["year"] + "Q" + df["quarter"]
        df["suppressed"] = df["suppression_used"].astype(str).str.lower() == "true"
        # min_count=1: a quarter where every row is suppressed stays NaN instead of becoming 0.
        # National (XX) rows CAN be suppressed for low-volume brands, so record how many were.
        q = df.groupby("period")[num].sum(min_count=1)
        q["suppressed"] = df.groupby("period")["suppressed"].sum()
        for period, r in q.iterrows():
            for metric, col in [("trx", "number_of_prescriptions"), ("units", "units_reimbursed"),
                                ("reimbursed_usd", "total_amount_reimbursed"), ("suppressed_rows", "suppressed")]:
                long_rows.append({"brand_key": d.brand_key, "source": "sdud", "payer": "medicaid", "period": period,
                                  "metric": metric, "value": r[col], "pulled_at": date.today().isoformat()})
        print(f"{d.brand_key}: {len(df)} rows, {df.ndc9.nunique()} NDC9s, {len(q)} quarters, peak TRx/qtr {q.number_of_prescriptions.max():,.0f}")

    out = pd.DataFrame(long_rows).sort_values(["brand_key", "period", "metric"])
    out.to_csv(PROCESSED / "sdud_quarterly.csv", index=False)
    pd.DataFrame(audit_rows).to_csv(PROCESSED / "sdud_ndc_audit.csv", index=False)
    print(f"wrote {len(out)} rows -> data/processed/sdud_quarterly.csv")


if __name__ == "__main__":
    main()
