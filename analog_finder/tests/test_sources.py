"""The approved-source gate (step 10): offline, with a fake HTTP getter."""
import csv

import requests

import pytest

from analog_finder.research import sources
from analog_finder.research.sources import Gate, Source, SourceRefused

LIST = [
    Source("ORIG labels", 6, ("www.accessdata.fda.gov",), ("line_of_therapy", "dosing_frequency")),
    Source("SEC EDGAR", 8, ("www.sec.gov", "efts.sec.gov"), ("launch_date",)),
    Source("Press releases", 8, (), ("launch_date",)),
]
LABEL = "https://www.accessdata.fda.gov/drugsatfda_docs/label/2010/200603lbl.pdf"


class Resp:
    def __init__(self, status=200, content=b"%PDF-1.4 label", headers=None):
        self.status_code, self.content = status, content
        self.headers = {"Content-Type": "application/pdf", **(headers or {})}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeGet:
    """Returns a scripted response per URL and records each call."""

    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def __call__(self, url, headers=None, timeout=None, allow_redirects=True):
        assert allow_redirects is False  # the gate follows redirects itself
        self.calls.append((url, headers))
        return self.responses[url]


def gate(tmp_path, responses=None, **kw):
    get = FakeGet(responses or {})
    return Gate(LIST, raw_dir=tmp_path / "research", get=get, min_interval=0, **kw), get


def refused_log(tmp_path):
    with (tmp_path / "research" / "refused.csv").open() as f:
        return list(csv.DictReader(f))


# --- checking ---------------------------------------------------------------------------------------------

def test_listed_host_passes(tmp_path):
    g, _ = gate(tmp_path)
    assert g.check(LABEL).name == "ORIG labels"
    assert g.allowed("HTTPS://WWW.ACCESSDATA.FDA.GOV./x.pdf")  # case and trailing dot ignored
    assert g.allowed("https://www.accessdata.fda.gov:443/x.pdf")  # port ignored


@pytest.mark.parametrize("url", [
    "https://www.drugs.com/pro/latuda.html",            # unlisted site
    "https://dailymed.nlm.nih.gov/dailymed/x",          # current label, never the ORIG one
    "https://evil.accessdata.fda.gov/x.pdf",            # subdomain not listed itself
    "https://accessdata.fda.gov.evil.com/x.pdf",        # look-alike
    "ftp://www.accessdata.fda.gov/x.pdf",               # not http(s)
    "file:///etc/passwd",
    "https://user:pw@www.accessdata.fda.gov/x.pdf",     # credentials in the URL
    "not a url",
])
def test_unlisted_url_refused(tmp_path, url):
    g, _ = gate(tmp_path)
    assert not g.allowed(url)
    with pytest.raises(SourceRefused):
        g.check(url)


def test_field_narrows_the_gate(tmp_path):
    g, _ = gate(tmp_path)
    assert g.allowed(LABEL, "dosing_frequency")
    with pytest.raises(SourceRefused, match="not for launch_date"):
        g.check(LABEL, "launch_date")
    with pytest.raises(SourceRefused, match="not for dosing_frequency"):
        g.check("https://www.sec.gov/Archives/x.htm", "dosing_frequency")
    assert g.hosts_for("launch_date") == ["efts.sec.gov", "www.sec.gov"]


def test_filter_splits_and_logs_dropped(tmp_path):
    g, _ = gate(tmp_path)
    urls = [LABEL, "https://www.fiercepharma.com/latuda", "https://www.sec.gov/Archives/x.htm"]
    kept, dropped = g.filter(urls, "launch_date")
    assert kept == ["https://www.sec.gov/Archives/x.htm"]
    assert dropped == [LABEL, "https://www.fiercepharma.com/latuda"]
    log = refused_log(tmp_path)
    assert [r["url"] for r in log] == dropped and all(r["field"] == "launch_date" for r in log)
    assert log[0]["reason"].startswith("filtered:")


