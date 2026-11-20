"""Review of the Label Research Agent's rows (step 12): approve, edit or reject each unapproved evidence row.

Used by the app's review page (analog_finder/app/pages/1_Review.py); plain code, so it's tested without a browser.

  load(path)            every row of analog_evidence.csv, with its row number, review status and a fingerprint
  to_review(ev, order)  the rows waiting for review, in review order
  decide(path, ...)     write one decision; every other line of the file stays byte for byte

`approved` is `true`, `false` (waiting) or `rejected` (decisions.md 2026-11-20). Approved and rejected rows are never
changed here (CLAUDE.md: never overwrite an approved row).

Spec: analog_finder/docs/components/review.md
"""
import csv
import hashlib
import io as _io
from datetime import datetime
from pathlib import Path

import pandas as pd

from analog_finder.finder.score import doses_per_week
from analog_finder.finder.target import LINE_CATEGORIES
from analog_finder.research.extract import NEW_COLS
from pipeline.build import EVIDENCE_COLS, EVIDENCE_FIELDS
from pipeline.common import REFERENCE

FIELD_LABELS = {"line_of_therapy": "Line of therapy", "n_competitors_at_launch": "# competitors at launch",
                "launch_date": "Launch date", "dosing_frequency": "Dosing frequency"}
# Not label quotes: the reviewer checks the source itself (data_model.md, label-reads plan, review)
SOURCE_CHECK_FIELDS = ("launch_date", "n_competitors_at_launch")
CHECK_LABEL = "I checked the value against the source myself"
REJECT_REASONS = ["value doesn't match the quote", "quote isn't on the source page", "wrong source or drug",
                  "a forecast, not a launch", "other"]
FINGERPRINT_COLS = ["analog_id", "field", "value", "quote", "source_url", "extracted_at", "approved"]


class ReviewError(ValueError):
    """A decision that can't be written; nothing was changed."""


def evidence_path(path=None):
    return Path(path) if path else REFERENCE / "analog_evidence.csv"


def status(approved):
    """'approved', 'rejected' or 'waiting' for an `approved` cell."""
    a = str(approved).strip().lower()
    return "approved" if a == "true" else "rejected" if a == "rejected" else "waiting"


def fingerprint(row):
    """Short hash of what the reviewer sees of a row, to catch a file that changed under them."""
    text = "\x1f".join(str(row.get(c, "")) for c in FINGERPRINT_COLS)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def load(path=None):
    """Every row as strings, plus `row` (0-based data row number), `status` and `fingerprint`."""
    path = evidence_path(path)
    if not path.exists():
        ev = pd.DataFrame(columns=EVIDENCE_COLS)
    else:
        ev = pd.read_csv(path, dtype=str, keep_default_na=False)
    for c in NEW_COLS:
        if c not in ev.columns:
            ev[c] = ""
    ev.insert(0, "row", range(len(ev)))
    ev["status"] = ev.approved.map(status)
    ev["fingerprint"] = [fingerprint(r) for r in ev.to_dict("records")]
    return ev


def counts(ev):
    return {s: int((ev.status == s).sum()) for s in ("waiting", "approved", "rejected")}


def to_review(ev, order=None):
    """The rows waiting for review: by `order` (analog_id -> queue priority; unknown analogs last), then analog,
    then field in queue order, so one label is read once for its two label fields."""
    order = order or {}
    fields = {f: i for i, f in enumerate(EVIDENCE_FIELDS)}
    w = ev[ev.status == "waiting"].copy()
    w["_p"] = w.analog_id.map(lambda a: order.get(a, 99))
    w["_f"] = w.field.map(lambda f: fields.get(f, 99))
    return w.sort_values(["_p", "analog_id", "_f", "row"]).drop(columns=["_p", "_f"])


def needs_source_check(field, quote_check):
    """A partial or unchecked quote, a launch date or a competitor count: approving needs the reviewer's tick."""
    return field in SOURCE_CHECK_FIELDS or str(quote_check).strip().lower() != "verbatim"


# --- writing one decision ---------------------------------------------------------------------------------------

def _records(text, nl):
    """Split CSV text into raw records (a quoted field may hold a line break), keeping each record's exact text."""
    out, buf = [], []
    for line in text.split(nl):
        buf.append(line)
        joined = nl.join(buf)
        if joined.count('"') % 2 == 0:
            out.append(joined)
            buf = []
    if buf:
        out.append(nl.join(buf))
    return out


def _line(values):
    s = _io.StringIO()
    csv.writer(s, lineterminator="").writerow(values)
    return s.getvalue()


def _append_note(notes, *new):
    parts = [p for p in [str(notes).strip(), *new] if p]
    return "; ".join(parts)


