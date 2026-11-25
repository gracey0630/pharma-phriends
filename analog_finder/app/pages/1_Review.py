"""Review page (step 12): approve, edit or reject each label read waiting in analog_evidence.csv.

The logic is in analog_finder/research/review.py; this page only shows rows and passes decisions on.
Spec: analog_finder/docs/components/review.md
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:  # streamlit puts only the app folder on the path
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from analog_finder.finder.target import LINE_CATEGORIES  # noqa: E402
from analog_finder.research import review  # noqa: E402

PER_PAGE = 10
SHOW = {"Waiting": "waiting", "Approved": "approved", "Rejected": "rejected", "All": None}
CHECK_COLOURS = {"verbatim": "green", "partial": "orange"}

st.set_page_config(page_title="Review label reads", layout="wide")
st.title("Review label reads")


@st.cache_data(show_spinner="Ordering by the scenario's work queue...")
def queue_order(scenario):
    """analog_id -> queue priority for the scenario; empty if it can't be built (rows then sort by analog)."""
    if not scenario:
        return {}
    from analog_finder.research import queue
    q = queue.for_scenario(scenario)
    return q.groupby("analog_id").priority.min().to_dict()


def esc(text):
    """Show source text as written: markdown characters in a quote are not formatting."""
    return "".join("\\" + ch if ch in "\\`*_{}[]<>()#+-.!|$~" else ch for ch in str(text))


with st.sidebar:
    reviewer = st.text_input("Your name (saved as approved_by)", key="reviewer")
    scenario = st.text_input("Scenario (optional: review its likely analogs first)", value="", key="scenario",
                             placeholder="e.g. torevia; empty = all analogs, A to Z")
    show = st.radio("Show", list(SHOW), key="show")
    fields = st.multiselect("Fields", list(review.FIELD_LABELS), format_func=review.FIELD_LABELS.get, key="fields")
    analog = st.text_input("Analog contains", key="analog")
    st.caption("One reviewer per batch: when you're done, run `python -m pipeline.labels --check` and commit "
               "`data/reference/analog_evidence.csv`.")

path = review.evidence_path(st.session_state.get("evidence_path"))
ev = review.load(path)
try:
    order = queue_order(scenario.strip())
except Exception as e:  # a bad scenario name shouldn't hide the rows
    st.sidebar.warning(f"Couldn't order by scenario {scenario!r}: {e}")
    order = {}

c = review.counts(ev)
m1, m2, m3 = st.columns(3)
m1.metric("Waiting for review", c["waiting"])
m2.metric("Approved", c["approved"])
m3.metric("Rejected", c["rejected"])

if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))

rows = review.to_review(ev, order) if SHOW[show] == "waiting" else (
    ev if SHOW[show] is None else ev[ev.status == SHOW[show]])
if fields:
    rows = rows[rows.field.isin(fields)]
if analog.strip():
    rows = rows[rows.analog_id.str.contains(analog.strip(), case=False, regex=False)]

if rows.empty:
    st.info("Nothing to show." + (" Every row is decided." if SHOW[show] == "waiting" and not c["waiting"] else ""))
    st.stop()

pages = (len(rows) - 1) // PER_PAGE + 1
if st.session_state.get("page", 1) > pages:  # a filter shrank the list
    st.session_state["page"] = 1
# No default value: the page starts at the minimum (1), and setting st.session_state["page"] above doesn't clash
# with a widget default (Streamlit's "default value but also set via the Session State API" warning).
page = st.number_input(f"Page (of {pages}; {len(rows)} rows)", 1, pages, key="page") if pages > 1 else 1
start = (page - 1) * PER_PAGE

for r in rows.iloc[start:start + PER_PAGE].to_dict("records"):
    n = r["row"]
    with st.container(border=True):
        check = r["quote_check"] or "not checked"
        st.markdown(f"**{esc(r['analog_id'])}** · {review.FIELD_LABELS.get(r['field'], esc(r['field']))} · "
                    f":{CHECK_COLOURS.get(check, 'gray')}[{esc(check)}]")
        st.markdown(f"Value: **{esc(r['value'])}**")
        st.markdown("> " + esc(r["quote"]).replace("\n", " "))
        url, kind = review.link(r["source_url"]), esc(r["source_type"] or "link")
        source = f"[{kind}]({url})" if url else f"{kind} ({esc(r['source_url']) or 'no link'})"
        st.markdown(f"Source: {source} · read by {esc(r['extracted_by'])} on {esc(r['extracted_at'])}")
        if r["notes"]:
            st.warning(r["notes"])
        if r["status"] != "waiting":
            st.caption(f"{r['status'].capitalize()} by {r['approved_by'] or '?'}"
                       + (f" at {r['approved_at']}" if r["approved_at"] else ""))
            continue
        if r["field"] in review.SOURCE_CHECK_FIELDS:
            st.caption("Not a label quote: open the source and check the value yourself.")
        if review.is_forecast(r["field"], r["quote"]):
            st.warning("This quote reads like a forecast (\"expected\", \"plans to\" or [excerpt, verify]), not a "
                       "launch. Approve only if the source confirms the drug actually launched; otherwise reject "
                       f"with \"{review.FORECAST_REASON}\".", icon="⚠️")

        with st.form(key=f"form-{n}"):
            if r["field"] == "line_of_therapy":
                cats = list(LINE_CATEGORIES)
                cur = r["value"].strip().lower()
                value = st.selectbox("Value", cats, index=cats.index(cur) if cur in cats else 0, key=f"value-{n}")
            else:
                value = st.text_input("Value", r["value"], key=f"value-{n}")
            quote = st.text_area("Quote (edit only if the value rests on different words)", r["quote"],
                                 key=f"quote-{n}")
            need = review.needs_source_check(r["field"], r["quote_check"])
            checked = st.checkbox(review.CHECK_LABEL, key=f"checked-{n}") if need else False
            reason = st.selectbox("Reason, if rejecting", [""] + review.REJECT_REASONS, key=f"reason-{n}")
            note = st.text_input("Note (optional)", key=f"note-{n}")
            left, right = st.columns(2)
            approve = left.form_submit_button("Approve", type="primary", key=f"approve-{n}")
            reject = right.form_submit_button("Reject", key=f"reject-{n}")
        if approve or reject:
            try:
                review.decide(path, n, r["fingerprint"], "approve" if approve else "reject", reviewer,
                              value=value, quote=quote, checked=checked, reason=reason, note=note)
            except review.ReviewError as e:
                st.error(str(e))
            else:
                st.session_state["flash"] = (f"{'Approved' if approve else 'Rejected'}: {r['analog_id']} "
                                             f"{review.FIELD_LABELS.get(r['field'], r['field'])}.")
                st.rerun()
