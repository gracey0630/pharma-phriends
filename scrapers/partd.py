"""Pull Medicare Part D Spending by Drug (annual) for brands in drug_master.csv.

Gives claims and beneficiaries per year -> fills per patient (SDUD has no patient counts).
The current release covers 2020-2024 only; earlier years are in archived releases.

Output: data/processed/partd_annual.csv (shared long format)
Usage: python -m scrapers.partd
"""
import re
from datetime import date

import pandas as pd

from scrapers.common import PROCESSED, REFERENCE, get_json

DATASET = "7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b"  # "Medicare Part D Spending by Drug", 2024 release
URL = f"https://data.cms.gov/data-api/v1/dataset/{DATASET}/data"
METRICS = {"Tot_Clms": "claims", "Tot_Benes": "beneficiaries", "Tot_Spndng": "spend_usd", "Tot_Dsg_Unts": "dosage_units"}


def main():
    master = pd.read_csv(REFERENCE / "drug_master.csv", dtype=str)
    rows = []
    for d in master.itertuples():
        # keyword search, then keep brand-name prefix matches: exact filter misses "Skyrizi On-Body" etc.
        hits = get_json(URL, {"keyword": d.brand_name, "size": 100}, source="partd")
        hits = [h for h in hits if h["Mftr_Name"] == "Overall" and h["Brnd_Name"].upper().startswith(d.brand_name.upper())]
        for h in hits:
            for col, val in h.items():
                m = re.fullmatch(r"(Tot_\w+?)_(\d{4})", col)
                if m and m.group(1) in METRICS and val not in ("", None):
                    rows.append({"brand_key": d.brand_key, "formulation": h["Brnd_Name"], "year": m.group(2),
                                 "metric": METRICS[m.group(1)], "value": float(val)})
        print(f"{d.brand_key}: {len(hits)} Part D brand rows ({', '.join(h['Brnd_Name'] for h in hits)})")

    df = pd.DataFrame(rows)
    # Sum formulations to brand level. Beneficiaries can double-count patients who used two
    # formulations in one year, so fills_per_patient is a slight underestimate for multi-form brands.
    brand = df.groupby(["brand_key", "year", "metric"])["value"].sum().unstack("metric")
    brand["fills_per_patient"] = brand["claims"] / brand["beneficiaries"]
    out = (brand.stack().rename("value").reset_index()
           .rename(columns={"year": "period"})
           .assign(source="partd_spending_by_drug", payer="medicare", pulled_at=date.today().isoformat()))
    out = out[["brand_key", "source", "payer", "period", "metric", "value", "pulled_at"]]
    out.to_csv(PROCESSED / "partd_annual.csv", index=False)
    print(brand[["claims", "beneficiaries", "fills_per_patient"]].round(2).to_string())


if __name__ == "__main__":
    main()