def test_repo_list_loads():
    names = {s.name for s in sources.load_sources()}
    assert "SEC EDGAR filings and full-text search" in names
    g = Gate(raw_dir="unused")
    assert g.allowed(LABEL, "line_of_therapy") and not g.allowed("https://www.drugs.com/x")
    # every host is a US government site, except company sources, which are tied to their own analogs and paths
    for s in g.sources:
        if not all(h.endswith(".gov") for h in s.hosts):
            assert s.analogs and s.paths and s.used_for == ("launch_date",), s.name
    lundbeck = "https://news.cision.com/h--lundbeck-a-s/r/solid-sales-performance-in-2015,c2808764"
    assert g.allowed(lundbeck, "launch_date", "rexulti_oral")
    assert not g.allowed(lundbeck, "launch_date", "latuda_oral")       # Lundbeck's site, not Sumitomo's drug
    assert not g.allowed(lundbeck, "launch_date")                      # analog must be named
    assert not g.allowed("https://news.cision.com/other-co/r/x", "launch_date", "rexulti_oral")  # other issuer
    assert not g.allowed(lundbeck, "dosing_frequency", "rexulti_oral")
    # line of therapy only from the ORIG label, never a trial registry (same label basis as the target)
    assert g.hosts_for("line_of_therapy") == ["www.accessdata.fda.gov"]
    assert not g.allowed("https://clinicaltrials.gov/api/v2/studies", "line_of_therapy")
    assert g.allowed("https://clinicaltrials.gov/api/v2/studies", "n_competitors_at_launch")


def test_company_source_limited_to_its_analog_and_path(tmp_path):
    company = Source("Acme releases", 8, ("news.acme.com",), ("launch_date",), ("alpha_oral",), ("/press/",))
    g = Gate(LIST + [company], raw_dir=tmp_path / "research", min_interval=0)
    ok = "https://news.acme.com/press/2015-launch"
    assert g.check(ok, "launch_date", "alpha_oral").name == "Acme releases"
    with pytest.raises(SourceRefused, match="only for other analogs"):
        g.check(ok, "launch_date", "beta_oral")
    with pytest.raises(SourceRefused, match="only under other paths"):
        g.check("https://news.acme.com/careers", "launch_date", "alpha_oral")
    assert g.hosts_for("launch_date") == ["efts.sec.gov", "www.sec.gov"]
    assert g.hosts_for("launch_date", "alpha_oral") == ["efts.sec.gov", "news.acme.com", "www.sec.gov"]
    kept, dropped = g.filter([ok, "https://www.sec.gov/x.htm"], "launch_date", "beta_oral")
    assert kept == ["https://www.sec.gov/x.htm"] and dropped == [ok]


def test_redirect_checked_against_the_analog(tmp_path):
    company = Source("Acme releases", 8, ("news.acme.com",), ("launch_date",), ("alpha_oral",), ("/press/",))
    sec = "https://www.sec.gov/Archives/x.htm"
    g, _ = gate(tmp_path, {sec: Resp(302, b"", {"Location": "https://news.acme.com/press/x"})},
                sec_user_agent="Team test@x.edu")
    g.sources.append(company)
    with pytest.raises(SourceRefused, match="only for other analogs"):
        g.fetch(sec, "launch_date", analog_id="beta_oral")


def test_used_for_typo_rejected(tmp_path):
    path = tmp_path / "approved_sources.yaml"
    path.write_text("sources:\n  - {name: Labels, row: 6, hosts: [www.accessdata.fda.gov], used_for: [dosing]}\n")
    with pytest.raises(ValueError, match="unknown used_for"):
        sources.load_sources(path)


# --- fetching ---------------------------------------------------------------------------------------------

def test_fetch_saves_unchanged_with_manifest_and_caches(tmp_path):
    g, get = gate(tmp_path, {LABEL: Resp(headers={"Last-Modified": "Tue, 01 Jun 2010"})})
    f = g.fetch(LABEL, "dosing_frequency")
    assert f.final_url == LABEL and f.redirects == () and f.content_type == "application/pdf"
    assert f.path.read_bytes() == b"%PDF-1.4 label" and f.path.suffix == ".pdf"
    assert f.path.parent == tmp_path / "research" / "www.accessdata.fda.gov"
    manifest = list(csv.DictReader((f.path.parent / "manifest.csv").open()))
    assert manifest[0]["url"] == LABEL and manifest[0]["last_modified"] == "Tue, 01 Jun 2010"
    assert g.fetch(LABEL).path == f.path and len(get.calls) == 1  # second fetch from the saved file


