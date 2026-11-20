"""The approved-source gate: every Label Research Agent fetch goes through here, and anything not on the list is refused.

The list is analog_finder/config/approved_sources.yaml (docs/data_sources.md). Hosts match exactly (a subdomain must
be listed itself); with a field, the host must belong to a source used for that field. Redirects are followed by
hand and each hop is re-checked, so an approved URL can't hand the agent an unlisted page. Refused and filtered-out
URLs are logged to data/raw/research/refused.csv.

Spec: analog_finder/docs/components/sources_queue.md
"""
import csv
import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import requests
import yaml

from analog_finder.io import CONFIG_DIR
from pipeline import common
from pipeline.build import EVIDENCE_FIELDS

MAX_REDIRECTS = 5
# What a source may be used for: the evidence fields plus the flags sources 9-10 supply. A typo in used_for would
# silently make a host unusable, so load_sources rejects anything else.
KNOWN_USES = set(EVIDENCE_FIELDS) | {"first_in_class", "rems"}
SEC_HOSTS = {"www.sec.gov", "efts.sec.gov", "sec.gov", "data.sec.gov"}
REFUSED_COLUMNS = ["at", "url", "field", "reason"]
_EXTENSIONS = {"application/pdf": ".pdf", "text/html": ".html", "application/json": ".json", "text/plain": ".txt",
               "application/xml": ".xml", "text/xml": ".xml"}


class SourceRefused(ValueError):
    """The URL (or a redirect from it) isn't on the approved-source list, for this field if one was given."""


@dataclass(frozen=True)
class Source:
    name: str
    row: int | None
    hosts: tuple
    used_for: tuple
    analogs: tuple = ()  # non-empty: approved only for these analogs (a company's site, for its own drug)
    paths: tuple = ()    # non-empty: only URLs whose path starts with one of these (the company's part of a site)


@dataclass(frozen=True)
class Fetched:
    url: str           # what was asked for
    final_url: str     # after redirects (each one checked)
    path: Path         # the saved file, unchanged
    content_type: str
    redirects: tuple   # the URLs passed through, in order


def load_sources(path=None):
    """approved_sources.yaml as a list of Source."""
    path = Path(path or CONFIG_DIR / "approved_sources.yaml")
    data = yaml.safe_load(path.read_text()) or {}
    out = []
    for s in data.get("sources") or []:
        bad = sorted(set(s.get("used_for") or []) - KNOWN_USES)
        if bad:
            raise ValueError(f"{path}: source '{s.get('name')}' has unknown used_for {bad} (known: {sorted(KNOWN_USES)})")
        out.append(Source(name=str(s["name"]), row=s.get("row"),
                          hosts=tuple(_host(h) for h in (s.get("hosts") or [])),
                          used_for=tuple(s.get("used_for") or []),
                          analogs=tuple(s.get("analogs") or []), paths=tuple(s.get("paths") or [])))
    return out


def _host(host):
    return str(host).strip().lower().rstrip(".")


def _parse(url):
    """(scheme, host) of an absolute http(s) URL, or raise SourceRefused."""
    parts = urlsplit(str(url).strip())
    if parts.scheme.lower() not in ("http", "https"):
        raise SourceRefused(f"not an http(s) URL: {url}")
    if parts.username or parts.password:
        raise SourceRefused(f"URL carries a username or password: {url}")
    host = _host(parts.hostname or "")
    if not host:
        raise SourceRefused(f"no host in URL: {url}")
    return parts.scheme.lower(), host


def _https(url):
    parts = urlsplit(str(url).strip())
    return urlunsplit(("https",) + tuple(parts)[1:]) if parts.scheme.lower() == "http" else str(url).strip()


