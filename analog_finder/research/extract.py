"""The Label Research Agent's readers: one per evidence field, each returning evidence rows (approved=false) for a
person to review, or a reason it wrote nothing.

  label fields (line_of_therapy, dosing_frequency)  ORIG label PDF, one model call per label
  launch_date                                       SEC EDGAR full-text search, or a page a person names
  n_competitors_at_launch                           model proposes, Drugs@FDA confirms, code counts

Every fetch goes through the approved-source gate (sources.py). Rows are only ever appended (append_rows).

Spec: analog_finder/docs/components/extract.md
"""
import csv
import json
import io as _io
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote as urlquote

import pandas as pd

from analog_finder.finder.score import doses_per_week, line_cross_check
from analog_finder.finder.target import LINE_CATEGORIES
from analog_finder.research import verify
from pipeline.build import EVIDENCE_COLS
from pipeline.labels import orig_label_url

NEW_COLS = ["quote_check", "approved_at", "notes"]  # Shared contracts (evidence row); blank for older rows
LABEL_CHARS = 40_000  # Highlights, Indications, Dosage and Administration sit at the start of a label
LAUNCH_WORDS = re.compile(r"launch|commercial(?:ly)? availab|now available|commenc|introduc|began (?:selling|shipping)|"
                          r"first (?:prescriptions?|sales)|promotion", re.I)
FORECAST_MARK = "forecast"
EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
DAF_OVERVIEW = "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={}"


@dataclass
class Analog:
    """What the readers need to know about one analog."""
    analog_id: str
    brand: str
    orig_application: str       # e.g. NDA200603
    indication: str
    approval_date: str          # YYYY-MM-DD
    launch_point: str           # YYYY-MM-DD: approved launch date, else the first day of the launch quarter


@dataclass
class Result:
    rows: list = field(default_factory=list)       # evidence rows (dicts) to append
    skipped: list = field(default_factory=list)    # (field, reason, detail) for the run report


def _row(analog_id, fld, value, quote, url, source_type, llm, quote_check, notes=""):
    return {"analog_id": analog_id, "field": fld, "value": str(value), "quote": quote, "source_url": url,
            "source_type": source_type, "extracted_by": f"agent:{llm.name}", "extracted_at": date.today().isoformat(),
            "approved": "false", "approved_by": "", "quote_check": quote_check, "approved_at": "", "notes": notes}


def _appl_digits(appl):
    return re.sub(r"\D", "", str(appl))


# --- label fields ---------------------------------------------------------------------------------------------

LABEL_SCHEMA = {
    "title": "label_read", "type": "object",
    "required": ["line_of_therapy", "line_of_therapy_quote", "dosing_frequency", "dosing_frequency_quote"],
    "properties": {
        "line_of_therapy": {"type": "string", "enum": list(LINE_CATEGORIES)},
        "line_of_therapy_quote": {"type": "string"},
        "dosing_frequency": {"type": "string"},
        "dosing_frequency_quote": {"type": "string"},
    },
}

LABEL_PROMPT = """You are reading the ORIGINAL FDA approval label of {brand}. Fill two fields from the label text below.

1. line_of_therapy, from section 1 (INDICATIONS AND USAGE), about the first indication only. One of:
   - "first": the label limits use to patients not previously treated (e.g. "initial therapy", "previously untreated")
   - "later": the label requires prior therapy (e.g. "after failure of", "who have received at least one prior")
   - "any": the label sets no requirement about prior therapy (e.g. "treatment of schizophrenia in adults")
   - "not stated": you can't tell from the label
   Being a "candidate for systemic therapy" is not a prior-therapy requirement.
2. dosing_frequency, from section 2 (DOSAGE AND ADMINISTRATION): how often the maintenance dose is taken, short, in
   this style: "once daily", "twice daily (after 5-day titration)", "every 4 weeks (loading doses at weeks 0 and 2)".

For each field also give the quote it rests on: one sentence or clause copied EXACTLY, word for word, from the label
text below. Don't paraphrase, shorten or fix it.
{retry}
LABEL TEXT:
{text}"""


