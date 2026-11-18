"""Hard filters and holdout: from the 426 analogs to the usable ones in the target's route group (D1, D2).

"Usable" is the checks.md funnel (pipeline.checks.usable: launch quarter, no late launch, no generic / biosimilar in
Q0-Q12, enough data), so the finder and the validation report share one definition. Label expansion, multi-route,
low volume, an unconfirmed peak and a weak Bass fit are warnings carried on each candidate, not filters.

A holdout (evaluation, user journey step 2) is removed before anything else, so it can't shape any later step.

Spec: analog_finder/docs/components/filters.md
"""
import warnings

import pandas as pd

from pipeline.checks import usable

FLAGS = ["warn_label_expansion", "warn_multi_route", "low_volume", "peak_not_confirmed", "weak_bass_fit"]
COLUMNS = ["analog_id", "drug_name", "atc4", "atc3", "area", "atc4_name", "atc3_name", "area_name", "route_group",
           "dosage_form", "indication_text"] + FLAGS


class FilterError(ValueError):
    """The filters can't produce a candidate table (unknown holdout, nothing left)."""


def codes(label):
    """'G03AA Progestogens ...; G03CA Natural ...' -> 'G03AA; G03CA'. Blank stays blank."""
    if not isinstance(label, str) or not label.strip():
        return ""
    return "; ".join(part.strip().split()[0] for part in label.split(";") if part.strip())


def _bool(series):
    return series.astype("boolean").fillna(False).astype(bool)


def candidates(tables, target, filters=None, holdout=None, top_k=5):
    """Candidate table: one row per analog that passes the hard filters, sorted by analog_id.

    tables: io.load_tables() output (analog_features, candidate_pool, analogs, bass_fits are read).
    filters: config["filters"] ({usable_only, match_route_group}); both default to true.
    holdout: an analog_id (or list of them) removed before filtering.
    Warns when fewer than 2 x top_k candidates are left (top 5 plus replacements); raises when none are.
    """
    filters = {"usable_only": True, "match_route_group": True, **(filters or {})}
    f = tables["analog_features"].copy()
    held = [holdout] if isinstance(holdout, str) else list(holdout or [])
    unknown = sorted(set(held) - set(f.analog_id))
    if unknown:
        raise FilterError(f"holdout analog(s) {unknown} not in analog_features")
    f = f[~f.analog_id.isin(held)]

    keep = pd.Series(True, index=f.index)
    if filters["usable_only"]:
        keep &= usable(f)
    if filters["match_route_group"]:
        keep &= f.route_group == target.route_group
    f = f[keep]
    if f.empty:
        raise FilterError(f"no analogs pass the filters for route group '{target.route_group}'")

    pool = tables["candidate_pool"].set_index("analog_id")
    analogs = tables["analogs"].set_index("analog_id")
    fits = tables["bass_fits"].set_index("analog_id")
    ids = f.analog_id
    out = pd.DataFrame({
        "analog_id": ids.values,
        "drug_name": ids.map(pool["brand_name"]).values,
        "atc4": f.class_narrow.map(codes).values,
        "atc3": f.class_broad.map(codes).values,
        "area": f.therapeutic_area.map(codes).values,
        "atc4_name": f.class_narrow.fillna("").values,
        "atc3_name": f.class_broad.fillna("").values,
        "area_name": f.therapeutic_area.fillna("").values,
        "route_group": f.route_group.values,
        "dosage_form": ids.map(analogs["dosage form"]).fillna("").values,
        "indication_text": ids.map(analogs["indication"]).fillna("").values,
        "warn_label_expansion": _bool(f.label_expansion_in_window).values,
        "warn_multi_route": _bool(f.multi_route).values,
        "low_volume": _bool(f.low_volume).values,
        "peak_not_confirmed": ~_bool(f.peak_confirmed).values,
        # no fit (not enough data, or the fit didn't converge) counts as weak
        "weak_bass_fit": ids.map(fits["weak_fit_flag"]).astype("boolean").fillna(True).astype(bool).values,
    })
    if len(out) < 2 * top_k:
        warnings.warn(f"only {len(out)} candidates pass the filters (fewer than {2 * top_k}: top {top_k} plus "
                      "replacements); rejections may run out", stacklevel=2)
    return out.sort_values("analog_id").reset_index(drop=True)[COLUMNS]
