"""Review (step 12): decisions written to a copy of the evidence file, and the app pages run headless. Offline."""
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from analog_finder import io
from analog_finder.research import queue, review

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "analog_finder" / "app"
NOW = datetime(2026, 11, 20, 14, 5, 9)
LABEL = "https://www.accessdata.fda.gov/drugsatfda_docs/label/2010/200603s000lbl.pdf"

# An older file: the 10 original columns, then a step-11 row that widened the header. Older rows stay short.
OLD_FILE = (
    "analog_id,field,value,quote,source_url,source_type,extracted_by,extracted_at,approved,approved_by\n"
    'otezla_oral,line_of_therapy,no prior therapy required,"OTEZLA, an inhibitor of PDE4, is indicated for the '
    'treatment of adult patients with active psoriatic arthritis",https://x.gov/otezla.pdf,ORIG label,'
    "claude (Claude Code),2026-10-21,true,Gabrielle\n"
    'taltz_sc,launch_date,2016-03,"[excerpt, verify] Taltz is expected to be available\nin the coming weeks",'
    "https://www.sec.gov/a.htm,SEC filing,claude (Claude Code),2026-10-21,false,\n"
)
AGENT = ["latuda_oral,line_of_therapy,any,LATUDA is indicated for the treatment of patients with schizophrenia,"
         f"{LABEL},ORIG label,agent:gemini,2026-11-20,false,,verbatim,,",
         f"latuda_oral,dosing_frequency,once daily,The recommended starting dose is 40 mg once daily,{LABEL},"
         "ORIG label,agent:gemini,2026-11-20,false,,partial,,first 7 of 9 words match the source",
         "latuda_oral,n_competitors_at_launch,3,\"[derived, verify each date] approved for the same indication "
         "before launch: Abilify (2002-11-15), Invega (2006-12-19), Fanapt (2009-05-06)\",https://www.accessdata.fda"
         ".gov/x,derived from FDA approval history,agent:gemini,2026-11-20,false,,not_checked,,dropped Zyprexa: "
         "generic entry 2011-10-24"]


@pytest.fixture
def evfile(tmp_path):
    p = tmp_path / "analog_evidence.csv"
    header = "analog_id,field,value,quote,source_url,source_type,extracted_by,extracted_at,approved,approved_by," \
             "quote_check,approved_at,notes"
    body = OLD_FILE.split("\n", 1)[1]
    p.write_text(header + "\n" + body + "\n".join(AGENT) + "\n", encoding="utf-8")
    return p


def rec(path, analog_id, field):
    ev = review.load(path)
    return ev[(ev.analog_id == analog_id) & (ev.field == field)].iloc[0].to_dict()


def decide(path, analog_id, field, decision, **kw):
    r = rec(path, analog_id, field)
    kw.setdefault("now", NOW)
    return review.decide(path, r["row"], r["fingerprint"], decision, kw.pop("reviewer", "Joshua"), **kw)


def lines(path):
    return path.read_bytes().split(b"\n")


# --- loading and order -------------------------------------------------------------------------------------------

def test_load_reads_status_and_short_rows(evfile):
    ev = review.load(evfile)
    assert list(ev.status) == ["approved", "waiting", "waiting", "waiting", "waiting"]
    assert ev.loc[0, "quote_check"] == "" and ev.loc[0, "notes"] == ""          # short row: blank new columns
    assert "\n" in ev.loc[1, "quote"]                                             # a quoted line break survives
    assert review.counts(ev) == {"waiting": 4, "approved": 1, "rejected": 0}
    assert review.status(" TRUE ") == "approved" and review.status("Rejected") == "rejected"
    assert review.status("false") == review.status("") == "waiting"


def test_review_order_follows_queue_priority_then_field(evfile):
    ev = review.load(evfile)
    got = review.to_review(ev, {"latuda_oral": 1, "taltz_sc": 3})
    assert list(zip(got.analog_id, got.field)) == [
        ("latuda_oral", "line_of_therapy"), ("latuda_oral", "n_competitors_at_launch"),
        ("latuda_oral", "dosing_frequency"), ("taltz_sc", "launch_date")]
    assert list(review.to_review(ev).analog_id) == ["latuda_oral"] * 3 + ["taltz_sc"]  # no order: by analog


def test_needs_source_check():
    assert not review.needs_source_check("line_of_therapy", "verbatim")
    assert review.needs_source_check("dosing_frequency", "partial")
    assert review.needs_source_check("line_of_therapy", "")                       # older rows: never checked
    assert review.needs_source_check("launch_date", "verbatim")                   # not a label quote
    assert review.needs_source_check("n_competitors_at_launch", "not_checked")


# --- approving ---------------------------------------------------------------------------------------------------

