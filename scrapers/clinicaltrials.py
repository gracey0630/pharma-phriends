"""Pull Phase 3 trials per analog from ClinicalTrials.gov API v2, plus Phase 2 trials that started
before approval (accelerated approvals often rest on a Phase 2, e.g. Ibrance / PALOMA-1).

Supports the "eligible" stage of the epi funnel and the line-of-therapy tag: eligibility text
says who the trial enrolled (e.g. "no prior systemic therapy for advanced disease" = 1L).
Trials that started before FDA approval are the registrational ones for the first indication.

Output: data/processed/ctgov_trials.csv (one row per trial; not long format, it's text)
  lot_hint is a keyword guess (1L / 2L+ / mixed / adjuvant/early), not a curated tag. Read the criteria.
Usage: python -m scrapers.clinicaltrials [--brands ibrance]
"""
import argparse
import re
from datetime import date

import pandas as pd

from scrapers.common import PROCESSED, REFERENCE, get_json, select_brands, write_brand_rows

URL = "https://clinicaltrials.gov/api/v2/studies"
PHASE3 = "AREA[Phase](PHASE3)"  # includes PHASE2/PHASE3 trials, whose phases list contains PHASE3
PHASE2 = "AREA[Phase](PHASE2) AND NOT AREA[Phase](PHASE3)"
# Titles say the setting directly; eligibility text is a fallback, and there "adjuvant" usually means
# *prior* adjuvant therapy in a metastatic trial, so it's only checked in titles.
EARLY = r"\b(neo)?adjuvant\b|early[- ]stage|early breast cancer|high[- ]risk early"
FIRST = r"first[- ]line|1st[- ]line|treatment[- ]na[iï]ve|previously untreated|no prior (systemic|endocrine|anti-?cancer)[^.;]{0,40}(advanced|metasta)|initial endocrine"
LATER = r"second[- ]line|2nd[- ]line|previously treated|refractory|relapsed|progress\w* (on|after|during|following)[^.;]{0,60}(endocrine|therapy|treatment|cdk)"


def lot_hint(title, eligibility):
    t, e = title.lower(), eligibility.lower()
    if re.search(EARLY, t):
        return "adjuvant/early"
    for text in (t, e):
        first, later = re.search(FIRST, text), re.search(LATER, text)
        if first and not later:
            return "1L"
        if later and not first:
            return "2L+"
        if first and later:
            return "mixed"
    return ""


def pull(generic, phases):
    studies, token = [], None
    while True:
        params = {"query.intr": generic, "filter.advanced": phases, "pageSize": 100}
        if token:
            params["pageToken"] = token
        data = get_json(URL, params, source="ctgov")
        studies += data.get("studies", [])
        token = data.get("nextPageToken")
        if not token:
            return studies


def to_row(d, s):
    p = s["protocolSection"]
    ident, status, design = p["identificationModule"], p["statusModule"], p.get("designModule", {})
    sponsor = p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
    elig = p.get("eligibilityModule", {}).get("eligibilityCriteria", "")
    start = status.get("startDateStruct", {}).get("date", "")
    interventions = [i["name"] for i in p.get("armsInterventionsModule", {}).get("interventions", [])]
    return {
        "brand_key": d.brand_key,
        "nct_id": ident["nctId"],
        "acronym": ident.get("acronym", ""),
        "title": ident.get("briefTitle", ""),
        "phase": "/".join(design.get("phases", [])),
        "status": status.get("overallStatus", ""),
        "start_date": start,
        "primary_completion": status.get("primaryCompletionDateStruct", {}).get("date", ""),
        "started_before_approval": bool(start) and start[:7] < d.approval_date[:7],
        "enrollment": design.get("enrollmentInfo", {}).get("count", ""),
        "lead_sponsor": sponsor.get("name", ""),
        "sponsor_class": sponsor.get("class", ""),
        "conditions": "; ".join(p.get("conditionsModule", {}).get("conditions", [])),
        "interventions": "; ".join(interventions),
        "lot_hint": lot_hint(ident.get("briefTitle", "") + " " + ident.get("officialTitle", ""), elig),
        "eligibility": re.sub(r"\s+", " ", elig)[:3000],
        "pulled_at": date.today().isoformat(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brands", help="comma-separated brand_keys (default: all in drug_master.csv)")
    args = ap.parse_args()
    master = select_brands(pd.read_csv(REFERENCE / "drug_master.csv", dtype=str), args.brands)

    rows = []
    for d in master.itertuples():
        generic = d.generic_name.split(";")[0].split("-")[0].strip().lower()  # "risankizumab-rzaa" -> "risankizumab"
        p3 = [to_row(d, s) for s in pull(generic, PHASE3)]
        p2 = [r for r in (to_row(d, s) for s in pull(generic, PHASE2)) if r["started_before_approval"]]
        rows += p3 + p2
        pre = sum(r["started_before_approval"] for r in p3)
        print(f"{d.brand_key} ({generic}): {len(p3)} phase 3 trials ({pre} started before approval), {len(p2)} pre-approval phase 2")

    out = pd.DataFrame(rows).sort_values(["brand_key", "start_date"])
    write_brand_rows(PROCESSED / "ctgov_trials.csv", out, list(master.brand_key) if args.brands else None)
    print(f"wrote {len(out)} rows -> data/processed/ctgov_trials.csv")


if __name__ == "__main__":
    main()
