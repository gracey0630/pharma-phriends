"""Validation report for the analog table (docs/data_model.md, "Validation checks").

Nothing here changes the data: it lists rows to look at. Written to data/processed/checks.md by pipeline.build.
"""
import pandas as pd

from pipeline.common import RAW
from pipeline.features import ENOUGH_QUARTERS, LOW_VOLUME, MAX_IMPUTED_SHARE
from pipeline.sdud import HIDDEN_HIGH, HIDDEN_LOW, HIDDEN_MID


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


def funnel(lines, features, fits):
    """How many analogs are left after each rule code can apply today, in order."""
    f = features
    steps = [
        ("All analogs (NME / new BLA, approved 2010+, oral or sc)", pd.Series(True, index=f.index)),
        ("Has a launch quarter (any SDUD row)", f.launch_quarter.notna()),
        ("Launch within 1 year of approval (not `late_launch`)", ~f.late_launch.fillna(False).astype(bool)),
        ("No generic / biosimilar in Q0-Q12", ~f.generic_entry_in_window.astype(bool)),
        (f"Enough data (>= {ENOUGH_QUARTERS} quarters, <= {MAX_IMPUTED_SHARE:.0%} of Q3-Q20 TRx imputed)",
         f.enough_data.astype(bool)),
    ]
    lines.append("\n## Pool after each rule")
    lines.append("Applied in order. Not applied here (flags only): `low_volume`, `multi_route` (counts IV forms added "
                 "later), `label_expansion_in_window` (counts every efficacy supplement), `enrollment_shock_in_window`, "
                 "and clinic-administered SC products (no flag yet).\n")
    lines.append("| Rule | Analogs left | oral | sc |")
    lines.append("|---|---|---|---|")
    keep = pd.Series(True, index=f.index)
    for name, rule in steps:
        keep &= rule
        left = f[keep]
        lines.append(f"| {name} | {len(left)} | {(left.route_group == 'oral').sum()} | {(left.route_group == 'sc').sum()} |")
    left = f[keep]
    lines.append(f"\nOf those {len(left)}: {left.low_volume.sum()} `low_volume` (peak < {LOW_VOLUME} TRx a quarter), "
                 f"{left.multi_route.sum()} `multi_route`, "
                 f"{left.label_expansion_in_window.sum()} `label_expansion_in_window`, "
                 f"{(left.enrollment_shock_in_window != '').sum()} with an enrollment shock in Q0-Q12.")
    lines.append(f"\nLaunch quarter source: {f.launch_source.value_counts().to_dict()}.")
    _section(lines, "Peak at the last quarter of data (still climbing)", left.analog_id[left.peak_at_last_quarter],
             "Among analogs with enough data. Their share_of_peak ends at 1.0 and the fitted m is above 1.")
    weak = fits[fits.weak_fit_flag]
    _section(lines, "Weak Bass fits", weak.analog_id,
             f"R^2 < 0.9 or a parameter on its bound; {len(fits)} analogs fitted, "
             f"{(weak.low_volume).sum()} of the weak fits are `low_volume`.")
    _section(lines, "Low Medicaid volume", left.analog_id[left.low_volume],
             f"Among analogs with enough data: peak < {LOW_VOLUME} TRx a quarter (mid estimate). Counting noise alone "
             "gives weak Bass fits at this size, so show the flag next to the fit.")


def not_in_pool_section(lines, not_in_pool):
    """NME brands (2010+) left out of the pool, by reason, so nothing drops out silently."""
    lines.append("\n## NME brands not in the pool")
    lines.append(f"{len(not_in_pool)} brands from the NME compilation (2010+) have no oral or sc route group.\n")
    lines.append("| Reason | Brands |")
    lines.append("|---|---|")
    for reason, g in not_in_pool.groupby("reason"):
        lines.append(f"| {reason} | {len(g)} |")
    other = not_in_pool[not_in_pool.reason == "other route"].route_groups.str.split(" | ", regex=False).explode()
    lines.append("\nOther routes: " + ", ".join(f"{r} {n}" for r, n in other.value_counts().items()) + ".")
    _section(lines, "Injection, route not stated", not_in_pool.brand_key[not_in_pool.reason == "injection, route not stated"],
             "Drugs@FDA lists them only as 'INJECTABLE;INJECTION' (sc, IV or IM?). The original label states the "
             "route; not resolved yet, so they're out of the pool.")
    _section(lines, "No route found", not_in_pool.brand_key[not_in_pool.reason == "no route found"],
             "Neither the NDC Directory nor Drugs@FDA Products gives a route.")
    _section(lines, "No NDC listings", not_in_pool.brand_key[not_in_pool.reason == "no NDC listings"])


