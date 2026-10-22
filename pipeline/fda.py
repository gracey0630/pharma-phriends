"""FDA bulk files -> candidate pool (one row per analog_id) and the FDA side of ndc_map.

Sources (downloaded unchanged to data/raw/<source>/, with a manifest):
  NME compilation  brand, generic, indication at approval (`Approved Use(s)`), approvals through the latest edition
  Drugs@FDA        sponsor, original approval date, submission class, later applications, ANDA approvals
  NDC Directory    NDC <-> brand x route group, dosage form, market category, start marketing date
                   (+ the excluded file, which keeps delisted NDCs such as launch-era packages)
  Purple Book      biosimilars (351(k)) per reference product, for possible generic/biosimilar NDCs

Pool rule (docs/data_model.md): NME / new BLA approved 2010+, route group oral or sc.
One analog = brand x route group; key analog_id = brand_key + "_" + route_group (e.g. skyrizi_sc).

Usage: python -m pipeline.fda [--refresh]
"""
import argparse
import re
import zipfile

import pandas as pd

from pipeline.common import PROCESSED, RAW, date_qnum, download, ndc9, qnum

FIRST_YEAR = 2010
ROUTE_GROUPS = {"ORAL": "oral", "SUBCUTANEOUS": "sc"}  # in scope; everything else is out (IV, IM, topical...)
DOWNLOADS = [
    # (source, file, url)
    ("nme", "nme_compilation.xlsx", "https://www.fda.gov/media/177921/download?attachment"),
    ("drugsfda", "drugsfda.zip", "https://www.fda.gov/media/89850/download?attachment"),
    ("ndc", "ndctext.zip", "https://www.accessdata.fda.gov/cder/ndctext.zip"),
    ("ndc", "ndc_excluded.zip", "https://www.accessdata.fda.gov/cder/ndc_excluded.zip"),
    # monthly file; when FDA posts a newer month, update this URL (list: purplebooksearch.fda.gov/downloads)
    ("purple_book", "purplebook.csv",
     "https://www.accessdata.fda.gov/drugsatfda_docs/PurpleBook/2026/purplebook-search-September-data-download.csv"),
]


def download_all(refresh=False):
    for source, name, url in DOWNLOADS:
        path = download(url, source, name, refresh)
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as z:
                for member in z.namelist():
                    if member.endswith(".txt"):
                        z.extract(member, path.parent / "unzipped")


def _tsv(path):
    return pd.read_csv(path, sep="\t", dtype=str, encoding="latin-1", keep_default_na=False)


def load_tables():
    d, n = RAW / "drugsfda" / "unzipped", RAW / "ndc" / "unzipped"
    t = {name: _tsv(d / f"{name}.txt") for name in ["Applications", "Products", "Submissions", "SubmissionClass_Lookup"]}
    t["ndc"] = pd.concat([_tsv(n / "product.txt").assign(listing="current"),
                          _tsv(n / "Products_excluded.txt").assign(listing="excluded")], ignore_index=True)
    nme = pd.read_excel(RAW / "nme" / "nme_compilation.xlsx", dtype=str).fillna("")
    nme.columns = [" ".join(str(c).split()) for c in nme.columns]  # headers have double spaces
    t["nme"] = nme
    t["purple"] = load_purple_book()
    return t


def load_purple_book():
    """The monthly CSV has a 'changes this month' section first; the full product list starts at the last header."""
    path = RAW / "purple_book" / "purplebook.csv"
    lines = path.read_text(encoding="latin-1").splitlines()
    header = max(i for i, line in enumerate(lines) if line.startswith("N/R/U,"))
    return pd.read_csv(path, skiprows=header, dtype=str, encoding="latin-1", keep_default_na=False)


def brand_key(name):
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def route_group(routename):
    return ROUTE_GROUPS.get(routename.strip().upper(), routename.strip().lower() or "")


def orig_approvals(t):
    """One row per application: its original approval (earliest ORIG + AP) with submission class."""
    s = t["Submissions"].merge(t["SubmissionClass_Lookup"], on="SubmissionClassCodeID", how="left")
    s = s[(s.SubmissionType == "ORIG") & (s.SubmissionStatus == "AP")].copy()
    # same-day ORIG approvals exist (Savaysa: ORIG-1 = NME, ORIG-2 = efficacy; Rydapt: the reverse). The pool
    # comes from the NME compilation, so the Type 1 submission wins, then the lowest number, every run
    s["_not_nme"] = ~s.SubmissionClassCode.fillna("").str.startswith("TYPE 1")
    s["_no"] = pd.to_numeric(s.SubmissionNo, errors="coerce")
    s = s.sort_values(["SubmissionStatusDate", "_not_nme", "_no"], kind="stable").drop(columns=["_not_nme", "_no"])
    s = s.drop_duplicates("ApplNo").merge(t["Applications"], on="ApplNo", how="left")
    return s.set_index("ApplNo")