def test_approve_saves_it_and_keeps_every_other_line(evfile):
    before = lines(evfile)
    out = decide(evfile, "latuda_oral", "line_of_therapy", "approve")
    after = lines(evfile)
    assert len(after) == len(before)
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert changed == [4]                                                         # header + 2 old lines (one spans 2)
    r = rec(evfile, "latuda_oral", "line_of_therapy")
    assert (r["approved"], r["approved_by"], r["approved_at"]) == ("true", "Joshua", "2026-11-20T14:05:09")
    assert r["notes"] == "" and out["value"] == "any"
    assert io.load_approved_evidence(evfile.parent).loc["latuda_oral", "line_of_therapy"] == "any"


def test_editing_a_value_records_what_it_was(evfile):
    decide(evfile, "latuda_oral", "line_of_therapy", "approve", value="Later", note="label says after one drug")
    r = rec(evfile, "latuda_oral", "line_of_therapy")
    assert r["value"] == "later" and r["quote_check"] == "verbatim"
    assert r["notes"] == "edited by Joshua: value was 'any'; Joshua: label says after one drug"


def test_line_of_therapy_must_be_a_category(evfile):
    before = evfile.read_bytes()
    with pytest.raises(review.ReviewError, match="must be one of"):
        decide(evfile, "latuda_oral", "line_of_therapy", "approve", value="second line")
    assert evfile.read_bytes() == before


def test_partial_quote_needs_the_tick_and_records_it(evfile):
    with pytest.raises(review.ReviewError, match="isn't verbatim"):
        decide(evfile, "latuda_oral", "dosing_frequency", "approve")
    decide(evfile, "latuda_oral", "dosing_frequency", "approve", checked=True)
    r = rec(evfile, "latuda_oral", "dosing_frequency")
    assert r["approved"] == "true"
    assert r["notes"] == "first 7 of 9 words match the source; source checked by Joshua"


def test_competitor_count_needs_the_tick(evfile):
    with pytest.raises(review.ReviewError, match="aren't label quotes"):
        decide(evfile, "latuda_oral", "n_competitors_at_launch", "approve")
    decide(evfile, "latuda_oral", "n_competitors_at_launch", "approve", value="2", checked=True)
    r = rec(evfile, "latuda_oral", "n_competitors_at_launch")
    assert r["value"] == "2" and r["notes"].startswith("dropped Zyprexa")
    assert "edited by Joshua: value was '3'" in r["notes"] and "source checked by Joshua" in r["notes"]


def test_edited_quote_is_unchecked_and_then_needs_the_tick(evfile):
    with pytest.raises(review.ReviewError):
        decide(evfile, "latuda_oral", "line_of_therapy", "approve", quote="LATUDA is indicated for schizophrenia")
    decide(evfile, "latuda_oral", "line_of_therapy", "approve", quote="LATUDA is indicated for schizophrenia",
           checked=True)
    r = rec(evfile, "latuda_oral", "line_of_therapy")
    assert r["quote_check"] == "not_checked" and "quote edited by Joshua" in r["notes"]


def test_unreadable_dosing_is_noted(evfile):
    decide(evfile, "latuda_oral", "dosing_frequency", "approve", value="as directed", checked=True)
    assert "frequency not machine-readable" in rec(evfile, "latuda_oral", "dosing_frequency")["notes"]


def test_old_short_file_gains_the_new_columns(tmp_path):
    p = tmp_path / "analog_evidence.csv"
    p.write_text(OLD_FILE, encoding="utf-8")
    before = lines(p)
    decide(p, "taltz_sc", "launch_date", "approve", checked=True)
    after = lines(p)
    assert after[0] == before[0] + b",quote_check,approved_at,notes"
    assert after[1] == before[1]                                                  # the approved row: untouched
    assert len(after) == len(before)                                              # the quoted line break stays
    r = rec(p, "taltz_sc", "launch_date")
    assert "\n" in r["quote"] and r["approved"] == "true"


# --- rejecting ---------------------------------------------------------------------------------------------------

def test_reject_needs_a_reason_and_is_recorded(evfile):
    with pytest.raises(review.ReviewError, match="reason"):
        decide(evfile, "taltz_sc", "launch_date", "reject")
    with pytest.raises(review.ReviewError, match="note"):
        decide(evfile, "taltz_sc", "launch_date", "reject", reason="other")
    decide(evfile, "taltz_sc", "launch_date", "reject", reason="a forecast, not a launch", note="says expected")
    r = rec(evfile, "taltz_sc", "launch_date")
    assert (r["approved"], r["status"], r["approved_by"]) == ("rejected", "rejected", "Joshua")
    assert r["notes"] == "rejected by Joshua: a forecast, not a launch (says expected)"
    assert r["value"] == "2016-03"                                                # the agent's reading is kept


