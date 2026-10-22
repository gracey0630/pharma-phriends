"""analog_features: one row per analog_id, the input to the analog agent's hard filters and similarity score.

Only columns code can fill today. Match fields from label reads (line of therapy, dosing, competitors) are
copied only once approved in analog_evidence.csv; rems and limited_distribution wait on label reads (blank).

Rules (docs/data_model.md; decisions 2026-10-22):
  - enough_data: >= 12 complete (non-provisional) quarters since launch and no blank quarter after Q2 in Q0-Q20
  - "in window" for distortion flags = Q0-Q12 (the first 3 years)
  - label_expansion_in_window counts every EFFICACY supplement, so it over-flags (see indication_history)
  - enrollment_shock_in_window names the shocks (medicaid_enrollment.SHOCKS) overlapping Q0-Q12

Output: data/processed/analog_features.csv
"""
import pandas as pd

from pipeline.common import date_qnum, qnum
from pipeline.enrollment import SHOCKS

ENOUGH_QUARTERS = 12
FLAG_WINDOW = 12  # Q0-Q12
LATE_LAUNCH = 4  # quarters from approval to launch; more = route added later or delayed launch
EVIDENCE_MATCH = ["line_of_therapy", "dosing_frequency", "n_competitors_at_launch"]


def build(pool, analogs, ndc_map, quarterly, curves, launch, history, evidence, class_broad, area):
    a = analogs.set_index("analog_id")
    p = pool.set_index("analog_id")
    out = pd.DataFrame(index=pool.analog_id)
    out["route_group"] = p.route_group
    out["therapeutic_area"] = a["class (narrow)"].map(area)
    out["class_broad"] = a["class (narrow)"].map(class_broad)
    out["class_narrow"] = a["class (narrow)"]

    ev = evidence.copy()
    ev["approved"] = ev.approved.str.lower() == "true"
    approved = ev[ev.approved].drop_duplicates(["analog_id", "field"], keep="last")
    approved = approved.pivot(index="analog_id", columns="field", values="value")
    for f in EVIDENCE_MATCH:
        out[f] = out.index.map(approved[f]) if f in approved else ""

    out["launch_quarter"] = launch.launch_quarter
    out["launch_source"] = launch.launch_source
    lq = out.launch_quarter.dropna().map(qnum)
    out["quarters_approval_to_launch"] = (lq - p.approval_date.map(date_qnum)).astype("Int64")

    latest_final = max(qnum(x) for x in curves.loc[~curves.provisional, "period"])
    out["quarters_of_data"] = (latest_final - lq + 1).clip(lower=0).astype("Int64")
    final = curves[~curves.provisional]
    g = final.groupby("analog_id")
    out["peak_trx"] = g.trx.max()
    # first quarter that reaches the peak, so ties (Iclusig, Lonsurf) resolve the same way every run
    out["peak_q"] = final.loc[final.trx.notna()].sort_values(["analog_id", "q_since_launch"]).set_index(
        "q_since_launch").groupby("analog_id").trx.idxmax()
    last_q = out.index.map(g.q_since_launch.max())
    out["peak_at_last_quarter"] = (out.peak_q == last_q).fillna(False).astype(bool)
    out["suppressed_quarters"] = g.suppressed_rows.apply(lambda s: int((s > 0).sum()))
    out["blank_quarters_after_q2"] = final[final.q_since_launch > 2].groupby("analog_id").trx.apply(
        lambda s: int(s.isna().sum()))
    out["provisional_quarters"] = curves[curves.provisional].groupby("analog_id").size()
    out["ndc_match_issues"] = ndc_map[ndc_map.match_method != "application_number"].groupby("analog_id").size()
    out["fields_not_approved"] = ev[~ev.approved].groupby("analog_id").size()
    for c in ["peak_trx", "peak_q", "suppressed_quarters", "blank_quarters_after_q2"]:
        out[c] = out[c].astype("Int64")
    for c in ["provisional_quarters", "ndc_match_issues", "fields_not_approved"]:
        out[c] = out[c].fillna(0).astype(int)

    exp = history[(history.kind != "original") & history.q_since_launch.between(0, FLAG_WINDOW)]
    out["label_expansion_in_window"] = out.index.isin(exp.analog_id)
    gen = a["generic / exclusivity date"]
    out["generic_entry_in_window"] = [bool(gen[i]) and i in lq.index and qnum(gen[i]) - lq[i] <= FLAG_WINDOW
                                      for i in out.index]
    out["enrollment_shock_in_window"] = [
        "; ".join(name for name, first, last in SHOCKS
                  if i in lq.index and qnum(first) <= lq[i] + FLAG_WINDOW and qnum(last) >= lq[i])
        for i in out.index]
    out["late_launch"] = (out.quarters_approval_to_launch > LATE_LAUNCH).fillna(False).astype(bool)
    out["multi_route"] = p.n_route_groups.astype(int) > 1
    out["rems"] = ""
    out["limited_distribution"] = ""
    out["enough_data"] = ((out.quarters_of_data >= ENOUGH_QUARTERS) & (out.blank_quarters_after_q2 == 0)).fillna(False)
    return out.reset_index()