def test_dotted_file_names_dont_collide(tmp_path):
    """Two URLs whose file names have a dot in the stem keep separate files, and each is read back from cache."""
    a = "https://www.sec.gov/Archives/edgar/data/1/report.2016-q1.htm"
    b = "https://www.sec.gov/Archives/edgar/data/2/report.2016-q2.htm"
    html = {"Content-Type": "text/html"}
    g, get = gate(tmp_path, {a: Resp(content=b"q1", headers=html), b: Resp(content=b"q2", headers=html)},
                  sec_user_agent="test test@example.com")
    fa, fb = g.fetch(a, "launch_date"), g.fetch(b, "launch_date")
    assert fa.path != fb.path and fa.path.read_bytes() == b"q1" and fb.path.read_bytes() == b"q2"
    assert g.fetch(a).path == fa.path and g.fetch(b).path == fb.path and len(get.calls) == 2


def test_unlisted_url_never_requested(tmp_path):
    g, get = gate(tmp_path)
    with pytest.raises(SourceRefused):
        g.fetch("https://www.drugs.com/pro/latuda.html")
    assert get.calls == []
    assert refused_log(tmp_path)[0]["url"] == "https://www.drugs.com/pro/latuda.html"


def test_redirect_to_unlisted_host_refused(tmp_path):
    bad = "https://tracker.example.com/latuda.pdf"
    g, get = gate(tmp_path, {LABEL: Resp(302, b"", {"Location": bad})})
    with pytest.raises(SourceRefused, match="redirect"):
        g.fetch(LABEL)
    assert [u for u, _ in get.calls] == [LABEL]  # the unlisted page is never requested
    assert not (tmp_path / "research" / "www.accessdata.fda.gov").exists()  # nothing saved
    assert refused_log(tmp_path)[0]["url"] == bad


def test_redirect_to_listed_host_is_followed(tmp_path):
    moved = "https://www.accessdata.fda.gov/drugsatfda_docs/label/2010/200603s000lbl.pdf"
    g, get = gate(tmp_path, {LABEL: Resp(301, b"", {"Location": "/drugsatfda_docs/label/2010/200603s000lbl.pdf"}),
                             moved: Resp()})
    f = g.fetch(LABEL, "line_of_therapy")
    assert f.final_url == moved and f.redirects == (moved,)  # relative Location resolved, then checked


def test_redirect_checked_against_the_field(tmp_path):
    sec = "https://www.sec.gov/Archives/x.htm"
    g, _ = gate(tmp_path, {LABEL: Resp(302, b"", {"Location": sec})})
    with pytest.raises(SourceRefused, match="not for dosing_frequency"):
        g.fetch(LABEL, "dosing_frequency")


def test_redirect_loop_stops(tmp_path):
    a, b = LABEL, LABEL.replace("200603lbl", "other")
    g, _ = gate(tmp_path, {a: Resp(302, b"", {"Location": b}), b: Resp(302, b"", {"Location": a})})
    with pytest.raises(SourceRefused, match="more than 5 redirects"):
        g.fetch(a)


def test_http_upgraded_to_https(tmp_path):
    g, get = gate(tmp_path, {LABEL: Resp()})
    g.fetch(LABEL.replace("https://", "http://"))
    assert get.calls[0][0] == LABEL


def test_sec_needs_its_user_agent(tmp_path, monkeypatch):
    sec = "https://www.sec.gov/Archives/x.htm"
    monkeypatch.setattr(sources.common, "env", lambda name, default=None: None)
    g, get = gate(tmp_path, {sec: Resp(headers={"Content-Type": "text/html"})})
    with pytest.raises(SourceRefused, match="SEC_USER_AGENT"):
        g.fetch(sec)
    g, get = gate(tmp_path, {sec: Resp(headers={"Content-Type": "text/html"})}, sec_user_agent="Team test@x.edu")
    assert g.fetch(sec).path.suffix == ".html"
    assert get.calls[0][1]["User-Agent"] == "Team test@x.edu"


def test_retries_then_errors(tmp_path):
    g, get = gate(tmp_path, {LABEL: Resp(503)})
    with pytest.raises(RuntimeError, match="503"):
        g.fetch(LABEL)
    assert len(get.calls) == 5


def test_timeout_is_retried(tmp_path):
    calls = []

    def flaky(url, headers=None, timeout=None, allow_redirects=False):
        calls.append(url)
        if len(calls) < 3:
            raise requests.ReadTimeout("slow")
        return Resp()

    g = Gate(LIST, raw_dir=tmp_path / "research", get=flaky, min_interval=0)
    assert g.fetch(LABEL).path.exists() and len(calls) == 3
