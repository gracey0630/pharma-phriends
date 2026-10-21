"""Pull CMS "Spending by Drug" (annual, 2020-2024 release) for brands in drug_master.csv.

Two datasets with the same layout:
  - Medicare Part D Spending by Drug -> data/processed/partd_annual.csv
    claims + beneficiaries -> fills per patient (SDUD has no patient counts)
  - Medicaid Spending by Drug        -> data/processed/medicaid_spending_annual.csv
    annual cross-check on the SDUD quarterly pull (no beneficiary counts)

Earlier Part D years are only in archived releases, not this API.

Metrics (per brand, formulations summed): claims, beneficiaries, spend_usd, dosage_units,
plus brand-level ratios recomputed from the sums (the per-formulation averages can't be summed):
  fills_per_patient, spend_per_claim, spend_per_bene, spend_per_unit, units_per_claim,
and screens: n_manufacturers (Tot_Mftr > 1 suggests generics/biosimilars) and outlier_flag.
price_cagr (spend per unit, first->last year) uses period "YYYY-YYYY".

Output: shared long format. Usage: python -m scrapers.cms_spending [--brands ibrance]
"""
import argparse
import re
from datetime import date

import pandas as pd

from scrapers.common import PROCESSED, REFERENCE, get_json, select_brands, write_brand_rows

DATASETS = {
    # name: (dataset id, payer, output file)
    "partd_spending_by_drug": ("7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b", "medicare", "partd_annual.csv"),
    "medicaid_spending_by_drug": ("be64fce3-e835-4589-b46b-024198e524a6", "medicaid", "medicaid_spending_annual.csv"),
}
URL = "https://data.cms.gov/data-api/v1/dataset/{id}/data"
SUMS = {"Tot_Clms": "claims", "Tot_Benes": "beneficiaries", "Tot_Spndng": "spend_usd", "Tot_Dsg_Unts": "dosage_units"}
MAXES = {"Outlier_Flag": "outlier_flag"}


def pull(dataset_id, d):
    """Rows for one brand: keyword search, then brand-name prefix matches on the "Overall" rows.
    Exact filter[Brnd_Name] misses formulation variants like "Skyrizi On-Body"."""
    hits = get_json(URL.format(id=dataset_id), {"keyword": d.brand_name, "size": 100}, source="cms_spending")
    hits = [h for h in hits if h["Mftr_Name"] == "Overall" and h["Brnd_Name"].upper().startswith(d.brand_name.upper())]
    rows, n_mftr = [], 0
    for h in hits:
        n_mftr = max(n_mftr, int(h.get("Tot_Mftr") or 0))
        for col, val in h.items():
            m = re.fullmatch(r"(\w+?)_(\d{4})", col)
            if m and m.group(1) in {**SUMS, **MAXES} and val not in ("", None):
                rows.append({"formulation": h["Brnd_Name"], "year": m.group(2), "col": m.group(1), "value": float(val)})
    return pd.DataFrame(rows), n_mftr, [h["Brnd_Name"] for h in hits]


def brand_metrics(df):
    """Sum formulations to brand level and recompute ratios. Beneficiaries can double-count patients
    who used two formulations in one year, so fills_per_patient is a slight underestimate for multi-form brands."""
    sums = df[df.col.isin(SUMS)].groupby(["year", "col"])["value"].sum().unstack("col").rename(columns=SUMS)
    maxes = df[df.col.isin(MAXES)].groupby(["year", "col"])["value"].max().unstack("col").rename(columns=MAXES)
    b = sums.join(maxes)
    b["spend_per_claim"] = b.spend_usd / b.claims
    b["spend_per_unit"] = b.spend_usd / b.dosage_units
    b["units_per_claim"] = b.dosage_units / b.claims  # days-supply check vs. the label's dosing
    if "beneficiaries" in b:
        b["fills_per_patient"] = b.claims / b.beneficiaries
        b["spend_per_bene"] = b.spend_usd / b.beneficiaries
    return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brands", help="comma-separated brand_keys (default: all in drug_master.csv)")
    args = ap.parse_args()
    master = select_brands(pd.read_csv(REFERENCE / "drug_master.csv", dtype=str), args.brands)
    today = date.today().isoformat()

    for source, (dataset_id, payer, filename) in DATASETS.items():
        out = []
        print(f"== {source}")
        for d in master.itertuples():
            df, n_mftr, names = pull(dataset_id, d)
            if df.empty:
                print(f"{d.brand_key}: not found")
                continue
            b = brand_metrics(df)
            long = b.stack().rename("value").reset_index().rename(columns={"year": "period", "col": "metric"})
            years = sorted(b.index)
            spu = b.spend_per_unit.dropna()
            extra = [{"period": f"{years[0]}-{years[-1]}", "metric": "n_manufacturers", "value": n_mftr}]
            if len(spu) > 1:
                n = int(spu.index[-1]) - int(spu.index[0])
                extra.append({"period": f"{spu.index[0]}-{spu.index[-1]}", "metric": "price_cagr",
                              "value": (spu.iloc[-1] / spu.iloc[0]) ** (1 / n) - 1})
            long = pd.concat([long, pd.DataFrame(extra)], ignore_index=True)
            out.append(long.assign(brand_key=d.brand_key))
            show = b[[c for c in ["claims", "beneficiaries", "fills_per_patient", "spend_per_claim"] if c in b]].round(1)
            print(f"{d.brand_key} ({', '.join(names)}; manufacturers={n_mftr})\n{show.to_string()}")

        out = (pd.concat(out, ignore_index=True)
               .assign(source=source, payer=payer, pulled_at=today)
               [["brand_key", "source", "payer", "period", "metric", "value", "pulled_at"]]
               .sort_values(["brand_key", "period", "metric"]))
        write_brand_rows(PROCESSED / filename, out, list(master.brand_key) if args.brands else None)
        print(f"wrote {len(out)} rows -> data/processed/{filename}")


if __name__ == "__main__":
    main()