def nme_brands(t):
    """NME compilation rows approved 2010+, one per brand, with their original application numbers."""
    nme = t["nme"]
    nme = nme[pd.to_numeric(nme["Approval Year"], errors="coerce") >= FIRST_YEAR].copy()
    unnamed = nme["Proprietary Name"].str.contains("without a proprietary name", case=False)
    nme.loc[unnamed, "Proprietary Name"] = nme.loc[unnamed, "Active Ingredient/Moiety"]
    nme["brand_key"] = nme["Proprietary Name"].map(brand_key)
    nme["appl_nos"] = nme.apply(lambda r: [r[f"Application Number({i})"].strip().zfill(6)
                                           for i in (1, 2, 3) if r[f"Application Number({i})"].strip()], axis=1)
    dupes = nme[nme.brand_key.duplicated(keep=False)]
    if len(dupes):
        print(f"warning: {len(dupes)} NME rows share a brand_key; keeping the first: {sorted(dupes.brand_key.unique())}")
    return nme.drop_duplicates("brand_key")


def brand_applications(t, brand):
    """The brand's NME applications plus later NDA/BLAs sold under the same name and ingredient
    (e.g. Ibrance tablets, NDA212436). Returns ['NDA207103', 'NDA212436', ...]."""
    prods = t["Products"].merge(t["Applications"][["ApplNo", "ApplType"]], on="ApplNo")
    nos = set(brand.appl_nos)
    ingredient = brand["Active Ingredient/Moiety"].split()[0].upper().split("-")[0] if brand["Active Ingredient/Moiety"] else ""
    same = prods[(prods.DrugName.str.upper() == brand["Proprietary Name"].upper()) & prods.ApplType.isin(["NDA", "BLA"])
                 & prods.ActiveIngredient.str.upper().str.startswith(ingredient)]
    nos |= set(same.ApplNo)
    types = prods.drop_duplicates("ApplNo").set_index("ApplNo").ApplType
    return sorted(f"{types.get(n, brand['NDA/BLA'])}{n}" for n in nos)


def fda_ndcs(t, brand, appls):
    """All NDC listings (current + excluded) under the brand's applications, with a route group.

    Delisted NDCs in the excluded file have no route. They get the route group of the earliest
    listed NDC under the same application (e.g. Skyrizi's 2019 launch NDC -> sc, because the
    IV kits under the same BLA came later); match_method records that it was inferred.
    """
    ndc = t["ndc"][t["ndc"].APPLICATIONNUMBER.isin(appls)].copy()
    # Under a later application, keep only NDCs sold under this brand name: NDA213051 carries both
    # Rybelsus (its own 2019 launch) and the 2026 Ozempic tablets.
    orig = ndc.APPLICATIONNUMBER.str[3:].isin(brand.appl_nos)
    named = ndc.PROPRIETARYNAME.str.upper().str.startswith(brand["Proprietary Name"].upper())
    ndc = ndc[orig | named]
    if ndc.empty:
        return ndc
    ndc["route_group"] = ndc.ROUTENAME.map(route_group)
    ndc["match_method"] = "application_number"
    known = ndc[ndc.route_group != ""].sort_values("STARTMARKETINGDATE")
    first_route = known.drop_duplicates("APPLICATIONNUMBER").set_index("APPLICATIONNUMBER").route_group
    missing = ndc.route_group == ""
    ndc.loc[missing, "route_group"] = ndc.loc[missing, "APPLICATIONNUMBER"].map(first_route).fillna("unknown")
    ndc.loc[missing, "match_method"] = "application_number; route inferred"
    ndc["ndc9"] = ndc.PRODUCTNDC.map(ndc9)
    ndc["brand_key"] = brand.brand_key
    return ndc


