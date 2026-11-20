"""Run the Label Research Agent on the work queue: read each (analog, field) still to do and append unapproved
evidence rows to data/reference/analog_evidence.csv for review.

Usage: python -m analog_finder.research [--scenario torevia] [--analogs ID ...] [--fields F ...] [--limit N]
                                        [--redo] [--dry-run] [--source-url URL]

Without GEMINI_API_KEY the model is FakeLLM, so nothing is written (a dry run). A run report goes to
data/raw/research/runs/<timestamp>.csv.

Spec: analog_finder/docs/components/extract.md
"""
import argparse
import csv
import sys
from datetime import datetime, timezone

import pandas as pd

from analog_finder import io, llm as llm_mod
from analog_finder.research import extract, queue, verify
from analog_finder.research.sources import default_gate
from pipeline.common import RAW

LABEL_FIELDS = ("line_of_therapy", "dosing_frequency")
REPORT_COLS = ["analog_id", "field", "outcome", "reason", "detail"]


def _quarter_start(q):
    """'2011Q1' -> '2011-01-01'."""
    q = str(q)
    return f"{q[:4]}-{(int(q[-1]) - 1) * 3 + 1:02d}-01" if len(q) == 6 and q[4] == "Q" else ""


def analogs_for(ids, tables, approved, orig):
    """extract.Analog for each id, from analogs.csv, analog_features and approved launch dates."""
    a = tables["analogs"].set_index("analog_id")
    f = tables["analog_features"].set_index("analog_id")
    out = {}
    for i in ids:
        launch = ""
        if approved is not None and i in approved.index and isinstance(approved.loc[i, "launch_date"], str):
            d = approved.loc[i, "launch_date"].strip()
            launch = d if len(d) == 10 else f"{d[:7]}-01" if len(d) >= 7 else ""
        launch = launch or _quarter_start(f.loc[i, "launch_quarter"]) or str(a.loc[i, "approval date"])[:10]
        out[i] = extract.Analog(i, str(a.loc[i, "brand name"]), str(orig.get(i, "")), str(a.loc[i, "indication"]),
                                str(a.loc[i, "approval date"])[:10], launch)
    return out


def existing_keys(evidence):
    return set(zip(evidence.analog_id, evidence.field, evidence.value, evidence.quote))


def run(items, analogs, gate, llm, fda=None, source_url=None, existing=frozenset(), generic_entry=None):
    """Read every queue item; returns (rows to write, report rows). Label fields share one model call per analog."""
    rows, report = [], []
    for analog_id, group in items.groupby("analog_id", sort=False):
        a, fields = analogs[analog_id], list(group.field)
        results = []
        label = [f for f in fields if f in LABEL_FIELDS]
        if label:
            results.append(extract.read_label(a, gate, llm, label))
        if "launch_date" in fields:
            results.append(extract.read_launch_date(a, gate, llm, source_url))
        if "n_competitors_at_launch" in fields:
            fda = fda or verify.DrugsFDA()
            results.append(extract.read_competitors(a, llm, fda, generic_entry))
        for res in results:
            for r in res.rows:
                if (r["analog_id"], r["field"], r["value"], r["quote"]) in existing:
                    report.append([analog_id, r["field"], "skipped", "same value and quote already in the file", ""])
                    continue
                rows.append(r)
                report.append([analog_id, r["field"], "written", r["quote_check"], r["notes"]])
            report += [[analog_id, f, "skipped", why, detail] for f, why, detail in res.skipped]
    return rows, report


def write_report(report, out_dir=None):
    out_dir = out_dir or RAW / "research" / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(REPORT_COLS)
        w.writerows(report)
    return path


def main(argv=None, out=sys.stdout, gate=None, llm=None, fda=None, evidence_path=None):
    ap = argparse.ArgumentParser(prog="python -m analog_finder.research", description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", default="torevia", help="sets the queue order (default torevia)")
    ap.add_argument("--analogs", nargs="+", metavar="ANALOG_ID")
    ap.add_argument("--fields", nargs="+", choices=queue.FIELDS)
    ap.add_argument("--limit", type=int, default=5, help="analogs to read this run (default 5; 0 = all)")
    ap.add_argument("--redo", action="store_true", help="also read items already waiting for review")
    ap.add_argument("--dry-run", action="store_true", help="print the rows, write nothing")
    ap.add_argument("--source-url", help="launch date from this page (one analog; an approved source)")
    args = ap.parse_args(argv)
    if args.source_url and (not args.analogs or len(args.analogs) != 1):
        ap.error("--source-url needs exactly one --analogs")

    cfg = io.load_config(args.scenario)
    evidence_path = evidence_path or cfg["paths"]["reference"] / "analog_evidence.csv"
    q = queue.for_scenario(args.scenario, fields=args.fields, analogs=args.analogs)
    if args.source_url:
        q = q[q.field == "launch_date"]
    if not args.redo:
        q = q[q.status == "todo"]
    if args.limit:
        q = q[q.analog_id.isin(q.analog_id.drop_duplicates().head(args.limit))]
    if q.empty:
        print("Nothing to read (every item asked for is approved or waiting for review; --redo reads those too).",
              file=out)
        return [], []

    llm = llm or llm_mod.get_llm()
    dry = args.dry_run or llm.name == "fake"
    tables = io.load_tables(cfg["paths"]["processed"], ["analogs", "analog_features"])
    evidence = io.load_evidence(cfg["paths"]["reference"])
    analogs = analogs_for(q.analog_id.unique(), tables,
                          io.load_approved_evidence(cfg["paths"]["reference"]),
                          q.drop_duplicates("analog_id").set_index("analog_id").orig_application)
    generic = None
    if "n_competitors_at_launch" in set(q.field):
        fda = fda or verify.DrugsFDA()
        generic = verify.GenericEntry(tables["analogs"], fda)
    rows, report = run(q, analogs, gate or default_gate(), llm, fda, args.source_url, existing_keys(evidence),
                       generic)

    if dry:
        report = [[a, f, "not written (dry run)" if o == "written" else o, why, d] for a, f, o, why, d in report]
    print(f"{len(q)} item(s) for {q.analog_id.nunique()} analog(s); model {llm.name}", file=out)
    for r in report:
        print("  " + "  ".join(str(x) for x in r if x != ""), file=out)
    if dry:
        why = "no GEMINI_API_KEY, so the model is FakeLLM" if llm.name == "fake" else "--dry-run"
        print(f"Nothing written ({why}).", file=out)
    elif rows:
        extract.append_rows(rows, evidence_path)
        print(f"Appended {len(rows)} row(s) to {evidence_path} (approved=false). Review them, then run "
              "`python -m pipeline.labels --check`.", file=out)
    print(f"Run report: {write_report(report)}", file=out)
    return rows, report


if __name__ == "__main__":
    main()
