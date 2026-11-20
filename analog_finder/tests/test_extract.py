"""Step 11: extraction and quote checks. Offline: a fake gate serves saved pages, the model is FakeLLM or a scripted
stand-in, and Drugs@FDA is a small stub."""
import json

import pandas as pd
import pytest

from analog_finder.llm import FakeLLM
from analog_finder.research import __main__ as cli
from analog_finder.research import extract, verify
from analog_finder.research.sources import Fetched, SourceRefused

LABEL_TEXT = """HIGHLIGHTS OF PRESCRIBING INFORMATION
----INDICATIONS AND USAGE----
ZEPRA is an atypical antipsychotic agent indicated for the treatment of patients with sc hizophrenia (1).
----DOSAGE AND ADMINISTRATION----
The recommended starting dose is 40 mg once daily. Initial dose titration is not required (2.1). ZEPRA should be
taken with food (at least 350 calories). Take once-
daily with an antipsy-
chotic-naive start."""

ANALOG = extract.Analog("zepra_oral", "Zepra", "NDA200001", "ZEPRA is indicated for the treatment of schizophrenia.",
                        "2010-10-28", "2011-01-01")


class FakeGate:
    """Serves saved text per URL; anything else is refused, like an unlisted site."""

    def __init__(self, tmp_path, pages):
        self.pages, self.tmp, self.calls = pages, tmp_path, []

    def fetch(self, url, field=None, *, refresh=False, analog_id=None):
        self.calls.append((url, field, analog_id))
        if url not in self.pages:
            raise SourceRefused(f"not on the list: {url}")
        name, body = self.pages[url]
        path = self.tmp / name
        path.write_text(body)
        return Fetched(url, url, path, "", ())


class ScriptedLLM:
    """Returns the answers in order (one list per schema title), recording the prompts."""
    name = "scripted"

    def __init__(self, answers):
        self.answers, self.prompts = {k: list(v) for k, v in answers.items()}, []

    def generate_json(self, prompt, schema):
        self.prompts.append((schema["title"], prompt))
        return self.answers[schema["title"]].pop(0)


@pytest.fixture
def label_gate(tmp_path, monkeypatch):
    url = "https://www.accessdata.fda.gov/drugsatfda_docs/label/2010/200001s000lbl.pdf"
    monkeypatch.setattr(extract, "orig_label_url", lambda appl: url if appl == "200001" else "")
    return FakeGate(tmp_path, {url: ("label.txt", LABEL_TEXT)}), url


GOOD_LABEL = {"line_of_therapy": "any",
              "line_of_therapy_quote": "indicated for the treatment of patients with schizophrenia",
              "dosing_frequency": "once daily",
              "dosing_frequency_quote": "The recommended starting dose is 40 mg once daily."}


# --- quote check --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("quote, status", [
    ("indicated for the treatment of patients with schizophrenia", "verbatim"),     # PDF split 'sc hizophrenia'
    ("The recommended starting dose is 40 mg once daily.", "verbatim"),
    ("the RECOMMENDED starting dose, is 40 mg once daily", "verbatim"),             # case and punctuation
    ("Take once-daily with an antipsychotic-naive start", "verbatim"),              # hyphens at line breaks
    ("The recommended starting dose is 80 mg once daily.", "partial"),
    ("indicated for bipolar depression", "partial"),
    ("", "partial"),
])
def test_quote_check(quote, status):
    assert verify.quote_check(quote, LABEL_TEXT)[0] == status


def test_quote_check_says_how_far_it_matched():
    assert verify.quote_check("The recommended starting dose is 80 mg", LABEL_TEXT) == \
        ("partial", "first 5 of 7 words match the source")


def test_html_text():
    html = "<html><style>x{}</style><body><p>LATUDA&nbsp;launched in <b>February 2011</b>.</p><div>Next</div></body>"
    assert verify.html_text(html) == "LATUDA launched in February 2011.\nNext"


# --- label fields -------------------------------------------------------------------------------------------

def test_label_read_writes_both_fields_unapproved(label_gate):
    gate, url = label_gate
    res = extract.read_label(ANALOG, gate, FakeLLM({"label_read": GOOD_LABEL}))
    assert [r["field"] for r in res.rows] == ["line_of_therapy", "dosing_frequency"] and not res.skipped
    lot, dose = res.rows
    assert (lot["value"], lot["quote_check"], lot["source_url"], lot["approved"]) == ("any", "verbatim", url, "false")
    assert (dose["value"], dose["quote_check"], dose["notes"]) == ("once daily", "verbatim", "")
    assert lot["extracted_by"] == "agent:fake" and lot["source_type"] == "ORIG label"
    assert gate.calls == [(url, "line_of_therapy", "zepra_oral")]  # fetched through the gate, once


