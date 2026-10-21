"""Validation report for the analog table (docs/data_model.md, "Validation checks").

Nothing here changes the data: it lists rows to look at. Written to data/processed/checks.md by pipeline.build.
"""
import pandas as pd

from pipeline.common import RAW

ENOUGH_QUARTERS = 12  # rule: >= 12 quarters of SDUD TRx after launch


def _q(period):
    """'2019Q2' -> 2019*4 + 1, so quarters can be subtracted."""
    return int(period[:4]) * 4 + int(period[-1]) - 1


def _date_q(iso):
    return int(iso[:4]) * 4 + (int(iso[5:7]) - 1) // 3


def _section(lines, title, ids, note=""):
    lines.append(f"\n### {title} ({len(ids)})")
    if note:
        lines.append(note)
    if len(ids):
        lines.append(", ".join(f"`{i}`" for i in sorted(ids)))


def run(analogs, ndc_map, quarterly, evidence):
    a = analogs.set_index("analog_id")
    trx = quarterly[quarterly.metric == "trx"].copy()
    trx["value"] = pd.to_numeric(trx.value, errors="coerce")
    first_rx = trx[trx.value > 0].groupby("analog_id").period.min()
    n_quarters = trx.groupby("analog_id").period.nunique()

    lines = ["# Validation report", "",
             f"{len(a)} analogs: {a['route of administration'].value_counts().to_dict()}. "
             f"{a['Rx'].ne('').sum()} have Medicaid Rx; {ndc_map.ndc9.nunique()} NDCs mapped."]

    lines.append("\n## Source freshness (data/raw/*/manifest.csv)")
    lines.append("Re-download FDA and CMS files right before any final build (`python -m pipeline.build --refresh`).\n")
    lines.append("| Source | Files | Last pulled |")
    lines.append("|---|---|---|")
    for m in sorted(RAW.glob("*/manifest.csv")):
        df = pd.read_csv(m, dtype=str)
        lines.append(f"| {m.parent.name} | {df.iloc[:, 1].nunique()} | {df.pulled_at.max()[:10]} |")

    lines.append("\n## Rows to look at")
    _section(lines, "No Medicaid Rx at all", a.index[a["Rx"] == ""],
             "No SDUD rows for any mapped NDC: often clinic-administered SC products, very recent launches, or NDCs missing from ndc_map.")
    approval = a["approval date"]
    start = a["start marketing date"]
    _section(lines, "Start marketing date before approval date", a.index[start < approval],
             "Usually an NDC listed shortly before approval; check if more than a few months early.")
    late = [i for i in a.index if _date_q(start[i]) - _date_q(approval[i]) > 4]
    _section(lines, "Start marketing date > 1 year after approval", late,
             "Route added later (e.g. an oral form of an injectable), or a delayed launch. Not a first-indication launch curve.")
    short = [i for i in a.index if i in first_rx and n_quarters.get(i, 0) < ENOUGH_QUARTERS]
    _section(lines, f"Fewer than {ENOUGH_QUARTERS} quarters of SDUD data", short, "Fails the 'enough data' rule for analogs.")
    blank = trx[trx.value.isna()].merge(first_rx.rename("first"), left_on="analog_id", right_index=True)
    blank = blank[blank.period.map(_q) - blank["first"].map(_q) >= 2]
    _section(lines, "Suppressed (blank) Rx quarters after launch quarter Q2", blank.analog_id.unique(),
             "Values stay blank, never 0. Fails the 'no suppressed quarters after Q2' rule.")
    gen = a["generic / exclusivity date"]
    early = [i for i in a.index if gen[i] and i in first_rx and _q(gen[i]) - _q(first_rx[i]) < 12]
    _section(lines, "Generic / biosimilar dispensed within 3 years of first Rx", early, "Out of scope (no generic entry in the first 3 years).")
    _section(lines, "No ATC class (narrow)", a.index[a["class (narrow)"] == ""], "RxClass has no ATC code yet (often recent approvals); fill by hand.")
    multi = a.groupby(a["brand name"]).filter(lambda g: len(g) > 1).index
    _section(lines, "Brands with two route groups", multi, "Each route group is its own analog; check which one launched first.")

    lines.append("\n## NDC matching")
    lines += [f"- {k}: {v}" for k, v in ndc_map.match_method.value_counts().items()]

    lines.append("\n## Label-read values (data/reference/analog_evidence.csv)")
    if evidence.empty:
        lines.append("None yet.")
    else:
        e = evidence.copy()
        e["approved"] = e.approved.str.lower() == "true"
        lines.append(f"{len(e)} values for {e.analog_id.nunique()} analogs; {e.approved.sum()} approved, "
                     f"{(~e.approved).sum()} waiting for review.")
        _section(lines, "Analogs with unapproved values", e[~e.approved].analog_id.unique())
        launch = e[e.field == "launch_date"].set_index("analog_id").value
        off = [i for i, d in launch.items() if i in first_rx and abs(_date_q(d) - _q(first_rx[i])) > 1]
        _section(lines, "Launch date vs first SDUD Rx quarter differ by > 1 quarter", off)
    return "\n".join(lines) + "\n"