def run(analogs, ndc_map, quarterly, evidence, features, fits, not_in_pool):
    a = analogs.set_index("analog_id")
    trx = quarterly[quarterly.metric == "trx"].copy()
    trx["value"] = pd.to_numeric(trx.value, errors="coerce")
    # first quarter with any SDUD row: a suppressed (blank) quarter still means 1-10 Rx were dispensed
    first_rx = trx.groupby("analog_id").period.min()
    n_quarters = trx.groupby("analog_id").period.nunique()
    rep = quarterly[quarterly.metric == "trx_reported"].copy()
    has_reported = pd.to_numeric(rep.value, errors="coerce").notna().groupby(rep.analog_id).any()
    hidden_only = has_reported.index[~has_reported]

    lines = ["# Validation report", "",
             f"{len(a)} analogs: {a['route of administration'].value_counts().to_dict()}. "
             f"{a['Rx'].ne('').sum()} have Medicaid Rx ({len(hidden_only)} of them only in suppressed rows); "
             f"{ndc_map.ndc9.nunique()} NDCs mapped.",
             f"\nTRx = reported rows + {HIDDEN_MID} per suppressed row (low {HIDDEN_LOW}, high {HIDDEN_HIGH}; "
             f"`trx_low` / `trx_high`). A quarter with no SDUD row is 0 TRx. Medicaid TRx to date: "
             f"{pd.to_numeric(trx.value).sum():,.0f}, of which "
             f"{pd.to_numeric(quarterly.loc[quarterly.metric == 'suppressed_rows', 'value']).sum() * HIDDEN_MID:,.0f} "
             "imputed."]

    lines.append("\n## Source freshness (data/raw/*/manifest.csv)")
    lines.append("Re-download FDA and CMS files right before any final build (`python -m pipeline.build --refresh`).\n")
    lines.append("| Source | Files | Last pulled |")
    lines.append("|---|---|---|")
    for m in sorted(RAW.glob("*/manifest.csv")):
        df = pd.read_csv(m, dtype=str)
        lines.append(f"| {m.parent.name} | {df.iloc[:, 1].nunique()} | {df.pulled_at.max()[:10]} |")

    funnel(lines, features, fits)
    not_in_pool_section(lines, not_in_pool)

    lines.append("\n## Rows to look at")
    _section(lines, "No Medicaid Rx at all", a.index[a["Rx"] == ""],
             "No SDUD rows for any mapped NDC: often clinic-administered SC products, very recent launches, or NDCs missing from ndc_map.")
    _section(lines, "Medicaid Rx only in suppressed rows", hidden_only,
             "Every SDUD row is suppressed (< 11 Rx), so all their TRx is imputed.")
    approval = a["approval date"]
    start = a["start marketing date"]
    _section(lines, "Start marketing date before approval date", a.index[start < approval],
             "Usually an NDC listed shortly before approval; check if more than a few months early.")
    late = [i for i in a.index if _date_q(start[i]) - _date_q(approval[i]) > 4]
    _section(lines, "Start marketing date > 1 year after approval", late,
             "Route added later (e.g. an oral form of an injectable), or a delayed launch. Not a first-indication launch curve.")
    short = [i for i in a.index if i in first_rx and n_quarters.get(i, 0) < ENOUGH_QUARTERS]
    _section(lines, f"Fewer than {ENOUGH_QUARTERS} quarters of SDUD data", short, "Fails the 'enough data' rule for analogs.")
    f = features.set_index("analog_id")
    long_enough = f.quarters_of_data >= ENOUGH_QUARTERS
    _section(lines, f"More than {MAX_IMPUTED_SHARE:.0%} of Q3-Q20 TRx imputed",
             f.index[long_enough & ~(f.imputed_share <= MAX_IMPUTED_SHARE)],
             "Fails the 'enough data' rule: the curve would be mostly imputed suppressed rows.")
    flips = (f.imputed_share_low <= MAX_IMPUTED_SHARE) != (f.imputed_share_high <= MAX_IMPUTED_SHARE)
    _section(lines, "Enough-data status depends on the imputation", f.index[long_enough & flips],
             f"Pass the {MAX_IMPUTED_SHARE:.0%} cap at {HIDDEN_LOW} Rx per suppressed row but not at {HIDDEN_HIGH}; "
             f"the rule uses {HIDDEN_MID}.")
    gen = a["generic / exclusivity date"]
    early = [i for i in a.index if gen[i] and i in first_rx and _q(gen[i]) - _q(first_rx[i]) < 12]
    _section(lines, "Generic / biosimilar dispensed within 3 years of first Rx", early, "Out of scope (no generic entry in the first 3 years).")
    _section(lines, "No ATC class (narrow)", a.index[a["class (narrow)"] == ""], "RxClass has no ATC code yet (often recent approvals); fill by hand.")
    _section(lines, "Several ATC classes (narrow)", a.index[a["class (narrow)"].str.contains("; ")],
             "Still more than one class after dropping combination-product and topical / eye classes (pipeline/rxclass.py). "
             "Analyses that need one class should check these.")
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