def read_label(analog, gate, llm, fields=("line_of_therapy", "dosing_frequency")):
    """Rows for the label fields asked for, from the analog's ORIG label."""
    res = Result()
    url = orig_label_url(_appl_digits(analog.orig_application))
    if not url:
        res.skipped += [(f, "no ORIG label in Drugs@FDA", analog.orig_application) for f in fields]
        return res
    try:
        page = gate.fetch(url, "line_of_therapy", analog_id=analog.analog_id)
    except Exception as e:  # refused by the gate, or a network error: report and move on
        res.skipped += [(f, "label not fetched", str(e)) for f in fields]
        return res
    text = verify.page_text(page.path)

    answer, retry = None, ""
    for _attempt in range(2):
        answer = llm.generate_json(LABEL_PROMPT.format(brand=analog.brand, retry=retry, text=text[:LABEL_CHARS]),
                                   LABEL_SCHEMA)
        checks = {f: verify.quote_check(answer[f"{f}_quote"], text) for f in fields}
        bad = [f for f in fields if checks[f][0] != "verbatim"]
        if not bad:
            break
        retry = ("\nYour previous quotes for " + ", ".join(bad) + " were not found word for word in the label. "
                 "Copy each quote exactly as it appears.\n")

    for f in fields:
        value, quote = str(answer[f]).strip(), str(answer[f"{f}_quote"]).strip()
        if not value:
            res.skipped.append((f, "model gave no value", ""))
            continue
        status, note = checks[f]
        notes = [note] if note else []
        if f == "line_of_therapy":
            if value not in LINE_CATEGORIES:
                res.skipped.append((f, f"not a category: {value!r}", ""))
                continue
            other = line_cross_check(value, quote)
            if other:
                notes.append(f"keywords in the quote read as {other}")
        if f == "dosing_frequency" and doses_per_week(value) is None:
            notes.append("frequency not machine-readable")
        res.rows.append(_row(analog.analog_id, f, value, quote, url, "ORIG label", llm, status, "; ".join(notes)))
    return res


# --- launch date ----------------------------------------------------------------------------------------------

LAUNCH_SCHEMA = {
    "title": "launch_date", "type": "object", "required": ["status", "date", "quote", "passage"],
    "properties": {
        "status": {"type": "string", "enum": ["launched", "forecast", "none"]},
        "date": {"type": "string"},
        "quote": {"type": "string"},
        "passage": {"type": "integer"},
    },
}

LAUNCH_PROMPT = """When did {brand} first become commercially available in the US (its launch, not its FDA approval
on {approval})? Below are numbered passages from company filings and releases.

Answer with:
- status: "launched" if a passage states the launch happened (e.g. "launched in February 2011", "commercially
  available since"), "forecast" if passages only say it is expected / planned / will be available, else "none"
- date: YYYY-MM-DD if the passage gives the day, YYYY-MM if only the month; "" otherwise. Never invent a day.
- quote: the sentence that states it, copied EXACTLY from the passage
- passage: the number of that passage (0 if none)

PASSAGES:
{passages}"""


def _passages(text, brand, width=400):
    """Stretches of text around each mention of the brand that also use a launch word."""
    out = []
    for m in re.finditer(re.escape(brand), text, re.I):
        chunk = text[max(0, m.start() - width): m.end() + width]
        if LAUNCH_WORDS.search(chunk) and chunk not in out:
            out.append(" ".join(chunk.split()))
    return out


