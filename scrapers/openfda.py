"""Build data/reference/drug_master.csv from openFDA for the brands in seed_drugs.csv.

Usage: python -m scrapers.openfda
"""
import pandas as pd

from scrapers.common import PROCESSED, REFERENCE, env, get_json, ndc9_from_product_ndc

BASE = "https://api.fda.gov/drug"


def _params(search, limit):
    p = {"search": search, "limit": limit}
    if env("OPENFDA_API_KEY"):
        p["api_key"] = env("OPENFDA_API_KEY")
    return p


def fetch_application(brand):
    """Return the Drugs@FDA record(s) for a brand name."""
    data = get_json(f"{BASE}/drugsfda.json", _params(f'openfda.brand_name:"{brand}"', 10), source="openfda")
    return data.get("results", [])


def fetch_ndc_products(brand):
    """Return NDC directory products for a brand (current listings)."""
    data = get_json(f"{BASE}/ndc.json", _params(f'brand_name:"{brand}"', 100), source="openfda")
    return data.get("results", [])


def fetch_label(brand):
    """Return the most recent label's indications text."""
    data = get_json(f"{BASE}/label.json", _params(f'openfda.brand_name:"{brand}"', 1), source="openfda")
    res = data.get("results", [])
    if not res:
        return ""
    return " ".join(res[0].get("indications_and_usage", [])).strip()


def build_row(brand_key, brand):
    apps = fetch_application(brand)
    # Original approvals across all applications for this brand; the earliest is the launch.
    origs = []
    for app in apps:
        for s in app.get("submissions", []):
            if s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP":
                origs.append((s["submission_status_date"], app, s))
    origs.sort(key=lambda x: x[0])
    first_date, first_app, first_sub = origs[0] if origs else (None, apps[0] if apps else {}, {})

    ofda = first_app.get("openfda", {})
    ndcs = set()
    for app in apps:
        ndcs.update(app.get("openfda", {}).get("product_ndc", []))
    products = fetch_ndc_products(brand)
    ndcs.update(p["product_ndc"] for p in products if "product_ndc" in p)
    dosage_forms = sorted({p.get("dosage_form", "") for p in products} - {""})

    return {
        "brand_key": brand_key,
        "brand_name": brand,
        "generic_name": "; ".join(ofda.get("generic_name", [])),
        "application_numbers": "; ".join(sorted(a["application_number"] for a in apps)),
        "sponsor": first_app.get("sponsor_name", ""),
        "approval_date": pd.to_datetime(first_date).date().isoformat() if first_date else "",
        "submission_class": first_sub.get("submission_class_code_description", ""),
        "nme_flag": "New Molecular Entity" in first_sub.get("submission_class_code_description", "")
        or first_app.get("application_number", "").startswith("BLA"),
        "route": "; ".join(ofda.get("route", [])),
        "dosage_forms": "; ".join(dosage_forms),
        "pharm_class_epc": "; ".join(ofda.get("pharm_class_epc", [])),
        "ndc9_list": "; ".join(sorted(ndc9_from_product_ndc(n) for n in ndcs)),
        "n_ndc9": len(ndcs),
        "indications_text": fetch_label(brand)[:2000],
        # Filled by hand / agent later: first indication, line of therapy, first-in-class, competitors at launch
        "first_indication": "",
        "line_of_therapy": "",
        "first_in_class": "",
    }


def main():
    seeds = pd.read_csv(REFERENCE / "seed_drugs.csv")
    rows = [build_row(r.brand_key, r.brand_name) for r in seeds.itertuples()]
    out = pd.DataFrame(rows)
    REFERENCE.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_csv(REFERENCE / "drug_master.csv", index=False)
    print(out[["brand_key", "application_numbers", "approval_date", "submission_class", "route", "n_ndc9"]].to_string())


if __name__ == "__main__":
    main()
