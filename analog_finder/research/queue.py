"""The work queue: which (analog, field) label reads still need doing, in the order to do them.

An (analog, field) stays in the queue until analog_evidence.csv has an approved value for it. `status` says whether
an unapproved row is already waiting for review (`pending_review`) or nothing has been read yet (`todo`).
Order: tier 1 = the scenario's expected analogs, tier 2 = other usable analogs in the target's therapeutic area and route group,
tier 3 = the rest of the usable analogs.

Usage: python -m analog_finder.research.queue --scenario torevia [--analogs ID ...] [--fields F ...] [--todo-only]
                                              [--limit N]

Spec: analog_finder/docs/components/sources_queue.md
"""
import argparse
import sys

import pandas as pd

from analog_finder import io
from analog_finder.research.sources import load_sources
from pipeline.build import EVIDENCE_FIELDS
from pipeline.checks import usable

FIELDS = list(EVIDENCE_FIELDS)
COLUMNS = ["priority", "tier", "analog_id", "drug_name", "application_number", "orig_application", "field", "sources",
           "status"]
TABLES = ["analog_features", "candidate_pool", "indication_history"]
TIERS = {1: "expected analog", 2: "same area and route group", 3: "other usable"}


class QueueError(ValueError):
    """Unknown analog or field asked for."""


def _area(label):
    """'N NERVOUS SYSTEM' -> 'N'; '' for blank."""
    return str(label).strip().split()[0].upper()[:1] if isinstance(label, str) and label.strip() else ""


def orig_applications(tables):
    """analog_id -> the application of the analog's original (ORIG) approval, where its first-indication label is.

    From indication_history (kind == original, submission ORIG; earliest, then lowest number). 45 analogs list
    several applications in candidate_pool (later strengths or forms); this picks the one to read. Without
    indication_history, the first listed application (the lowest number, which is the original for every current
    analog)."""
    cp = tables["candidate_pool"].set_index("analog_id").application_number.astype(str)
    first = cp.str.split("; ").str[0]
    h = tables.get("indication_history")
    if h is None:
        return first
    o = h[(h.kind == "original") & (h.submission_type.astype(str).str.strip() == "ORIG")]
    o = o.sort_values(["analog_id", "approval_date", "application_number"]).drop_duplicates("analog_id")
    return o.set_index("analog_id").application_number.astype(str).reindex(cp.index).fillna(first)


def _approved(ev):
    return ev.approved.astype(str).str.strip().str.lower() == "true"


def build_queue(tables, evidence, target=None, expected=(), fields=None, analogs=None, sources=None):
    """Work-queue table (columns COLUMNS), sorted by priority, analog_id, then field (EVIDENCE_FIELDS order).

    tables: io.load_tables(names=TABLES) output (analog_features, candidate_pool, and indication_history for
    orig_application; without it, the first listed application). evidence: io.load_evidence() (every row).
    target: a finder Target (its `area` sets tier 2) or None. expected: analog_ids for tier 1.
    fields: subset of EVIDENCE_FIELDS (default all). analogs: limit to these analog_ids (any analog in
    analog_features, usable or not); default the usable analogs plus the expected ones (an expected analog the
    funnel drops is still read first: the team named it).
    """
    fields = list(fields or FIELDS)
    unknown = [f for f in fields if f not in EVIDENCE_FIELDS]
    if unknown:
        raise QueueError(f"unknown field(s) {unknown}; fields are {FIELDS}")
    feats = tables["analog_features"]
    if analogs:
        missing = sorted(set(analogs) - set(feats.analog_id))
        if missing:
            raise QueueError(f"analog(s) {missing} not in analog_features")
        pool = feats[feats.analog_id.isin(analogs)]
    expected = set(expected or ())
    if not analogs:
        unknown_expected = sorted(expected - set(feats.analog_id))
        if unknown_expected:
            raise QueueError(f"expected analog(s) {unknown_expected} not in analog_features")
        pool = feats[usable(feats) | feats.analog_id.isin(expected)]
    area = getattr(target, "area", "") or ""
    route = getattr(target, "route_group", "") or ""

    def tier(row):
        if row.analog_id in expected:
            return 1
        # tier 2 = analogs the finder could pick for this target: same area and route group (filters.py)
        if area and _area(row.therapeutic_area) == area and (not route or row.route_group == route):
            return 2
        return 3

    cp = tables["candidate_pool"].set_index("analog_id")
    orig = orig_applications(tables)
    srcs = list(sources if sources is not None else load_sources())

    def source_names(analog_id, field):
        return "; ".join(s.name for s in srcs if field in s.used_for and (not s.analogs or analog_id in s.analogs))

    ev = evidence[evidence.field.isin(fields)]
    done = set(zip(ev.analog_id[_approved(ev)], ev.field[_approved(ev)]))
    waiting = set(zip(ev.analog_id[~_approved(ev)], ev.field[~_approved(ev)]))

    rows = []
    for r in pool.itertuples(index=False):
        t = tier(r)
        for f in fields:
            if (r.analog_id, f) in done:
                continue
            rows.append({"priority": t, "tier": TIERS[t], "analog_id": r.analog_id,
                         "drug_name": cp.brand_name.get(r.analog_id, ""),
                         "application_number": str(cp.application_number.get(r.analog_id, "") or ""),
                         "orig_application": str(orig.get(r.analog_id, "") or ""),
                         "field": f, "sources": source_names(r.analog_id, f),
                         "status": "pending_review" if (r.analog_id, f) in waiting else "todo"})
    q = pd.DataFrame(rows, columns=COLUMNS)
    if q.empty:
        return q
    q["_f"] = q.field.map({f: i for i, f in enumerate(FIELDS)})
    return q.sort_values(["priority", "analog_id", "_f"]).drop(columns="_f").reset_index(drop=True)


