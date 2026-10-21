"""Medicaid State Drug Utilization Data (SDUD): national quarterly TRx per analog.

Pull: every national row (state == "XX") for each whole year 2010+, from the data.medicaid.gov
datastore API, saved unchanged to data/raw/sdud/national_<year>.csv. National rows only keeps the
download to ~300k rows/year instead of the ~8 GB state-level CSVs (decision 2026-10-21).

Build rules (docs/data_sources.md):
  - sum FFSU + MCOU
  - join on 9-digit NDC (labeler + product), never on the truncated product_name
  - suppressed values stay blank, never 0

Output: data/processed/sdud_quarterly.csv in the shared long format
        analog_id, source, payer, period, metric, value, pulled_at

Usage: python -m pipeline.sdud [--pull-only] [--refresh] [--start-year 2010]
"""
import argparse
import csv
from datetime import date

import pandas as pd

from pipeline.common import PROCESSED, RAW, _fetch, get_json, log_manifest, today

CATALOG = "https://data.medicaid.gov/api/1/search"
QUERY = "https://data.medicaid.gov/api/1/datastore/query/{id}/0"
PAGE = 8000  # API maximum
FIRST_YEAR = 2010  # managed-care (MCOU) records start in 2010
SDUD = RAW / "sdud"
COLS = ["utilization_type", "state", "ndc", "labeler_code", "product_code", "package_size", "year", "quarter",
        "suppression_used", "product_name", "units_reimbursed", "number_of_prescriptions", "total_amount_reimbursed"]


def datasets():
    """Map year -> (dataset id, last modified), looked up from the catalog (ids change when CMS republishes)."""
    data = get_json(CATALOG, {"fulltext": "State Drug Utilization Data", "page-size": 100}, source="sdud", refresh=True)
    out = {}
    for v in data["results"].values():
        title = v.get("title", "")
        if title.startswith("State Drug Utilization Data ") and title[-4:].isdigit():
            out[int(title[-4:])] = (v["identifier"], v.get("modified", ""))
    return out


def _query(dataset_id, offset, count=False):
    params = {
        "limit": PAGE, "offset": offset, "count": str(count).lower(), "results": "true",
        "conditions[0][property]": "state", "conditions[0][operator]": "=", "conditions[0][value]": "XX",
        # stable order so offset paging never skips or repeats rows
        "sorts[0][property]": "ndc", "sorts[0][order]": "asc",
        "sorts[1][property]": "quarter", "sorts[1][order]": "asc",
        "sorts[2][property]": "utilization_type", "sorts[2][order]": "asc",
    }
    for i, c in enumerate(COLS):
        params[f"properties[{i}]"] = c
    resp = _fetch(QUERY.format(id=dataset_id), params, timeout=300)
    resp.raise_for_status()
    return resp.json()


def pull_year(year, dataset_id, modified, refresh=False):
    """Save every national row of one SDUD year to data/raw/sdud/national_<year>.csv."""
    path = SDUD / f"national_{year}.csv"
    if path.exists() and not refresh:
        return path
    SDUD.mkdir(parents=True, exist_ok=True)
    first = _query(dataset_id, 0, count=True)
    total = int(first["count"])
    tmp = path.with_suffix(".part")
    n = 0
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        offset, batch = 0, first["results"]
        while True:
            w.writerows(batch)
            n += len(batch)
            if len(batch) < PAGE:
                break
            offset += PAGE
            batch = _query(dataset_id, offset)["results"]
    if n != total:
        raise RuntimeError(f"SDUD {year}: got {n} rows, API count says {total}")
    tmp.rename(path)
    log_manifest("sdud", path.name, QUERY.format(id=dataset_id) + "?state=XX", modified, n)
    print(f"SDUD {year}: {n:,} national rows")
    return path


def pull(start_year=FIRST_YEAR, refresh=False):
    ds = datasets()
    for year in sorted(y for y in ds if y >= start_year):
        pull_year(year, *ds[year], refresh=refresh)


def load_national(labelers=None):
    """All pulled national rows, with ndc9 = 5-digit labeler + 4-digit product.
    labelers: optional set of 5-digit labeler codes to keep (keeps memory down; ~5M rows in total)."""
    frames = []
    for p in sorted(SDUD.glob("national_*.csv")):
        df = pd.read_csv(p, dtype=str, keep_default_na=False)
        df["labeler_code"] = df.labeler_code.str.zfill(5)
        frames.append(df[df.labeler_code.isin(labelers)] if labelers is not None else df)
    df = pd.concat(frames, ignore_index=True)
    df["ndc9"] = df.labeler_code.str.zfill(5) + df.product_code.str.zfill(4)
    return df


def build(ndc_map, national=None):
    """Quarterly trx / units / reimbursed_usd / suppressed_rows per analog, long format."""
    df = national if national is not None else load_national()
    df = df.merge(ndc_map[["analog_id", "ndc9"]], on="ndc9")
    num = ["number_of_prescriptions", "units_reimbursed", "total_amount_reimbursed"]
    df[num] = df[num].apply(pd.to_numeric, errors="coerce")
    df["period"] = df.year + "Q" + df.quarter
    df["suppressed"] = df.suppression_used.str.lower() == "true"
    # min_count=1: a quarter where every row is suppressed stays NaN instead of becoming 0
    g = df.groupby(["analog_id", "period"])
    q = g[num].sum(min_count=1)
    q["suppressed_rows"] = g.suppressed.sum()
    q = q.rename(columns={"number_of_prescriptions": "trx", "units_reimbursed": "units",
                          "total_amount_reimbursed": "reimbursed_usd"})
    out = q.reset_index().melt(["analog_id", "period"], var_name="metric", value_name="value")
    out.insert(1, "source", "sdud")
    out.insert(2, "payer", "medicaid")
    out["pulled_at"] = today()
    return out.sort_values(["analog_id", "period", "metric"], ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull-only", action="store_true", help="download the national rows and stop")
    ap.add_argument("--refresh", action="store_true", help="re-download years already pulled")
    ap.add_argument("--start-year", type=int, default=FIRST_YEAR)
    args = ap.parse_args()
    pull(args.start_year, args.refresh)
    if args.pull_only:
        return
    ndc_map = pd.read_csv(PROCESSED / "ndc_map.csv", dtype=str)
    out = build(ndc_map, load_national(set(ndc_map.ndc9.str[:5])))
    out.to_csv(PROCESSED / "sdud_quarterly.csv", index=False)
    print(f"wrote {len(out):,} rows -> data/processed/sdud_quarterly.csv")


if __name__ == "__main__":
    main()