def generic_ndcs(t, appls, brand):
    """NDCs of possible generic / biosimilar entrants: ANDAs with the same active ingredient, and
    351(k) BLAs referencing this brand (Purple Book).

    The entry date itself comes from SDUD (first quarter one of these NDCs is dispensed, see
    pipeline.build), because neither approval nor NDC listing means a product is on the market:
    apremilast and apixaban ANDAs are approved and listed years before patents let them launch.
    """
    nos = [a[3:] for a in appls]
    prods = t["Products"].merge(t["Applications"][["ApplNo", "ApplType"]], on="ApplNo")
    ingredients = set(prods[prods.ApplNo.isin(nos)].ActiveIngredient.str.upper())
    anda = prods[prods.ActiveIngredient.str.upper().isin(ingredients) & (prods.ApplType == "ANDA")]
    pb = t["purple"]
    bios = pb[pb["License Type"].str.startswith("351(k)")
              & (pb["Ref. Product Proprietary Name"].str.upper() == brand["Proprietary Name"].upper())]
    entrants = {f"ANDA{n}" for n in anda.ApplNo} | {f"BLA{n.zfill(6)}" for n in bios["BLA Number"]}
    ndc = t["ndc"][t["ndc"].APPLICATIONNUMBER.isin(entrants)]
    return pd.DataFrame({"brand_key": brand.brand_key, "ndc9": ndc.PRODUCTNDC.map(ndc9),
                         "application_number": ndc.APPLICATIONNUMBER, "labeler_name": ndc.LABELERNAME}).drop_duplicates("ndc9")


INDICATION_CLASSES = {"EFFICACY": "efficacy supplement", "TYPE 6": "new indication application",
                      "TYPE 9": "new indication application", "TYPE 9- BLA": "new indication application",
                      "TYPE 10": "new indication application", "TYPE 10- BLA": "new indication application"}


def indication_history(t, pool, launch):
    """One row per analog x approval that set or may have changed its indications: each ORIG approval under
    the route group's applications, plus EFFICACY supplements and new-indication applications (types 6, 9, 10).
    New-indication applications often have no NDCs of their own (Otezla's psoriasis NDA206088), so they're
    taken from all the brand's applications, not just the route group's.

    kind: anything approved on the first approval date is "original" (Rydapt: two indications the same day);
    later "new indication application" rows are expansions; "efficacy supplement" rows are only *possible*
    expansions, since Drugs@FDA doesn't say whether one adds an indication or only new clinical data (Skyrizi
    has 12). indication and line_of_therapy need label reads and stay blank.
    launch: analog_id -> launch quarter ('2019Q2'), for q_since_launch.
    """
    s = t["Submissions"].merge(t["SubmissionClass_Lookup"], on="SubmissionClassCodeID", how="left")
    s = s[s.SubmissionStatus == "AP"]
    s = s[(s.SubmissionType == "ORIG") | s.SubmissionClassCode.isin(INDICATION_CLASSES)]
    new_indication = set(s[(s.SubmissionType == "ORIG") & s.SubmissionClassCode.isin(INDICATION_CLASSES)].ApplNo)
    brands = nme_brands(t).set_index("brand_key")
    frames = []
    for a in pool.itertuples():
        nos = {n[3:] for n in a.application_number.split("; ")}
        nos |= {n[3:] for n in brand_applications(t, brands.loc[a.brand_key])} & new_indication
        g = s[s.ApplNo.isin(nos)].copy()
        g["kind"] = g.SubmissionClassCode.map(INDICATION_CLASSES).fillna("original")
        # an ORIG classed as efficacy is its own submission for an indication, not a supplement
        g.loc[(g.SubmissionType == "ORIG") & (g.SubmissionClassCode == "EFFICACY"), "kind"] = "new indication application"
        # anything approved with the first approval (Rydapt: AML and mastocytosis the same day) is the original label
        g.loc[g.SubmissionStatusDate <= g.SubmissionStatusDate.min(), "kind"] = "original"
        g["analog_id"] = a.analog_id
        frames.append(g)
    h = pd.concat(frames, ignore_index=True)
    types = t["Applications"].set_index("ApplNo").ApplType
    h["application_number"] = h.ApplNo.map(types) + h.ApplNo
    h["approval_date"] = h.SubmissionStatusDate.str[:10]
    h["q_since_launch"] = [date_qnum(d) - qnum(launch[i]) if i in launch.index else pd.NA
                           for i, d in zip(h.analog_id, h.approval_date)]
    h["q_since_launch"] = h.q_since_launch.astype("Int64")
    h = h.rename(columns={"SubmissionType": "submission_type", "SubmissionNo": "submission_no",
                          "SubmissionClassCodeDescription": "submission_class"})
    h["indication"] = ""
    h["line_of_therapy"] = ""
    cols = ["analog_id", "application_number", "submission_type", "submission_no", "submission_class", "kind",
            "approval_date", "q_since_launch", "indication", "line_of_therapy"]
    return h[cols].sort_values(["analog_id", "approval_date", "application_number"], ignore_index=True)