def edgar_urls(analog, gate, months=15, limit=12):
    """Filing documents on www.sec.gov mentioning the brand, from approval to approval + `months`, oldest first."""
    start = date.fromisoformat(analog.approval_date)
    end = start + timedelta(days=int(months * 30.5))
    url = (f"{EDGAR_SEARCH}?q=%22{urlquote(analog.brand)}%22&forms=8-K,10-Q,10-K&dateRange=custom"
           f"&startdt={start}&enddt={end}")
    page = gate.fetch(url, "launch_date", analog_id=analog.analog_id)
    hits = json.loads(page.path.read_text()).get("hits", {}).get("hits", [])
    docs = []
    for h in sorted(hits, key=lambda h: h.get("_source", {}).get("file_date", "")):
        src = h.get("_source", {})
        adsh, _, filename = h.get("_id", "").partition(":")
        cik = (src.get("ciks") or [""])[0].lstrip("0")
        if adsh and filename and cik:
            docs.append(f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{filename}")
    return list(dict.fromkeys(docs))[:limit]


def read_launch_date(analog, gate, llm, source_url=None):
    """A launch_date row from SEC filings (or from `source_url`, a page a person found on an approved source)."""
    res = Result()
    try:
        urls = [source_url] if source_url else edgar_urls(analog, gate)
    except Exception as e:
        res.skipped.append(("launch_date", "search failed", str(e)))
        return res
    passages, texts = [], {}
    for u in urls:
        try:
            page = gate.fetch(u, "launch_date", analog_id=analog.analog_id)
        except Exception as e:
            res.skipped.append(("launch_date", "page not fetched", f"{u}: {e}"))
            continue
        texts[u] = verify.page_text(page.path)
        passages += [(u, p) for p in _passages(texts[u], analog.brand)]
    if not passages:
        res.skipped.append(("launch_date", "no passage mentions a launch", f"{len(urls)} documents read"))
        return res
    passages = passages[:40]
    listing = "\n\n".join(f"[{i}] {p}" for i, (_, p) in enumerate(passages, 1))
    a = llm.generate_json(LAUNCH_PROMPT.format(brand=analog.brand, approval=analog.approval_date, passages=listing),
                          LAUNCH_SCHEMA)
    n = int(a.get("passage") or 0)
    url = passages[n - 1][0] if 1 <= n <= len(passages) else ""
    if a["status"] == FORECAST_MARK:
        res.skipped.append(("launch_date", "only a forecast found (not written)", f"{url}: {a['quote']}"))
        return res
    if a["status"] != "launched" or not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", str(a["date"])) or not url:
        res.skipped.append(("launch_date", "no launch statement found", f"{len(passages)} passages"))
        return res
    status, note = verify.quote_check(a["quote"], texts[url])
    source_type = "SEC filing" if "sec.gov" in url else "company release"
    res.rows.append(_row(analog.analog_id, "launch_date", a["date"], a["quote"].strip(), url, source_type, llm,
                         status, note))
    return res


# --- competitors ----------------------------------------------------------------------------------------------

COMPETITOR_SCHEMA = {
    "title": "competitors", "type": "object", "required": ["competitors"],
    "properties": {"competitors": {"type": "array", "items": {
        "type": "object", "required": ["brand", "active_ingredient", "approval_year", "reason"],
        "properties": {"brand": {"type": "string"}, "active_ingredient": {"type": "string"},
                       "approval_year": {"type": "integer"}, "reason": {"type": "string"}}}}},
}

COMPETITOR_PROMPT = """List the US competitors {brand} had when it launched ({launch}).

A competitor is a BRANDED NOVEL drug (a new molecular entity NDA or a new biologic BLA; any class, any route) that
FDA approved for the SAME disease and treatment setting as {brand}'s first indication, before {launch}. Same
setting means e.g. acute vs preventive migraine are different. Leave out biosimilars, withdrawn drugs and drugs
whose generic was available by {launch}. Don't use drug class to decide: drugs of other classes for the same
disease count, drugs of the same class for other diseases don't.

{brand}'s first indication: {indication}

For each competitor give the US brand name exactly as FDA lists it, the active ingredient, the approval year and a
short reason it treats the same disease and setting. List every one you know; dates are checked afterwards."""


def read_competitors(analog, llm, fda, generic_entry=None):
    res = Result()
    a = llm.generate_json(COMPETITOR_PROMPT.format(brand=analog.brand, launch=analog.launch_point,
                                                   indication=analog.indication), COMPETITOR_SCHEMA)
    kept, dropped = verify.check_competitors(a["competitors"], analog.launch_point, fda, generic_entry)
    own = analog.brand.upper()
    kept = [k for k in kept if k.brand != own]
    listed = ", ".join(f"{k.brand.title()} ({k.approval_date})" for k in kept) or "none"
    quote = f"[derived, verify each date] approved for the same indication before launch: {listed}"
    notes = "; ".join([f"proposed by the model, approval dates from Drugs@FDA; launch point {analog.launch_point}"] +
                      [f"dropped {b}: {why}" for b, why in dropped])
    url = DAF_OVERVIEW.format(_appl_digits(analog.orig_application))
    res.rows.append(_row(analog.analog_id, "n_competitors_at_launch", len(kept), quote, url,
                         "derived from FDA approval history", llm, "not_checked", notes))
    return res


# --- writing --------------------------------------------------------------------------------------------------

def append_rows(rows, path):
    """Append evidence rows to analog_evidence.csv without touching any existing line.

    The header gains NEW_COLS if missing (older rows stay as they are, read as blank there). Afterwards the
    existing rows are read back and compared; any difference restores the file and raises."""
    path = Path(path)
    before = path.read_bytes() if path.exists() else b""
    text = before.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline) if text else []
    header = next(csv.reader([lines[0]])) if lines else list(EVIDENCE_COLS)
    header += [c for c in NEW_COLS if c not in header]
    old = pd.read_csv(path, dtype=str, keep_default_na=False) if before else pd.DataFrame(columns=header)

    buf = _io.StringIO()
    w = csv.writer(buf, lineterminator=newline)
    for r in rows:
        w.writerow([r.get(c, "") for c in header])
    body = newline.join(lines[1:]) if lines else ""
    if body and not body.endswith(newline):
        body += newline
    head = _io.StringIO()
    csv.writer(head, lineterminator=newline).writerow(header)
    path.write_text(head.getvalue() + body + buf.getvalue(), encoding="utf-8", newline="")

    after = pd.read_csv(path, dtype=str, keep_default_na=False)
    same = len(after) == len(old) + len(rows) and after.iloc[:len(old)][list(old.columns)].reset_index(drop=True) \
        .equals(old.reset_index(drop=True))
    if not same:
        path.write_bytes(before)
        raise RuntimeError(f"{path}: existing rows changed while appending; file restored")
    return len(rows)
