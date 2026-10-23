"""class (narrow) = ATC level 4 from the NLM RxClass API (e.g. risankizumab -> L04AC Interleukin inhibitors).
class_broad (ATC level 3) and the therapeutic area (ATC level 1) are looked up from the level-4 codes.

ATC is revised yearly; the RxNav version is recorded in data/raw/rxclass/manifest.csv on each run.

Usage: python -m pipeline.rxclass   (prints the class for every analog in candidate_pool.csv)
"""
import csv
import re

import pandas as pd

from pipeline.common import PROCESSED, RAW, get_json, today

BY_DRUG = "https://rxnav.nlm.nih.gov/REST/rxclass/class/byDrugName.json"
BY_ID = "https://rxnav.nlm.nih.gov/REST/rxclass/class/byId.json"
VERSION = "https://rxnav.nlm.nih.gov/REST/version.json"
INGREDIENT_SEP = r";| and |,|/"
LOCAL_ROUTE_GROUPS = ("D", "S")  # dermatologicals, sensory organs: topical and eye/ear forms


def ingredient(generic_name):
    """'risankizumab-rzaa' -> 'risankizumab'; combinations ('a and b', 'a; b') -> first ingredient."""
    first = re.split(INGREDIENT_SEP, generic_name.lower())[0].strip()
    return re.sub(r"-[a-z]{4}$", "", first)  # biologic 4-letter suffix


def is_combination(generic_name):
    """'ledipasvir, sofosbuvir' -> True; 'risankizumab-rzaa' -> False."""
    return len(re.split(INGREDIENT_SEP, generic_name.lower())) > 1


def atc4(generic_name):
    """'L04AC Interleukin inhibitors' (several joined with '; '), or '' if RxClass has no ATC class.

    RxClass returns the classes of every product with the ingredient. Two rules keep the analog's own class:
      - single-ingredient brands: only classes found on the ingredient itself (tty IN), not on combination
        products (MIN): empagliflozin is A10BK SGLT2, not A10BD "combinations" (Synjardy); liraglutide is A10BJ
        GLP-1, not A10AE insulin (Xultophy). Combination brands (Natazia, Harvoni) keep their combination classes.
      - the pool is oral and sc, so topical / eye classes (ATC D, S) go when another class remains:
        ruxolitinib is L01EJ JAK, not D11AH (Opzelura cream); dupilumab keeps its only class, D11AH
    Classes still several after that are kept, '; '-joined, and listed in checks.md.
    """
    data = get_json(BY_DRUG, {"drugName": ingredient(generic_name), "relaSource": "ATC"}, source="rxclass")
    items = data.get("rxclassDrugInfoList", {}).get("rxclassDrugInfo", [])
    if not is_combination(generic_name):
        single = [i for i in items if i["minConcept"]["tty"] == "IN"]
        items = single or items  # no single-ingredient class: keep what there is
    classes = {(i["rxclassMinConceptItem"]["classId"], i["rxclassMinConceptItem"]["className"]) for i in items}
    classes = {(cid, name) for cid, name in classes if len(cid) == 5}
    systemic = {(cid, name) for cid, name in classes if not cid.startswith(LOCAL_ROUTE_GROUPS)}
    return "; ".join(f"{cid} {name}" for cid, name in sorted(systemic or classes))


def class_name(class_id):
    """ATC class id at any level ('L', 'L04A') -> its name ('IMMUNOSUPPRESSANTS'), or '' if RxClass doesn't know it."""
    data = get_json(BY_ID, {"classId": class_id}, source="rxclass")
    items = data.get("rxclassMinConceptList", {}).get("rxclassMinConcept", [])
    return items[0]["className"] if items else ""


def broader(atc4_classes, level):
    """'L04AC Interleukin inhibitors; L04AA ...' -> the level-1 ('L ANTINEOPLASTIC ...') or level-3
    ('L04A IMMUNOSUPPRESSANTS') classes they belong to, '; '-joined. level is 1 or 3."""
    ids = sorted({c.split()[0][:{1: 1, 3: 4}[level]] for c in atc4_classes.split("; ") if c})
    return "; ".join(f"{i} {class_name(i)}" for i in ids)


def log_version():
    version = get_json(VERSION, source="rxclass", refresh=True)
    manifest = RAW / "rxclass" / "manifest.csv"
    new = not manifest.exists()
    with manifest.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["pulled_at", "url", "version"])
        w.writerow([today(), BY_DRUG, version.get("version", "")])


def classes(generic_names):
    """Map generic_name -> ATC level 4 class for every name given."""
    log_version()
    return {g: atc4(g) for g in sorted(set(generic_names))}


if __name__ == "__main__":
    pool = pd.read_csv(PROCESSED / "candidate_pool.csv", dtype=str, keep_default_na=False)
    for g, c in classes(pool.generic_name).items():
        print(f"{g:40s} {c}")
