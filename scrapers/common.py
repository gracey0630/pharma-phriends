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


def get_json(url, params=None, source="misc", refresh=False):
    """GET a JSON endpoint, caching the response under data/raw/<source>/.

    Re-runs read from the cache, so we only hit an API once per unique query.
    """
    key = hashlib.sha1(json.dumps([url, params], sort_keys=True).encode()).hexdigest()[:16]
    cache = RAW / source / f"{key}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text())

    global _last_call
    wait = MIN_INTERVAL - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    for attempt in range(4):
        resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=120)
        _last_call = time.time()
        if resp.status_code == 404 and source == "openfda":
            data = {"results": []}  # openFDA returns 404 for "no matches"
            break
        if resp.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** attempt * 2)
            continue
        resp.raise_for_status()
        data = resp.json()
        break
    else:
        resp.raise_for_status()

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data))
    log_pull(source, url, params, data)
    return data


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
