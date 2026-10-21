"""Shared helpers: paths, cached + throttled HTTP, bulk downloads with a manifest, NDC formatting."""
import csv
import hashlib
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REFERENCE = ROOT / "data" / "reference"

USER_AGENT = "pharma-phriends-research/0.1 (Columbia student project)"
MIN_INTERVAL = 0.5  # seconds between live requests (~2 req/s)
_last_call = 0.0

MANIFEST_COLS = ["pulled_at", "file", "url", "last_modified", "sha256", "bytes", "rows"]


def _fetch(url, params=None, stream=False, timeout=120):
    """Throttled GET with retries on 429/5xx. Returns the Response (404 left to the caller)."""
    global _last_call
    wait = MIN_INTERVAL - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    for attempt in range(5):
        try:
            resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, stream=stream, timeout=timeout)
        except requests.ConnectionError:
            time.sleep(2 ** attempt * 2)
            continue
        _last_call = time.time()
        if resp.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** attempt * 2)
            continue
        return resp
    resp.raise_for_status()


def _cache_path(url, params, source, suffix):
    key = hashlib.sha1(json.dumps([url, params], sort_keys=True).encode()).hexdigest()[:16]
    return RAW / source / "api" / f"{key}{suffix}"


def get_json(url, params=None, source="misc", refresh=False):
    """GET a JSON endpoint, caching the response under data/raw/<source>/api/.

    Re-runs read from the cache, so we only hit an API once per unique query.
    """
    cache = _cache_path(url, params, source, ".json")
    if cache.exists() and not refresh:
        return json.loads(cache.read_text())
    resp = _fetch(url, params)
    resp.raise_for_status()
    data = resp.json()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data))
    return data


def download(url, source, name, refresh=False):
    """Download a bulk file to data/raw/<source>/<name> (unchanged) and record it in the manifest."""
    path = RAW / source / name
    if path.exists() and not refresh:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {source}/{name} ...")
    with _fetch(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        last_modified = r.headers.get("Last-Modified", "")
        with path.open("wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    log_manifest(source, name, url, last_modified)
    return path


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def log_manifest(source, name, url, last_modified="", rows=""):
    """Append one row per downloaded file to data/raw/<source>/manifest.csv (how stale files are caught)."""
    path = RAW / source / name
    manifest = RAW / source / "manifest.csv"
    new = not manifest.exists()
    with manifest.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(MANIFEST_COLS)
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), name, url, last_modified,
                    sha256(path), path.stat().st_size, rows])


def ndc9(product_ndc):
    """FDA product NDC ('0074-1050', '59572-631') -> SDUD-style 9-digit labeler+product ('000741050').

    FDA NDCs come in 4-4, 5-3 or 5-4 segments; SDUD pads labeler to 5 and product to 4.
    Malformed values (one row in the excluded file has no dash) return "".
    """
    if "-" not in product_ndc:
        return ""
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


def today():
    return date.today().isoformat()