def build(t):
    """Returns (pool, ndc_map, generics): pool has one row per in-scope analog_id; ndc_map one row per
    analog_id x ndc9; generics one row per brand x possible generic/biosimilar NDC."""
    approvals = orig_approvals(t)
    pool_rows, ndc_frames, generic_frames = [], [], []
    for _, b in nme_brands(t).iterrows():
        appls = brand_applications(t, b)
        ndc = fda_ndcs(t, b, appls)
        orig = approvals.loc[approvals.index.intersection(b.appl_nos)].sort_values("SubmissionStatusDate", kind="stable")
        first = orig.iloc[0] if len(orig) else None
        if ndc.empty:
            print(f"{b.brand_key}: no NDC listings, skipped")
            continue
        ndc_frames.append(ndc)
        generic_frames.append(generic_ndcs(t, appls, b))
        n_routes = ndc.route_group.nunique()  # incl. out-of-scope routes (IV etc.)
        for rg, g in ndc.groupby("route_group"):
            if rg not in ROUTE_GROUPS.values():
                continue
            pool_rows.append({
                "analog_id": f"{b.brand_key}_{rg}",
                "brand_key": b.brand_key,
                "brand_name": b["Proprietary Name"],
                "generic_name": b["Active Ingredient/Moiety"],
                "route_group": rg,
                "application_number": "; ".join(sorted(g.APPLICATIONNUMBER.unique())),
                "sponsor": first.SponsorName if first is not None else b.Applicant,
                "submission_class": first.SubmissionClassCodeDescription if first is not None else "",
                "approval_date": (first.SubmissionStatusDate[:10] if first is not None
                                  else b["FDA Approval Date"][:10]),
                "start_marketing_date": pd.to_datetime(g.STARTMARKETINGDATE.min(), format="%Y%m%d").date().isoformat(),
                "market_category": "; ".join(sorted(set(g.MARKETINGCATEGORYNAME) - {""})),
                "dosage_form": "; ".join(sorted(set(g.DOSAGEFORMNAME) - {""})),
                "indication": " ".join(b["Approved Use(s)"].split()),
                "novel_drug": True,
                "n_route_groups": n_routes,
            })
    ndc_all = pd.concat(ndc_frames, ignore_index=True)
    ndc_all = ndc_all[ndc_all.route_group.isin(ROUTE_GROUPS.values())]
    ndc_all["analog_id"] = ndc_all.brand_key + "_" + ndc_all.route_group
    ndc_map = ndc_all.rename(columns={
        "PRODUCTNDC": "product_ndc", "LABELERNAME": "labeler_name", "APPLICATIONNUMBER": "application_number",
        "DOSAGEFORMNAME": "dosage_form", "ROUTENAME": "route", "STARTMARKETINGDATE": "start_marketing_date",
        "ENDMARKETINGDATE": "end_marketing_date", "PROPRIETARYNAME": "proprietary_name"})
    cols = ["analog_id", "ndc9", "product_ndc", "proprietary_name", "labeler_name", "application_number",
            "dosage_form", "route", "start_marketing_date", "end_marketing_date", "listing", "match_method"]
    # the same product NDC can appear in both files or under several SPL versions
    ndc_map = ndc_map[cols].sort_values(["analog_id", "ndc9", "listing"]).drop_duplicates(["analog_id", "ndc9"])
    return pd.DataFrame(pool_rows), ndc_map.reset_index(drop=True), pd.concat(generic_frames, ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download the FDA bulk files")
    args = ap.parse_args()
    download_all(args.refresh)
    pool, ndc_map, generics = build(load_tables())
    PROCESSED.mkdir(parents=True, exist_ok=True)
    pool.to_csv(PROCESSED / "candidate_pool.csv", index=False)
    ndc_map.to_csv(PROCESSED / "ndc_map.csv", index=False)
    generics.to_csv(PROCESSED / "generic_ndcs.csv", index=False)
    print(f"candidate pool: {len(pool)} analogs ({pool.route_group.value_counts().to_dict()}); "
          f"ndc_map: {len(ndc_map)} NDCs")


if __name__ == "__main__":
    main()