def test_rejected_item_goes_back_to_todo_and_is_never_used(evfile, finder_tables):
    decide(evfile, "latuda_oral", "line_of_therapy", "reject", reason="value doesn't match the quote")
    ev = io.load_evidence(evfile.parent)
    assert "latuda_oral" not in io.load_approved_evidence(evfile.parent).index or pd.isna(
        io.load_approved_evidence(evfile.parent).loc["latuda_oral", "line_of_therapy"])
    rows = ev[ev.analog_id == "latuda_oral"].copy()
    rows["analog_id"] = "o01_oral"                                                # a usable analog of the fixtures
    tables = dict(finder_tables)
    tables["candidate_pool"] = tables["candidate_pool"].assign(application_number="NDA200000")  # as in test_queue
    q = queue.build_queue(tables, rows, analogs=["o01_oral"], sources=[])
    st = q.set_index("field").status
    assert st["line_of_therapy"] == "todo"                                        # rejected: read again
    assert st["dosing_frequency"] == "pending_review"                             # still waiting


# --- refusals ----------------------------------------------------------------------------------------------------

def test_decided_rows_are_read_only(evfile):
    r = rec(evfile, "otezla_oral", "line_of_therapy")
    with pytest.raises(review.ReviewError, match="already decided"):
        review.decide(evfile, r["row"], r["fingerprint"], "reject", "Joshua", reason="other", note="x")


def test_stale_page_is_refused(evfile):
    r = rec(evfile, "latuda_oral", "line_of_therapy")
    decide(evfile, "latuda_oral", "dosing_frequency", "approve", checked=True)   # another row: fingerprint holds
    review.decide(evfile, r["row"], r["fingerprint"], "approve", "Joshua", now=NOW)
    r2 = rec(evfile, "latuda_oral", "n_competitors_at_launch")
    text = evfile.read_text().replace(",3,\"[derived", ",4,\"[derived")              # someone else edits that row
    evfile.write_text(text)
    before = evfile.read_bytes()
    with pytest.raises(review.ReviewError, match="changed since"):
        review.decide(evfile, r2["row"], r2["fingerprint"], "approve", "Joshua", checked=True)
    assert evfile.read_bytes() == before


def test_name_is_required(evfile):
    with pytest.raises(review.ReviewError, match="name"):
        decide(evfile, "latuda_oral", "line_of_therapy", "approve", reviewer="  ")


def test_crlf_file_keeps_its_line_endings(tmp_path):
    p = tmp_path / "analog_evidence.csv"
    p.write_bytes(OLD_FILE.replace("\n", "\r\n").encode())
    decide(p, "taltz_sc", "launch_date", "reject", reason="a forecast, not a launch")
    raw = p.read_bytes()
    assert raw.count(b"\r\n") == OLD_FILE.count("\n") and b"\n" not in raw.replace(b"\r\n", b"")


def test_spreadsheet_approval_still_counts(evfile):
    text = evfile.read_text().replace(f"agent:gemini,2026-11-20,false,,verbatim", "agent:gemini,2026-11-20,true,Grace,verbatim", 1)
    evfile.write_text(text)
    assert rec(evfile, "latuda_oral", "line_of_therapy")["status"] == "approved"
    assert io.load_approved_evidence(evfile.parent).loc["latuda_oral", "line_of_therapy"] == "any"


# --- the app, headless -------------------------------------------------------------------------------------------

def app(evfile, page, **state):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(page), default_timeout=30)
    at.session_state["evidence_path"] = str(evfile)
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def test_home_shows_the_counts(evfile):
    at = app(evfile, APP / "Home.py")
    assert not at.exception
    assert [m.value for m in at.metric] == ["4", "1", "0"]


def test_review_page_approves_a_row(evfile):
    at = app(evfile, APP / "pages" / "1_Review.py", reviewer="Joshua", scenario="")
    assert not at.exception
    assert len(at.get("form")) == 4                                               # the 4 waiting rows
    row = rec(evfile, "latuda_oral", "line_of_therapy")["row"]
    at.button(key=f"approve-{row}").click().run()
    assert not at.exception and not at.error
    assert rec(evfile, "latuda_oral", "line_of_therapy")["approved_by"] == "Joshua"
    assert "Approved: latuda_oral" in at.success[0].value
    assert len(at.get("form")) == 3


def test_review_page_without_a_name_shows_an_error(evfile):
    at = app(evfile, APP / "pages" / "1_Review.py", scenario="")
    row = rec(evfile, "taltz_sc", "launch_date")["row"]
    at.button(key=f"reject-{row}").click().run()
    assert at.error and "name" in at.error[0].value
    assert rec(evfile, "taltz_sc", "launch_date")["status"] == "waiting"
