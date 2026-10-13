"""Build data/reference/drug_master.csv from FDA bulk files instead of the openFDA API.

Same output columns as scrapers/openfda.py, plus fields the API doesn't have:
  - first_indication, review/accelerated/breakthrough/orphan flags: CDER NME & New Biologic
    Approvals compilation ("Approved Use(s)" is the indication at original approval)
  - atc_class: NLM RxClass (FDA's EPC is often too broad, e.g. "Kinase Inhibitor")
  - dosing_text: DailyMed SPL "Dosage and Administration" (ceiling on fills per patient)

Sources (downloaded once to data/raw/fda_files/, gitignored):
  Drugs@FDA data files   https://www.fda.gov/drugs/drug-approvals-and-databases/drugsfda-data-files
  NDC Directory          https://www.accessdata.fda.gov/cder/ndctext.zip
  NME compilation        https://www.fda.gov/drugs/drug-approvals-and-databases/compilation-cder-new-molecular-entity-nme-drug-and-new-biologic-approvals
  DailyMed / RxClass APIs (cached via get_json/get_text)

Usage: python -m scrapers.fda_files [--brands ibrance,kisqali] [--refresh]
"""
import argparse
import re
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd
import requests

from scrapers.common import RAW, REFERENCE, USER_AGENT, get_json, get_text, ndc9_from_product_ndc, select_brands, write_brand_rows

FILES = RAW / "fda_files"
DOWNLOADS = {
    "drugsfda.zip": "https://www.fda.gov/media/89850/download?attachment",
    "ndctext.zip": "https://www.accessdata.fda.gov/cder/ndctext.zip",
    "nme_compilation.xlsx": "https://www.fda.gov/media/177921/download?attachment",
}
DAILYMED = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
RXCLASS = "https://rxnav.nlm.nih.gov/REST/rxclass/class/byDrugName.json"
SPL_NS = {"v3": "urn:hl7-org:v3"}
LOINC_INDICATIONS, LOINC_DOSING = "34067-9", "34068-7"