def test_label_read_retries_once_then_keeps_a_partial_quote(label_gate):
    gate, _ = label_gate
    bad = {**GOOD_LABEL, "dosing_frequency_quote": "Take 40 mg every day."}
    llm = ScriptedLLM({"label_read": [bad, bad]})
    res = extract.read_label(ANALOG, gate, llm)
    assert len(llm.prompts) == 2 and "not found word for word" in llm.prompts[1][1]
    dose = res.rows[1]
    assert dose["quote_check"] == "partial" and "words match the source" in dose["notes"]


def test_label_read_retry_can_fix_the_quote(label_gate):
    gate, _ = label_gate
    llm = ScriptedLLM({"label_read": [{**GOOD_LABEL, "dosing_frequency_quote": "40 mg a day"}, GOOD_LABEL]})
    assert all(r["quote_check"] == "verbatim" for r in extract.read_label(ANALOG, gate, llm).rows)


def test_label_read_notes_the_checks(label_gate):
    gate, _ = label_gate
    odd = {**GOOD_LABEL, "line_of_therapy": "first", "line_of_therapy_quote": "Initial dose titration is not required",
           "dosing_frequency": "as directed"}
    lot, dose = extract.read_label(ANALOG, gate, FakeLLM({"label_read": odd})).rows
    assert lot["notes"] == "" or "read as" not in lot["notes"]  # "initial" reads as first: agrees
    assert dose["notes"] == "frequency not machine-readable"
    later = {**GOOD_LABEL, "line_of_therapy": "first",
             "line_of_therapy_quote": "ZEPRA should be taken with food (at least 350 calories). Take once-"}
    assert extract.read_label(ANALOG, gate, FakeLLM({"label_read": later})).rows[0]["notes"] == ""
    disagree = {**GOOD_LABEL, "line_of_therapy": "later", "line_of_therapy_quote": "Initial dose titration"}
    assert extract.read_label(ANALOG, gate, FakeLLM({"label_read": disagree})).rows[0]["notes"] == \
        "keywords in the quote read as first"


def test_label_read_only_the_fields_asked(label_gate):
    gate, _ = label_gate
    res = extract.read_label(ANALOG, gate, FakeLLM({"label_read": GOOD_LABEL}), fields=["dosing_frequency"])
    assert [r["field"] for r in res.rows] == ["dosing_frequency"]


def test_no_orig_label_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "orig_label_url", lambda appl: "")
    llm = FakeLLM()
    res = extract.read_label(ANALOG, FakeGate(tmp_path, {}), llm)
    assert res.rows == [] and {s[1] for s in res.skipped} == {"no ORIG label in Drugs@FDA"} and llm.calls == []


def test_refused_label_url_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "orig_label_url", lambda appl: "https://www.drugs.com/pro/zepra.html")
    res = extract.read_label(ANALOG, FakeGate(tmp_path, {}), FakeLLM())
    assert res.rows == [] and res.skipped[0][1] == "label not fetched"


# --- launch date --------------------------------------------------------------------------------------------

FILING = "https://www.sec.gov/Archives/edgar/data/1/000000000011000001/ex991.htm"
FILING_HTML = "<html><body><p>Zepra was launched in the US in February 2011 and is now promoted by our sales force." \
              "</p></body></html>"
FORECAST_HTML = "<p>We expect Zepra to be commercially available in the first quarter of 2011.</p>"


def _search_json():
    return json.dumps({"hits": {"hits": [
        {"_id": "0000000000-11-000001:ex991.htm", "_source": {"ciks": ["0000000001"], "file_date": "2011-03-01"}}]}})


def test_edgar_urls_from_the_search(tmp_path):
    search = (f"{extract.EDGAR_SEARCH}?q=%22Zepra%22&forms=8-K,10-Q,10-K&dateRange=custom"
              f"&startdt=2010-10-28&enddt=2012-01-28")
    gate = FakeGate(tmp_path, {search: ("search.json", _search_json())})
    assert extract.edgar_urls(ANALOG, gate) == [FILING]


def test_launch_date_written_with_its_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "edgar_urls", lambda a, g: [FILING])
    gate = FakeGate(tmp_path, {FILING: ("f.html", FILING_HTML)})
    llm = FakeLLM({"launch_date": {"status": "launched", "date": "2011-02", "passage": 1,
                                   "quote": "Zepra was launched in the US in February 2011"}})
    (row,) = extract.read_launch_date(ANALOG, gate, llm).rows
    assert (row["value"], row["quote_check"], row["source_url"], row["source_type"]) == \
        ("2011-02", "verbatim", FILING, "SEC filing")
    assert "Zepra was launched" in llm.calls[0][1]  # the passage was sent