def decide(path, row, seen, decision, reviewer, value=None, quote=None, checked=False, reason="", note="",
           now=None):
    """Approve or reject data row `row` (0-based) of the evidence file, which the reviewer saw with fingerprint
    `seen`. Approving may change the value and the quote first. Returns the row as written.

    Raises ReviewError, with the file unchanged, when: the name is blank; the row isn't waiting or changed since it
    was loaded; a line-of-therapy value isn't a category; a source check is needed and not ticked; a rejection
    has no reason (or 'other' without a note)."""
    path = evidence_path(path)
    reviewer = str(reviewer or "").strip()
    if decision not in ("approve", "reject"):
        raise ReviewError(f"decision must be 'approve' or 'reject', got {decision!r}")
    if not reviewer:
        raise ReviewError("Type your name in the sidebar first: it's saved as approved_by.")

    before = path.read_bytes()
    text = before.decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    old = pd.read_csv(path, dtype=str, keep_default_na=False)
    if not 0 <= row < len(old):
        raise ReviewError(f"row {row} isn't in {path.name} ({len(old)} rows); reload the page")
    current = old.iloc[row].to_dict()
    if fingerprint(current) != seen:
        raise ReviewError(f"{current.get('analog_id', '')} {current.get('field', '')}: this row changed since the page "
                          "loaded it (someone else saved the file?). Reload and look again.")
    if status(current["approved"]) != "waiting":
        raise ReviewError("This row is already decided; approved and rejected rows aren't changed.")

    records = _records(text, nl)
    trailing = records[-1] == ""
    data = records[1:-1] if trailing else records[1:]
    if len(data) != len(old):
        raise ReviewError(f"{path.name}: {len(data)} lines but {len(old)} rows; fix the file in a spreadsheet first")
    header = next(csv.reader([records[0]]))
    header_new = header + [c for c in NEW_COLS if c not in header]

    new = {c: current.get(c, "") for c in header_new}
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    fld = current["field"]
    if decision == "approve":
        new_value = current["value"] if value is None else str(value).strip()
        new_quote = current["quote"] if quote is None else str(quote).strip()
        if not new_value:
            raise ReviewError("The value is empty; reject the row instead.")
        if fld == "line_of_therapy" and new_value.lower() not in LINE_CATEGORIES:
            raise ReviewError(f"Line of therapy must be one of {', '.join(LINE_CATEGORIES)}.")
        notes = []
        if new_value != current["value"]:
            notes.append(f"edited by {reviewer}: value was {current['value']!r}")
        if new_quote != current["quote"]:
            notes.append(f"quote edited by {reviewer}; run pipeline.labels --check")
            new["quote_check"] = "not_checked"
        if needs_source_check(fld, new.get("quote_check", "")):
            if not checked:
                raise ReviewError(f"Tick '{CHECK_LABEL}' first: "
                                  + ("launch dates and competitor counts aren't label quotes."
                                     if fld in SOURCE_CHECK_FIELDS else "the quote isn't verbatim on its source."))
            notes.append(f"source checked by {reviewer}")
        if fld == "dosing_frequency" and doses_per_week(new_value) is None \
                and "not machine-readable" not in current.get("notes", ""):
            notes.append("frequency not machine-readable")
        if note.strip():
            notes.append(f"{reviewer}: {note.strip()}")
        new.update(value=new_value.lower() if fld == "line_of_therapy" else new_value, quote=new_quote,
                   approved="true")
    else:
        reason = str(reason or "").strip()
        if not reason:
            raise ReviewError("Pick a reason for rejecting.")
        if reason == "other" and not note.strip():
            raise ReviewError("Say why in the note when the reason is 'other'.")
        notes = [f"rejected by {reviewer}: {reason}" + (f" ({note.strip()})" if note.strip() else "")]
        new["approved"] = "rejected"
    new.update(approved_by=reviewer, approved_at=stamp, notes=_append_note(current.get("notes", ""), *notes))

    head = records[0] if header_new == header else _line(header_new)
    data[row] = _line([new[c] for c in header_new])
    path.write_bytes((nl.join([head] + data) + (nl if trailing else "")).encode("utf-8"))

    after = pd.read_csv(path, dtype=str, keep_default_na=False)
    others = [i for i in range(len(old)) if i != row]
    ok = len(after) == len(old) and after.iloc[others][list(old.columns)].reset_index(drop=True).equals(
        old.iloc[others].reset_index(drop=True)) and after.iloc[row]["approved"] == new["approved"]
    if not ok:
        path.write_bytes(before)
        raise ReviewError(f"{path.name}: other rows changed while saving; file restored, nothing written")
    return new