def download(refresh=False):
    """Fetch the bulk files and unzip the Drugs@FDA / NDC text tables."""
    FILES.mkdir(parents=True, exist_ok=True)
    for name, url in DOWNLOADS.items():
        path = FILES / name
        if path.exists() and not refresh:
            continue
        print(f"downloading {name} ...")
        with requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=300) as r:
            r.raise_for_status()
            with path.open("wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
    for name, sub in [("drugsfda.zip", "drugsfda"), ("ndctext.zip", "ndc")]:
        with zipfile.ZipFile(FILES / name) as z:
            for member in z.namelist():
                if member.endswith(".txt") and "/" not in member:  # flat .txt tables only
                    z.extract(member, FILES / sub)


def _tsv(path):
    return pd.read_csv(path, sep="\t", dtype=str, encoding="latin-1", keep_default_na=False)


def load_tables():
    d = FILES / "drugsfda"
    t = {name: _tsv(d / f"{name}.txt") for name in ["Applications", "Products", "Submissions", "SubmissionClass_Lookup"]}
    t["ndc_product"] = _tsv(FILES / "ndc" / "product.txt")
    nme = pd.read_excel(FILES / "nme_compilation.xlsx", dtype=str).fillna("")
    nme.columns = [" ".join(str(c).split()) for c in nme.columns]  # headers have double spaces
    t["nme"] = nme
    return t


def spl_sections(brand):
    """Indications and dosing text from the most recently published DailyMed label for a brand."""
    spls = get_json(f"{DAILYMED}/spls.json", {"drug_name": brand}, source="dailymed").get("data", [])
    spls = [s for s in spls if s["title"].upper().startswith(brand.upper())]
    if not spls:
        return "", "", ""
    spls.sort(key=lambda s: pd.to_datetime(s["published_date"]), reverse=True)
    setid = spls[0]["setid"]
    root = ET.fromstring(get_text(f"{DAILYMED}/spls/{setid}.xml", source="dailymed", suffix=".xml"))
    out = {}
    for sec in root.iter("{urn:hl7-org:v3}section"):
        code = sec.find("v3:code", SPL_NS)
        if code is not None and code.get("code") in (LOINC_INDICATIONS, LOINC_DOSING) and code.get("code") not in out:
            out[code.get("code")] = re.sub(r"\s+", " ", " ".join(sec.itertext())).strip()
    return out.get(LOINC_INDICATIONS, ""), out.get(LOINC_DOSING, ""), "; ".join(s["setid"] for s in spls)


def atc_class(generic):
    data = get_json(RXCLASS, {"drugName": generic.split(";")[0].strip().lower(), "relaSource": "ATC"}, source="rxclass")
    items = data.get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", [])
    return "; ".join(sorted({i["rxclassMinConceptItem"]["className"] for i in items}))


def build_row(t, seed):
    brand_key, brand = seed.brand_key, seed.brand_name
    prods = t["Products"][t["Products"].DrugName.str.upper() == brand.upper()]
    appl_nos = sorted(prods.ApplNo.unique())
    apps = t["Applications"][t["Applications"].ApplNo.isin(appl_nos)]
    subs = t["Submissions"][t["Submissions"].ApplNo.isin(appl_nos)]
    subs = subs.merge(t["SubmissionClass_Lookup"], on="SubmissionClassCodeID", how="left")
    origs = subs[(subs.SubmissionType == "ORIG") & (subs.SubmissionStatus == "AP")].sort_values("SubmissionStatusDate")
    first = origs.iloc[0] if len(origs) else None
    first_app = apps[apps.ApplNo == first.ApplNo].iloc[0] if first is not None else None
    appl_ids = [f"{a.ApplType}{a.ApplNo}" for a in apps.itertuples()]

    # NDC Directory: match brand name AND application number, so unrelated products sharing a name drop out.
    ndc = t["ndc_product"]
    ndc = ndc[(ndc.PROPRIETARYNAME.str.upper() == brand.upper()) & ndc.APPLICATIONNUMBER.isin(appl_ids)]
    epc = sorted({c.strip() for cs in ndc.PHARM_CLASSES for c in cs.split(",") if c.strip().endswith("[EPC]")})

    nme = t["nme"][t["nme"]["Proprietary Name"].str.upper() == brand.upper()]
    nme = nme.iloc[0] if len(nme) else None
    generic = "; ".join(sorted(prods.ActiveIngredient.unique()))
    indications, dosing, setids = spl_sections(brand)
    sub_class = first.SubmissionClassCodeDescription if first is not None else ""

    return {
        "brand_key": brand_key,
        "brand_name": brand,
        "generic_name": generic,
        "application_numbers": "; ".join(sorted(appl_ids)),
        "sponsor": first_app.SponsorName if first_app is not None else "",
        "approval_date": first.SubmissionStatusDate[:10] if first is not None else "",
        "submission_class": sub_class,
        "nme_flag": "New Molecular Entity" in sub_class or nme is not None,
        "route": "; ".join(sorted({f.split(";")[-1] for f in prods.Form})),
        "dosage_forms": "; ".join(sorted(ndc.DOSAGEFORMNAME.unique())),
        "pharm_class_epc": "; ".join(epc),
        "ndc9_list": "; ".join(sorted({ndc9_from_product_ndc(n) for n in ndc.PRODUCTNDC})),
        "n_ndc9": ndc.PRODUCTNDC.nunique(),
        "indications_text": indications[:2000],
        "first_indication": " ".join(nme["Approved Use(s)"].split())[:1000] if nme is not None else "",
        # hand tags live in seed_drugs.csv so re-running this script doesn't wipe them
        "line_of_therapy": getattr(seed, "line_of_therapy", ""),
        "first_in_class": getattr(seed, "first_in_class", ""),
        "review_designation": nme["Review Designation"] if nme is not None else (first.ReviewPriority if first is not None else ""),
        "accelerated_approval": nme["Accelerated Approval"] if nme is not None else "",
        "breakthrough": nme["Breakthrough Therapy Designation"] if nme is not None else "",
        "orphan": nme["Orphan Drug Designation"] if nme is not None else "",
        "atc_class": atc_class(generic) if generic else "",
        "dosing_text": dosing[:1500],
        "dailymed_setids": setids,
        "master_source": "fda_files",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brands", help="comma-separated brand_keys from seed_drugs.csv (default: all)")
    ap.add_argument("--refresh", action="store_true", help="re-download the FDA bulk files")
    args = ap.parse_args()

    download(args.refresh)
    t = load_tables()
    seeds = select_brands(pd.read_csv(REFERENCE / "seed_drugs.csv", dtype=str).fillna(""), args.brands)
    out = pd.DataFrame([build_row(t, r) for r in seeds.itertuples()])
    write_brand_rows(REFERENCE / "drug_master.csv", out, list(seeds.brand_key) if args.brands else None)
    print(out[["brand_key", "application_numbers", "approval_date", "submission_class", "route", "n_ndc9", "atc_class"]].to_string())


if __name__ == "__main__":
    main()