def for_scenario(scenario, tables=None, evidence=None, **kwargs):
    """build_queue with the scenario's target and `expected_analogs`."""
    from analog_finder.finder.target import load_target
    cfg = io.load_config(scenario)
    tables = tables if tables is not None else io.load_tables(cfg["paths"]["processed"], TABLES)
    evidence = evidence if evidence is not None else io.load_evidence(cfg["paths"]["reference"])
    spec = io.load_scenario(scenario)
    return build_queue(tables, evidence, load_target(scenario), spec.get("expected_analogs") or (), **kwargs)


def print_queue(q, out=sys.stdout, limit=None):
    if q.empty:
        print("Nothing to read: every (analog, field) asked for has an approved value.", file=out)
        return
    counts = q.groupby(["priority", "tier", "status"]).size().unstack(fill_value=0)
    n = q.analog_id.nunique()
    print(f"{len(q)} label read{'s' * (len(q) != 1)} for {n} analog{'s' * (n != 1)}", file=out)
    for (p, tier), r in counts.iterrows():
        parts = ", ".join(f"{n} {s.replace('_', ' ')}" for s, n in r.items() if n)
        k = q[q.priority == p].analog_id.nunique()
        print(f"  tier {p} ({tier}): {k} analog{'s' * (k != 1)}; {parts}", file=out)
    shown = q if limit is None else q.head(limit)
    print(file=out)
    print(shown[["priority", "analog_id", "drug_name", "orig_application", "field", "status"]].to_string(
        index=False), file=out)
    if limit is not None and len(q) > limit:
        print(f"... {len(q) - limit} more (--limit)", file=out)


def main(argv=None, out=sys.stdout):
    ap = argparse.ArgumentParser(prog="python -m analog_finder.research.queue", description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", default="torevia", help="sets tiers 1 and 2 (default torevia); 'none' for no tiers")
    ap.add_argument("--analogs", nargs="+", metavar="ANALOG_ID")
    ap.add_argument("--fields", nargs="+", choices=FIELDS)
    ap.add_argument("--todo-only", action="store_true", help="leave out reads already waiting for review")
    ap.add_argument("--limit", type=int, default=40, help="rows to print (default 40; 0 = all)")
    args = ap.parse_args(argv)
    if args.scenario.lower() == "none":
        cfg = io.load_config()
        q = build_queue(io.load_tables(cfg["paths"]["processed"], TABLES),
                        io.load_evidence(cfg["paths"]["reference"]), fields=args.fields, analogs=args.analogs)
    else:
        q = for_scenario(args.scenario, fields=args.fields, analogs=args.analogs)
    if args.todo_only:
        q = q[q.status == "todo"].reset_index(drop=True)
    print_queue(q, out, None if args.limit == 0 else args.limit)
    return q


if __name__ == "__main__":
    main()