def test_forecast_is_never_a_launch_date(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "edgar_urls", lambda a, g: [FILING])
    gate = FakeGate(tmp_path, {FILING: ("f.html", FORECAST_HTML)})
    llm = FakeLLM({"launch_date": {"status": "forecast", "date": "2011-01", "passage": 1,
                                   "quote": "We expect Zepra to be commercially available"}})
    res = extract.read_launch_date(ANALOG, gate, llm)
    assert res.rows == [] and res.skipped[0][1] == "only a forecast found (not written)"


def test_launch_date_from_a_named_page(tmp_path):
    page = "https://news.example.com/press/zepra"
    gate = FakeGate(tmp_path, {page: ("p.html", FILING_HTML)})
    llm = FakeLLM({"launch_date": {"status": "launched", "date": "2011-02", "passage": 1,
                                   "quote": "Zepra was launched in the US in February 2011"}})
    (row,) = extract.read_launch_date(ANALOG, gate, llm, source_url=page).rows
    assert row["source_type"] == "company release" and gate.calls[0] == (page, "launch_date", "zepra_oral")


def test_launch_date_bad_answers_write_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "edgar_urls", lambda a, g: [FILING])
    gate = FakeGate(tmp_path, {FILING: ("f.html", FILING_HTML)})
    for answer in [{"status": "launched", "date": "early 2011", "passage": 1, "quote": "x"},   # not a date
                   {"status": "launched", "date": "2011-02", "passage": 9, "quote": "x"},      # no such passage
                   {"status": "none", "date": "", "passage": 0, "quote": ""}]:
        assert extract.read_launch_date(ANALOG, gate, FakeLLM({"launch_date": answer})).rows == []
    no_mention = FakeGate(tmp_path, {FILING: ("g.html", "<p>Quarterly results.</p>")})
    res = extract.read_launch_date(ANALOG, no_mention, FakeLLM())
    assert res.skipped[0][1] == "no passage mentions a launch"


# --- competitors --------------------------------------------------------------------------------------------

class StubFDA:
    APPROVALS = {"OLDBRAND": ("000100", "1999-01-01", "OLDINE"), "MIDBRAND": ("000200", "2008-05-01", "MIDINE"),
                 "NEWBRAND": ("000300", "2012-06-01", "NEWINE"), "ZEPRA": ("200001", "2010-10-28", "ZEPRINE")}
    ANDAS = {"OLDINE": "2005-01-01"}

    def brand_approval(self, brand):
        b = brand.upper()
        if b not in self.APPROVALS:
            return None
        appl, d, ingr = self.APPROVALS[b]
        return verify.Approval(b, appl, "NDA", ingr, d)

    def first_anda(self, ingredient):
        return self.ANDAS.get(ingredient)


def test_check_competitors():
    proposed = [{"brand": b} for b in ["Oldbrand", "Midbrand", "midbrand", "Newbrand", "Madeup"]]
    kept, dropped = verify.check_competitors(proposed, "2011-01-01", StubFDA())
    assert [k.brand for k in kept] == ["MIDBRAND"]
    assert dict(dropped) == {"Oldbrand": "generic entry 2005-01-01 (first ANDA approval (proxy)), before the launch",
                             "Newbrand": "approved 2012-06-01, not before the launch (2011-01-01)",
                             "Madeup": "not found as an NDA / BLA brand in Drugs@FDA"}


def test_generic_entry_prefers_sdud_for_pool_brands():
    analogs = pd.DataFrame({"brand name": ["Midbrand", "Oldbrand"], "generic / exclusivity date": ["", "2012Q3"]})
    ge = verify.GenericEntry(analogs, StubFDA())
    old, mid = StubFDA().brand_approval("Oldbrand"), StubFDA().brand_approval("Midbrand")
    assert ge(old) == ("2012-07-01", "first generic dispensed (SDUD)")   # not the 2005 ANDA
    assert ge(mid) == (None, "no generic dispensed (SDUD)")
    kept, _ = verify.check_competitors([{"brand": "Oldbrand"}], "2011-01-01", StubFDA(), ge)
    assert [k.brand for k in kept] == ["OLDBRAND"]  # generic dispensed only from 2012


