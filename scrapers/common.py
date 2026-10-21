"""Shared helpers: cached + throttled HTTP GET, pull manifest, NDC formatting."""
import csv
import hashlib
import json
import os
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REFERENCE = ROOT / "data" / "reference"

USER_AGENT = "pharma-phriends-research/0.1 (Columbia student project)"
MIN_INTERVAL = 0.5  # seconds between live requests
_last_call = 0.0


def _fetch(url, params, source):
    """Throttled GET with retries on 429/5xx. Returns the Response (404 left to the caller)."""
    global _last_call
    wait = MIN_INTERVAL - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    for attempt in range(4):
        resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=120)
        _last_call = time.time()
        if resp.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** attempt * 2)
            continue
        return resp
    resp.raise_for_status()


def _cache_path(url, params, source, suffix):
    key = hashlib.sha1(json.dumps([url, params], sort_keys=True).encode()).hexdigest()[:16]
    return RAW / source / f"{key}{suffix}"


def get_json(url, params=None, source="misc", refresh=False):
    """GET a JSON endpoint, caching the response under data/raw/<source>/.

    Re-runs read from the cache, so we only hit an API once per unique query.
    """
    cache = _cache_path(url, params, source, ".json")
    if cache.exists() and not refresh:
        return json.loads(cache.read_text())

    resp = _fetch(url, params, source)
    if resp.status_code == 404 and source == "openfda":
        data = {"results": []}  # openFDA returns 404 for "no matches"
    else:
        resp.raise_for_status()
        data = resp.json()

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data))
    log_pull(source, url, params, data)
    return data


def get_text(url, params=None, source="misc", suffix=".txt", refresh=False):
    """Like get_json, for non-JSON responses (e.g. DailyMed SPL XML)."""
    cache = _cache_path(url, params, source, suffix)
    if cache.exists() and not refresh:
        return cache.read_text()
    resp = _fetch(url, params, source)
    resp.raise_for_status()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(resp.text)
    log_pull(source, url, params, [resp.text])
    return resp.text


def log_pull(source, url, params, data):
    """Append one row per live API call to data/raw/<source>/manifest.csv."""
    manifest = RAW / source / "manifest.csv"
    new = not manifest.exists()
    n = len(data.get("results", data)) if isinstance(data, dict) else len(data)
    with manifest.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["pulled_at", "url", "params", "n_results"])
        w.writerow([date.today().isoformat(), url, json.dumps(params), n])


def ndc9_from_product_ndc(product_ndc):
    """FDA product NDC ('0074-1050', '59572-631') -> SDUD-style 9-digit labeler+product ('000741050').

    FDA NDCs come in 4-4, 5-3 or 5-4 segments; SDUD pads labeler to 5 and product to 4.
    """
    labeler, product = product_ndc.split("-")[:2]
    return labeler.zfill(5) + product.zfill(4)


def env(name, default=None):
    """Read a setting from the environment or a local .env file."""
    if name in os.environ:
        return os.environ[name]
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip()
    return default


def select_brands(master, brands):
    """Filter drug_master rows to --brands (comma-separated brand_keys); all rows if none given."""
    if not brands:
        return master
    keys = [b.strip().lower() for b in brands.split(",")]
    missing = set(keys) - set(master.brand_key)
    if missing:
        raise SystemExit(f"unknown brand_key (add it to seed_drugs.csv and build drug_master first): {', '.join(sorted(missing))}")
    return master[master.brand_key.isin(keys)]


def write_brand_rows(path, df, brand_keys=None):
    """Write df to path. With brand_keys, replace only those brands' rows and keep everyone else's,
    so adding one analog doesn't mean re-pulling (and re-caching) every other brand."""
    import pandas as pd

    if brand_keys is not None and path.exists():
        old = pd.read_csv(path, dtype=str)
        df = pd.concat([old[~old.brand_key.isin(brand_keys)], df.astype(str)], ignore_index=True)
        df = df.replace("nan", "")
    df.to_csv(path, index=False)
