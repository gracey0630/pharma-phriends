"""bass_fits: Bass p and q per analog, fitted to its launch curve.

Convention (decision 2026-10-22): share_of_peak is treated as the share of eventual adopters reached, and fitted
with the cumulative Bass curve m * F(t), t = quarters since launch + 1 (end of quarter):
    F(t) = (1 - exp(-(p + q) t)) / (1 + (q / p) exp(-(p + q) t))
Strictly, Bass models new adopters and TRx counts everyone on therapy; state this wherever the fits are shown.
m (share of the Q0-Q20 peak at saturation) is fitted too, so curves still climbing at Q20 can end above 1.

Fitted for analogs with enough_data, on non-provisional, non-blank quarters. weak_fit_flag: R^2 < WEAK_R2
(often curves that rise and fall, e.g. HCV cures) or a parameter on an arbitrary bound (see on_bound; often
curves still climbing at Q20, where m is unidentified). dropped is for the step-4 review (always False here).

Output: data/processed/bass_fits.csv, one row per fitted analog: analog_id, p, q, m, n_points, fit_quality (R^2),
        weak_fit_flag, dropped
"""
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

BOUNDS = ([1e-4, 0.0, 0.5], [0.5, 2.0, 5.0])  # p, q, m
STARTS = [(0.01, 0.1), (0.01, 0.5), (0.05, 0.3), (0.1, 0.1)]
WEAK_R2 = 0.9


def bass_cdf(t, p, q, m):
    e = np.exp(-(p + q) * t)
    return m * (1 - e) / (1 + (q / p) * e)


def fit(t, y):
    """Best (p, q, m, r2) over a few starting points, or None if no start converges."""
    best = None
    for p0, q0 in STARTS:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                params, _ = curve_fit(bass_cdf, t, y, p0=(p0, q0, 1.0), bounds=BOUNDS, maxfev=10000)
        except RuntimeError:
            continue
        resid = y - bass_cdf(t, *params)
        r2 = 1 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum()
        if best is None or r2 > best[3]:
            best = (*params, r2)
    return best


def on_bound(params):
    """p or q at its cap, or m at either limit. p and q at their lower limits (~0) are real values (no
    innovation / no imitation effect), not a sign the fit is unidentified."""
    p, q, m = params
    (_, _, m_lo), (p_hi, q_hi, m_hi) = BOUNDS
    return any(np.isclose(v, hi, rtol=0.01) for v, hi in [(p, p_hi), (q, q_hi), (m, m_hi)]) or np.isclose(m, m_lo, rtol=0.01)


def build(curves, features):
    ok = set(features.loc[features.enough_data, "analog_id"])
    pts = curves[curves.analog_id.isin(ok) & ~curves.provisional & curves.share_of_peak.notna()]
    rows = []
    for a, c in pts.groupby("analog_id"):
        t = c.q_since_launch.to_numpy(float) + 1
        y = c.share_of_peak.to_numpy(float)
        res = fit(t, y)
        if res is None:
            rows.append({"analog_id": a, "n_points": len(c), "weak_fit_flag": True, "dropped": False})
            continue
        p, q, m, r2 = res
        rows.append({"analog_id": a, "p": round(p, 5), "q": round(q, 4), "m": round(m, 3), "n_points": len(c),
                     "fit_quality": round(r2, 4), "weak_fit_flag": bool(r2 < WEAK_R2 or on_bound((p, q, m))),
                     "dropped": False})
    cols = ["analog_id", "p", "q", "m", "n_points", "fit_quality", "weak_fit_flag", "dropped"]
    return pd.DataFrame(rows, columns=cols)