class Gate:
    """Checks URLs against the approved sources and fetches only those that pass.

    sources: list of Source (default: approved_sources.yaml). raw_dir: where fetched files and the refused log go
    (default data/raw/research). get: a requests.get-like function, for tests (called with allow_redirects=False).
    """

    def __init__(self, sources=None, raw_dir=None, get=None, user_agent=None, sec_user_agent=None,
                 min_interval=common.MIN_INTERVAL):
        self.sources = list(sources if sources is not None else load_sources())
        self.raw_dir = Path(raw_dir or common.RAW / "research")
        self._get = get or requests.get
        self.user_agent = user_agent or common.USER_AGENT
        self._sec_user_agent = sec_user_agent
        self.min_interval = min_interval
        self._last = 0.0

    # --- checking -----------------------------------------------------------------------------------------

    def check(self, url, field=None, analog_id=None):
        """The Source that approves this URL (for this field and analog, if given). Raises SourceRefused.

        A source limited to some analogs (a company's site) passes only when analog_id is one of them, and a source
        limited to some paths only for URLs under one of them."""
        _, host = _parse(url)
        path = urlsplit(str(url).strip()).path or "/"
        # "." / ".." segments (also percent-encoded) are refused, not resolved: the request library resolves them,
        # so /h--lundbeck-a-s/../h--other/ would pass a path rule and then fetch another company's page
        if any(seg in (".", "..") for seg in unquote(path).split("/")):
            raise SourceRefused(f"URL path has a '.' or '..' segment ({url})")
        matches = [s for s in self.sources if host in s.hosts]
        if not matches:
            raise SourceRefused(f"host {host} is not on the approved-source list ({url})")
        matches = [s for s in matches if not s.paths or any(path.startswith(p) for p in s.paths)]
        if not matches:
            raise SourceRefused(f"host {host} is approved only under other paths ({url})")
        if field is not None:
            for_field = [s for s in matches if field in s.used_for]
            if not for_field:
                names = "; ".join(s.name for s in matches)
                raise SourceRefused(f"host {host} is approved ({names}) but not for {field} ({url})")
            matches = for_field
        for_analog = [s for s in matches if not s.analogs or analog_id in s.analogs]
        if not for_analog:
            names = "; ".join(f"{s.name}: {', '.join(s.analogs)}" for s in matches)
            raise SourceRefused(f"host {host} is approved only for other analogs ({names}), not "
                                f"{analog_id or 'an unnamed analog'} ({url})")
        return for_analog[0]

    def allowed(self, url, field=None, analog_id=None):
        try:
            self.check(url, field, analog_id)
            return True
        except SourceRefused:
            return False

    def filter(self, urls, field=None, analog_id=None):
        """(kept, dropped) for a list of URLs (e.g. web-search results); dropped ones are logged."""
        kept, dropped = [], []
        for u in urls:
            try:
                self.check(u, field, analog_id)
                kept.append(u)
            except SourceRefused as e:
                dropped.append(u)
                self._log_refused(u, field, f"filtered: {e}")
        return kept, dropped

    def hosts_for(self, field, analog_id=None):
        """Every approved host for a field (sorted); with analog_id, including that analog's company sites."""
        return sorted({h for s in self.sources if field in s.used_for and (not s.analogs or analog_id in s.analogs)
                       for h in s.hosts})

    # --- fetching -----------------------------------------------------------------------------------------

    def fetch(self, url, field=None, *, refresh=False, analog_id=None):
        """Fetch an approved URL, following redirects only to approved URLs. Returns Fetched; raises SourceRefused.

        The response is saved unchanged under raw_dir/<host>/ with a manifest row, and read from there next time."""
        try:
            self.check(url, field, analog_id)
        except SourceRefused as e:
            self._log_refused(url, field, str(e))
            raise
        start = _https(url)
        path = self._path(start)
        cached = self._cached(path)
        if cached is not None and not refresh:
            return Fetched(url, start, cached, _content_type_of(cached), ())

        current, hops = start, []
        for _ in range(MAX_REDIRECTS + 1):
            resp = self._request(current)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location", "")
                nxt = _https(urljoin(current, location)) if location else ""
                try:
                    if not nxt:
                        raise SourceRefused(f"redirect from {current} has no Location")
                    self.check(nxt, field, analog_id)
                except SourceRefused as e:
                    self._log_refused(nxt or current, field, f"redirect from {url}: {e}")
                    raise SourceRefused(f"redirect from {url} refused: {e}") from None
                hops.append(nxt)
                current = nxt
                continue
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            path = path.with_suffix(_EXTENSIONS.get(content_type, ".bin"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(resp.content)
            self._manifest(path, url, current, resp.headers.get("Last-Modified", ""))
            return Fetched(url, current, path, content_type, tuple(hops))
        self._log_refused(url, field, f"more than {MAX_REDIRECTS} redirects")
        raise SourceRefused(f"more than {MAX_REDIRECTS} redirects from {url}")

    def _request(self, url):
        _, host = _parse(url)
        headers = {"User-Agent": self._agent_for(host)}
        for attempt in range(5):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self._get(url, headers=headers, timeout=120, allow_redirects=False)
            except (requests.ConnectionError, requests.Timeout):
                time.sleep(2 ** attempt * 2 * (self.min_interval > 0))
                continue
            self._last = time.time()
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(2 ** attempt * 2 * (self.min_interval > 0))
                continue
            return resp
        raise requests.ConnectionError(f"could not reach {url}")

    def _agent_for(self, host):
        if host in SEC_HOSTS:
            agent = self._sec_user_agent or common.env("SEC_USER_AGENT")
            if not agent:
                raise SourceRefused("SEC requires a User-Agent with contact info: set SEC_USER_AGENT in .env "
                                    "(see .env.example)")
            return agent
        return self.user_agent

    # --- files --------------------------------------------------------------------------------------------

    def _path(self, url):
        """raw_dir/<host>/<name>, the suffix set once the content type is known."""
        _, host = _parse(url)
        last = urlsplit(url).path.rsplit("/", 1)[-1]
        stem = Path(last).stem if last else "index"
        key = hashlib.sha1(url.encode()).hexdigest()[:10]
        # no "." in the name: fetch() sets the extension with with_suffix, which would cut a dotted name (and its
        # key) short, e.g. report.2016-q1 -> report.html for every such URL
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)[:60] or "page"
        return self.raw_dir / host / f"{safe}-{key}"

    def _cached(self, path):
        if not path.parent.exists():
            return None
        hits = sorted(path.parent.glob(path.name + ".*"))
        return hits[0] if hits else None

    def _manifest(self, path, url, final_url, last_modified):
        manifest = path.parent / "manifest.csv"
        new = not manifest.exists()
        with manifest.open("a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(common.MANIFEST_COLS + ["final_url"])
            w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), path.name, url, last_modified,
                        common.sha256(path), path.stat().st_size, "", final_url])

    def _log_refused(self, url, field, reason):
        log = self.raw_dir / "refused.csv"
        log.parent.mkdir(parents=True, exist_ok=True)
        new = not log.exists()
        with log.open("a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(REFUSED_COLUMNS)
            w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), url, field or "", reason])


def _content_type_of(path):
    for ct, ext in _EXTENSIONS.items():
        if path.suffix == ext:
            return ct
    return ""


def default_gate(**kwargs):
    """A Gate on the repo's approved_sources.yaml and data/raw/research."""
    return Gate(**kwargs)
