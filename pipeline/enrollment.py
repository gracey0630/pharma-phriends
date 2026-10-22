"""Medicaid & CHIP enrollment by quarter, plus the enrollment-shock windows used to flag analog curves.

Source: data.medicaid.gov "State Medicaid and CHIP Applications, Eligibility Determinations, and Enrollment
Data". One row per state x month x preliminary/updated; we keep the updated (final_report = Y) rows, sum the
states and average the months of each quarter. Saved unchanged to data/raw/enrollment/enrollment.csv.

Coverage: one baseline month (2013-09), then monthly from 2017-06. 2013-10 to 2017-05 isn't in the dataset,
so v1 flags shock windows and doesn't normalize curves by enrollment (decision 2026-10-22).

Output: data/processed/medicaid_enrollment.csv, one row per quarter from 2010Q1:
        period, enrollees (blank where the dataset has no month), months, shock

Usage: python -m pipeline.enrollment [--refresh]
"""
import argparse
import csv

import pandas as pd

from pipeline.common import PROCESSED, RAW, _fetch, get_json, log_manifest, qnum, qstr

CATALOG = "https://data.medicaid.gov/api/1/search"
QUERY = "https://data.medicaid.gov/api/1/datastore/query/{id}/0"
TITLE = "State Medicaid and CHIP Applications, Eligibility Determinations, and Enrollment Data"
PAGE = 8000
COLS = ["state_abbreviation", "reporting_period", "preliminary_or_updated", "final_report",
        "total_medicaid_and_chip_enrollment"]
FIRST_PERIOD = "2010Q1"  # same start as SDUD
# (name, first quarter, last quarter): fixed windows, since enrollment data before 2017 is missing
SHOCKS = [
    ("2014 expansion", "2014Q1", "2015Q4"),  # ACA expansion starts Jan 2014; later states join through 2015
    ("COVID continuous coverage", "2020Q2", "2023Q1"),  # continuous enrollment Mar 2020 - Mar 2023
    ("unwinding", "2023Q2", "2024Q4"),  # redeterminations restart Apr 2023
]


def dataset():
    data = get_json(CATALOG, {"fulltext": TITLE, "page-size": 50}, source="enrollment", refresh=True)
    for v in data["results"].values():
        if v.get("title") == TITLE:
            return v["identifier"], v.get("modified", "")
    raise RuntimeError(f"data.medicaid.gov catalog has no dataset titled {TITLE!r}")


def pull(refresh=False):
    """Save every row of the dataset (the enrollment columns only) to data/raw/enrollment/enrollment.csv."""
    path = RAW / "enrollment" / "enrollment.csv"
    if path.exists() and not refresh:
        return path
    dataset_id, modified = dataset()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows, offset = [], 0
    while True:
        params = {"limit": PAGE, "offset": offset, "results": "true"}
        for i, c in enumerate(COLS):
            params[f"properties[{i}]"] = c
        resp = _fetch(QUERY.format(id=dataset_id), params, timeout=300)
        resp.raise_for_status()
        batch = resp.json()["results"]
        rows += batch
        if len(batch) < PAGE:
            break
        offset += PAGE
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    log_manifest("enrollment", path.name, QUERY.format(id=dataset_id), modified, len(rows))
    print(f"enrollment: {len(rows):,} state-month rows")
    return path


def shock(period):
    n = qnum(period)
    return "; ".join(name for name, first, last in SHOCKS if qnum(first) <= n <= qnum(last))


def build(path=None):
    df = pd.read_csv(path or RAW / "enrollment" / "enrollment.csv", dtype=str, keep_default_na=False)
    df = df[df.final_report == "Y"].copy()
    df["enrollees"] = pd.to_numeric(df.total_medicaid_and_chip_enrollment, errors="coerce")
    month = df.groupby("reporting_period").enrollees.sum(min_count=1).dropna()
    by_q = pd.DataFrame({"enrollees": month.values,
                         "period": [qstr(int(m[:4]) * 4 + (int(m[4:]) - 1) // 3) for m in month.index]})
    q = by_q.groupby("period").agg(enrollees=("enrollees", "mean"), months=("enrollees", "size"))
    last = max(qnum(p) for p in q.index)
    out = pd.DataFrame({"period": [qstr(n) for n in range(qnum(FIRST_PERIOD), last + 1)]})
    out = out.merge(q.round().reset_index(), on="period", how="left")
    out["enrollees"] = out.enrollees.astype("Int64")
    out["months"] = out.months.fillna(0).astype(int)
    out["shock"] = out.period.map(shock)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download the enrollment dataset")
    args = ap.parse_args()
    out = build(pull(args.refresh))
    out.to_csv(PROCESSED / "medicaid_enrollment.csv", index=False)
    print(f"wrote {len(out)} quarters -> data/processed/medicaid_enrollment.csv")


if __name__ == "__main__":
    main()