def test_competitor_row_counts_what_code_confirmed():
    llm = FakeLLM({"competitors": {"competitors": [
        {"brand": b, "active_ingredient": "", "approval_year": 2000, "reason": "same disease"}
        for b in ["Midbrand", "Oldbrand", "Zepra", "Madeup"]]}})
    (row,) = extract.read_competitors(ANALOG, llm, StubFDA()).rows
    assert row["field"] == "n_competitors_at_launch" and row["value"] == "1"  # Midbrand; Zepra itself left out
    assert row["quote"] == ("[derived, verify each date] approved for the same indication before launch: "
                            "Midbrand (2008-05-01)")
    assert row["quote_check"] == "not_checked" and "dropped Madeup" in row["notes"] and "dropped Oldbrand" in row["notes"]
    assert row["source_url"].endswith("ApplNo=200001")
    assert "first indication: ZEPRA is indicated" in llm.calls[0][1] and "2011-01-01" in llm.calls[0][1]


# --- writing ------------------------------------------------------------------------------------------------

OLD = ("analog_id,field,value,quote,source_url,source_type,extracted_by,extracted_at,approved,approved_by\r\n"
       "a_oral,line_of_therapy,any,\"x, y\",https://u,ORIG label,seed,2026-10-21,true,Gabrielle\r\n"
       "b_oral,launch_date,2015-08,q,https://v,SEC filing,seed,2026-10-21,false,\r\n")


def test_append_rows_leaves_existing_lines_untouched(tmp_path):
    path = tmp_path / "analog_evidence.csv"
    path.write_bytes(OLD.encode())
    row = extract._row("c_oral", "dosing_frequency", "once daily", "q, with comma", "https://w", "ORIG label",
                       FakeLLM(), "verbatim", "n")
    assert extract.append_rows([row], path) == 1
    lines = path.read_bytes().decode().split("\r\n")
    assert lines[0].endswith(",approved_by,quote_check,approved_at,notes")
    assert "\r\n".join(lines[1:3]) + "\r\n" == OLD.split("\r\n", 1)[1]   # old rows byte for byte
    ev = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert len(ev) == 3 and ev.loc[2, "quote"] == "q, with comma" and ev.loc[2, "approved"] == "false"
    extract.append_rows([row], path)  # a second append doesn't touch the header again
    assert path.read_bytes().decode().count("quote_check") == 1


def test_loaders_read_short_older_rows(tmp_path):
    from analog_finder import io
    path = tmp_path / "analog_evidence.csv"
    path.write_bytes(OLD.encode())
    extract.append_rows([extract._row("c_oral", "line_of_therapy", "later", "q", "u", "ORIG label", FakeLLM(),
                                      "verbatim")], path)
    wide = io.load_approved_evidence(tmp_path)
    assert wide.loc["a_oral", "line_of_therapy"] == "any" and "c_oral" not in wide.index  # unapproved


# --- CLI ----------------------------------------------------------------------------------------------------

def test_cli_with_fake_model_writes_nothing(tmp_path, monkeypatch):
    path = tmp_path / "analog_evidence.csv"
    path.write_bytes(OLD.encode())
    monkeypatch.setattr(cli, "write_report", lambda report, out_dir=None: tmp_path / "report.csv")
    monkeypatch.setattr(extract, "orig_label_url", lambda appl: "")
    import io as _io
    out = _io.StringIO()
    cli.main(["--analogs", "latuda_oral", "--fields", "line_of_therapy"], out=out, gate=FakeGate(tmp_path, {}),
             llm=FakeLLM(), evidence_path=path)
    assert "Nothing written (no GEMINI_API_KEY" in out.getvalue() and path.read_bytes() == OLD.encode()


def test_cli_appends_rows(tmp_path, monkeypatch):
    path = tmp_path / "analog_evidence.csv"
    path.write_bytes(OLD.encode())
    url = "https://www.accessdata.fda.gov/drugsatfda_docs/label/2010/200603s000lbl.pdf"
    monkeypatch.setattr(extract, "orig_label_url", lambda appl: url)
    monkeypatch.setattr(cli, "write_report", lambda report, out_dir=None: tmp_path / "report.csv")
    gate = FakeGate(tmp_path, {url: ("latuda.txt", LABEL_TEXT)})
    llm = ScriptedLLM({"label_read": [GOOD_LABEL]})
    import io as _io
    rows, report = cli.main(["--analogs", "latuda_oral", "--fields", "line_of_therapy", "dosing_frequency"],
                            out=_io.StringIO(), gate=gate, llm=llm, evidence_path=path)
    ev = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert len(ev) == 4 and set(ev.analog_id[2:]) == {"latuda_oral"} and (ev.approved[2:] == "false").all()
    assert [r[2] for r in report] == ["written", "written"]


def test_source_url_needs_one_analog():
    with pytest.raises(SystemExit):
        cli.main(["--source-url", "https://x"], gate=None, llm=FakeLLM())
