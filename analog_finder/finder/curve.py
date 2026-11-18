"""Weights and the uptake curve: turn the confirmed analogs into one similarity-weighted trajectory (D5).

Weights: each confirmed analog's similarity, normalized so they sum to 1. The forecaster may fix an analog's weight
with a reason (scenario YAML `weight_overrides: {analog_id: {weight, reason}}`); the other analogs share what's left
in proportion to their similarity, so the total stays 1.

Curve: share_of_peak by quarter since launch, Q0-Q20, from launch_curves, provisional quarters dropped. Each quarter
averages the analogs that have data that quarter, their weights renormalized among them (a recent launch such as
Lybalvi stops before Q20), and records n_analogs. The band is the plain min-max of those analogs. n_upper_bound counts
the analogs whose peak isn't confirmed, whose share of peak is an upper bound ("<= X").

Spec: analog_finder/docs/components/curve.md
"""
import warnings

import numpy as np
import pandas as pd

QUARTERS = range(0, 21)  # Q0-Q20, the Bass fit window
WEIGHT_COLUMNS = ["analog_id", "similarity", "weight", "override_weight", "override_reason"]
CURVE_COLUMNS = ["quarter", "weighted_share_of_peak", "band_min", "band_max", "n_analogs", "n_upper_bound"]
BASS_COLUMNS = ["analog_id", "drug_name", "weight", "p", "q", "m", "fit_quality", "weak_fit_flag", "low_volume"]
CAVEATS = [
    "Illustrative: a similarity-weighted average of a few analogs, not a forecast.",
    "Medicaid only (SDUD): curves may differ from commercial or Medicare uptake.",
    "Share of peak is against each analog's Q0-Q28 peak; for analogs without the full window it is an upper bound.",
    "Bass p and q are fitted to TRx share of peak (everyone on therapy), not new adopters.",
    "Suppressed SDUD rows are imputed at 5 Rx and quarters with no row count as 0 (not confirmed with CMS).",
]


class CurveError(ValueError):
    """Bad weight overrides, or nothing to build a curve from."""


def weights(confirmed, scores, overrides=None):
    """analog_weights table for the confirmed analogs (in the order given).

    overrides: {analog_id: {"weight": 0-1, "reason": text}}. An override for an analog that isn't confirmed is
    ignored with a warning (the confirmed set changes from run to run, e.g. with a holdout)."""
    if not confirmed:
        raise CurveError("no confirmed analogs")
    sim = scores.set_index("analog_id").similarity.reindex(confirmed).astype(float)
    if sim.isna().any():
        raise CurveError(f"confirmed analogs without a score: {list(sim.index[sim.isna()])}")
    overrides = dict(overrides or {})
    for a in sorted(set(overrides) - set(confirmed)):
        warnings.warn(f"weight override for {a} ignored: not a confirmed analog", stacklevel=2)
        overrides.pop(a)
    fixed = {}
    for a, o in overrides.items():
        o = o or {}
        w, reason = o.get("weight"), str(o.get("reason") or "").strip()
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not 0 <= w <= 1:
            raise CurveError(f"weight override for {a}: weight must be a number from 0 to 1, got {w!r}")
        if not reason:
            raise CurveError(f"weight override for {a}: a reason is required")
        fixed[a] = (float(w), reason)
    total_fixed = sum(w for w, _ in fixed.values())
    free = [a for a in confirmed if a not in fixed]
    if total_fixed > 1 + 1e-9 or (not free and abs(total_fixed - 1) > 1e-6):
        raise CurveError(f"weight overrides sum to {total_fixed:g}; they must total 1 when every analog is "
                         "overridden, and at most 1 otherwise")
    out = pd.DataFrame({"analog_id": confirmed, "similarity": sim.values})
    free_sim = sim[free].sum()
    rest = 1 - total_fixed
    out["weight"] = [fixed[a][0] if a in fixed else (rest * sim[a] / free_sim if free_sim > 0 else rest / len(free))
                     for a in confirmed]
    out["override_weight"] = [fixed[a][0] if a in fixed else np.nan for a in confirmed]
    out["override_reason"] = [fixed[a][1] if a in fixed else "" for a in confirmed]
    out["weight"] = out.weight.round(6)
    return out[WEIGHT_COLUMNS]


def uptake_curve(weight_table, launch_curves, upper_bound=()):
    """uptake_curve table, Q0-Q20. upper_bound: analog_ids whose peak isn't confirmed."""
    w = weight_table.set_index("analog_id").weight
    lc = launch_curves[launch_curves.analog_id.isin(w.index) & ~launch_curves.provisional.astype(bool)
                       & launch_curves.q_since_launch.isin(QUARTERS) & launch_curves.share_of_peak.notna()]
    rows = []
    for q in QUARTERS:
        d = lc[lc.q_since_launch == q]
        ww = d.analog_id.map(w).to_numpy(float)
        y = d.share_of_peak.to_numpy(float)
        if len(d) == 0:
            rows.append({"quarter": q, "n_analogs": 0, "n_upper_bound": 0})
            continue
        rows.append({"quarter": q,
                     "weighted_share_of_peak": round(float((ww * y).sum() / ww.sum()), 4) if ww.sum() > 0 else np.nan,
                     "band_min": round(float(y.min()), 4), "band_max": round(float(y.max()), 4),
                     "n_analogs": len(d), "n_upper_bound": int(d.analog_id.isin(set(upper_bound)).sum())})
    return pd.DataFrame(rows).reindex(columns=CURVE_COLUMNS).astype({"n_analogs": int, "n_upper_bound": int})


def bass_table(weight_table, bass_fits, candidates):
    """The confirmed analogs' Bass fits (bass_fits.csv), shown next to the curve; blank where there's no fit."""
    t = weight_table[["analog_id", "weight"]].merge(bass_fits, on="analog_id", how="left")
    t["drug_name"] = t.analog_id.map(candidates.set_index("analog_id").drug_name)
    return t.reindex(columns=BASS_COLUMNS)
