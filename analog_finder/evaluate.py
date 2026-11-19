"""Evaluation harness: does the finder predict a held-out launch better than a "typical drug" guess? (plan step 8)

Leave one out: each usable analog with all of Q0-Q12 becomes the target, the finder picks 5 analogs from the rest of
its route group (filters -> embed -> score -> auto-confirm the top 5 -> weighted curve), and the error is the mean
absolute gap between the predicted and actual share of peak over Q0-Q12. Lower is better.

Methods: TF-IDF hybrid (scoring.yaml weights) and structured only (text weight 0).
Baselines (no matching), from the other usable analogs in the same route group: the all-analog median and the ATC 4
class median (at least 3 others in the class, else the all-analog median).

Usage: python -m analog_finder.evaluate [--analogs ID ...] [--out CSV] [--embedder tfidf]

Spec: analog_finder/docs/components/evaluate.md
"""
import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from analog_finder import io
from analog_finder.finder import curve, embed, filters, loop, rerank, score
from analog_finder.finder.target import Target
from pipeline.checks import usable

QUARTERS = list(range(0, 13))  # Q0-Q12, the first 3 years
MIN_CLASS = 3  # others in the ATC 4 class needed for a class median (as in the EDA)
METHODS = ["tfidf_hybrid", "structured_only"]
BASELINES = ["atc4_median", "all_analog_median"]
LABELS = {"tfidf_hybrid": "TF-IDF hybrid", "structured_only": "Structured only (ATC class)",
          "atc4_median": "ATC 4 median (baseline)", "all_analog_median": "All-analog median (baseline)"}
REFERENCE = "all_analog_median"
EDA_BASELINE = 0.18


# --- inputs -----------------------------------------------------------------------------------------------

def actual_curves(tables):
    """Share of peak, one row per usable analog, one column per quarter Q0-Q12 (NaN where provisional or missing)."""
    f = tables["analog_features"]
    ids = f.analog_id[usable(f)]
    lc = tables["launch_curves"]
    lc = lc[lc.analog_id.isin(ids) & ~lc.provisional.astype(bool) & lc.q_since_launch.isin(QUARTERS)]
    return lc.pivot(index="analog_id", columns="q_since_launch", values="share_of_peak").reindex(
        index=pd.Index(sorted(ids), name="analog_id"), columns=QUARTERS)


def held_out_ids(actual):
    """The analogs evaluated: usable, with a value in every quarter Q0-Q12."""
    return list(actual.index[actual.notna().all(axis=1)])


def _first(label):
    return filters.codes(label).split("; ")[0] if isinstance(label, str) else ""


def target_for(analog_id, tables):
    """A Target built from an analog's own data: indication text, first ATC 4 code (ATC 3 and area derived from it),
    route group, dosage form. No evidence. Built directly: the scenario check would reject an analog with no ATC."""
    f = tables["analog_features"].set_index("analog_id").loc[analog_id]
    a = tables["analogs"].set_index("analog_id").loc[analog_id]
    name = tables["candidate_pool"].set_index("analog_id").brand_name.get(analog_id, analog_id)
    atc4 = _first(f.class_narrow)
    atc3 = atc4[:4] if atc4 else _first(f.class_broad)
    area = atc4[:1] if atc4 else _first(f.therapeutic_area)[:1]
    text = lambda v: "" if pd.isna(v) else str(v).strip()  # noqa: E731
    return Target(name=text(name), indication_text=text(a["indication"]), atc4=atc4, atc3=atc3, area=area,
                  route_group=f.route_group, dosage_form=text(a["dosage form"]))


# --- predictions ------------------------------------------------------------------------------------------

def mean_abs_error(actual, predicted):
    """Mean absolute gap over the quarters both have (the EDA's measure)."""
    gap = np.abs(np.asarray(actual, float) - np.asarray(predicted, float))
    return float(np.nanmean(gap)) if np.isfinite(gap).any() else np.nan


def baselines(analog_id, actual, features):
    """{all_analog_median, atc4_median} predictions (Series over Q0-Q12) from the other usable analogs in the same
    route group, plus whether the ATC 4 median fell back to the all-analog median."""
    f = features.set_index("analog_id")
    route = f.route_group
    others = actual.index[(actual.index != analog_id) & (actual.index.map(route) == route[analog_id])]
    overall = actual.loc[others].median()
    atc4 = _first(f.class_narrow[analog_id])
    same = [a for a in others if atc4 and _first(f.class_narrow[a]) == atc4]
    fallback = len(same) < MIN_CLASS
    return {"all_analog_median": overall,
            "atc4_median": overall if fallback else actual.loc[same].median()}, fallback


def method_weights(weights):
    return {"tfidf_hybrid": dict(weights), "structured_only": {**weights, "text": 0.0}}


def finder_predictions(analog_id, tables, cfg, embedder_name):
    """{method: (prediction over Q0-Q12 or None, top 5 analog_ids)}. None when the method has nothing to rank on
    (structured only for a target with no ATC class)."""
    target = target_for(analog_id, tables)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # "fewer than 2 x top_k candidates" is expected for small pools
        cands = filters.candidates(tables, target, cfg["filters"], holdout=analog_id, top_k=cfg["top_k"])
    emb = embed.embed(cands, None, target, tables["analog_features"], embed.get_embedder(embedder_name, cfg),
                      use_evidence=False)
    out = {}
    for method, weights in method_weights(cfg["weights"]).items():
        s = rerank.rerank(score.score(cands, emb, None, target, weights, use_evidence=False), target, cands)
        queue = loop.CandidateQueue(s, "evaluate", top_k=cfg["top_k"])
        queue.auto_confirm()
        top = queue.confirmed
        if s.set_index("analog_id").similarity.reindex(top).isna().any():
            out[method] = (None, top)
            continue
        uc = curve.uptake_curve(curve.weights(top, s), tables["launch_curves"])
        out[method] = (uc.set_index("quarter").weighted_share_of_peak.reindex(QUARTERS), top)
    return out


# --- run ----------------------------------------------------------------------------------------------------

def run(tables, cfg, analogs=None, embedder_name=None, progress=None):
    """Per-analog errors: one row per held-out analog, an `error_<method>` column per method and baseline, plus
    `atc4_fallback`, `structured_fallback`, the two top-5 lists, `route_group` and `peak_confirmed`."""
    if cfg.get("use_evidence"):
        raise ValueError("use_evidence is on, but the evaluation builds targets without evidence (step 15 adds it)")
    actual = actual_curves(tables)
    ids = held_out_ids(actual)
    if analogs:
        unknown = sorted(set(analogs) - set(ids))
        if unknown:
            raise ValueError(f"not evaluated (not usable, or missing a quarter in Q0-Q12): {unknown}")
        ids = [a for a in ids if a in set(analogs)]
    name = embedder_name or cfg["embedder"]
    features = tables["analog_features"].set_index("analog_id")
    rows = []
    for i, a in enumerate(ids, 1):
        base, atc4_fallback = baselines(a, actual, tables["analog_features"])
        row = {"analog_id": a, "route_group": features.route_group[a],
               "peak_confirmed": bool(features.peak_confirmed[a]), "atc4_fallback": atc4_fallback}
        try:
            preds = finder_predictions(a, tables, cfg, name)
        except filters.FilterError as e:  # nothing else in its route group
            preds, row["skipped"] = {}, str(e)
        for method in METHODS:
            pred, top = preds.get(method, (None, []))
            if method == "structured_only":
                row["structured_fallback"] = pred is None and bool(preds)
                if row["structured_fallback"]:
                    pred = base[REFERENCE]  # no class to match on: the guess without matching
            row[f"error_{method}"] = mean_abs_error(actual.loc[a], pred) if pred is not None else np.nan
            row[f"top5_{method}"] = "; ".join(top)
        for b in BASELINES:
            row[f"error_{b}"] = mean_abs_error(actual.loc[a], base[b])
        rows.append(row)
        if progress:
            progress(i, len(ids))
    errors = pd.DataFrame(rows)
    if "skipped" not in errors:
        errors["skipped"] = ""
    errors["skipped"] = errors.skipped.fillna("")
    return errors


def _ci(values, rng, n_boot):
    idx = rng.integers(0, len(values), size=(n_boot, len(values)))
    return np.percentile(np.median(values[idx], axis=1), [2.5, 97.5])


def summarize(errors, n_boot=2000, seed=0):
    """One row per method and baseline, for all evaluated analogs and for those with a confirmed peak: median error
    (95% bootstrap interval), mean error, paired median difference from the all-analog median (95% interval; < 0 =
    better), share of analogs better than it, and fallbacks."""
    e = errors[errors.skipped == ""]
    rows = []
    for subset, d in [("all", e), ("peak confirmed", e[e.peak_confirmed])]:
        ref = d[f"error_{REFERENCE}"].to_numpy(float)
        for m in METHODS + BASELINES:
            v = d[f"error_{m}"].to_numpy(float)
            rng = np.random.default_rng(seed)
            lo, hi = _ci(v, rng, n_boot) if len(v) else (np.nan, np.nan)
            row = {"subset": subset, "method": LABELS[m], "analogs": len(v),
                   "median_error": np.median(v) if len(v) else np.nan, "ci_low": lo, "ci_high": hi,
                   "mean_error": v.mean() if len(v) else np.nan}
            if m != REFERENCE and len(v):
                diff = v - ref
                dlo, dhi = _ci(diff, np.random.default_rng(seed), n_boot)
                row.update(vs_all_analog=np.median(diff), vs_ci_low=dlo, vs_ci_high=dhi,
                           share_better=float((v < ref).mean()))
            row["fallbacks"] = int(d.atc4_fallback.sum()) if m == "atc4_median" else (
                int(d.structured_fallback.sum()) if m == "structured_only" else 0)
            rows.append(row)
    return pd.DataFrame(rows)


# --- CLI ----------------------------------------------------------------------------------------------------

def _fmt(x, nd=3):
    return "" if x != x else f"{x:.{nd}f}"


def print_summary(summary, errors, out=sys.stdout):
    skipped = errors[errors.skipped != ""]
    print(f"\nLeave-one-out over {len(errors) - len(skipped)} analogs, Q0-Q12 (error = mean gap in share of peak; "
          "lower is better)", file=out)
    for subset, d in summary.groupby("subset", sort=False):
        print(f"\n[{subset}: {d.analogs.iloc[0]} analogs]", file=out)
        print(f"  {'method':<30}{'median':>8}  {'95% interval':>13}{'mean':>8}  {'vs all-analog':>14}"
              f"  {'95% interval':>15}{'better':>8}{'fallback':>10}", file=out)
        for r in d.itertuples(index=False):
            vs = getattr(r, "vs_all_analog", np.nan)
            vs_ci = ("" if vs != vs else f"{r.vs_ci_low:+.3f} to {r.vs_ci_high:+.3f}")
            better = getattr(r, "share_better", np.nan)
            print(f"  {r.method:<30}{_fmt(r.median_error):>8}  {_fmt(r.ci_low)}-{_fmt(r.ci_high):<7}"
                  f"{_fmt(r.mean_error):>8}  {('' if vs != vs else f'{vs:+.3f}'):>14}  {vs_ci:>15}"
                  f"{('' if better != better else f'{better:.0%}'):>8}{(r.fallbacks or ''):>10}", file=out)
    base = summary[(summary.subset == "all") & (summary.method == LABELS[REFERENCE])].median_error.iloc[0]
    print(f"\nMeasuring-tool check: all-analog median {base:.3f} (EDA: {EDA_BASELINE}).", file=out)
    if len(skipped):
        print(f"Skipped {len(skipped)}: " + "; ".join(f"{r.analog_id} ({r.skipped})" for r in skipped.itertuples()),
              file=out)
    print("Matching on indication text and ATC class only (use_evidence off), so the hybrid score is understated "
          "until label reads (step 15). Medicaid (SDUD) only.", file=out)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="python -m analog_finder.evaluate", description=__doc__.splitlines()[0])
    ap.add_argument("--analogs", nargs="+", metavar="ANALOG_ID", help="evaluate only these analogs")
    ap.add_argument("--embedder", choices=["tfidf", "rxbert"], default=None,
                    help="text embedder (default: config/scoring.yaml)")
    ap.add_argument("--out", type=Path, default=None,
                    help="per-analog errors CSV (default: data/cache/evaluation/errors.csv)")
    ap.add_argument("--boot", type=int, default=2000, help="bootstrap resamples")
    ap.add_argument("--seed", type=int, default=0)
    return ap.parse_args(argv)


def main(argv=None, tables=None, out=sys.stdout):
    args = parse_args(argv)
    cfg = io.load_config()
    tables = tables if tables is not None else io.load_tables(cfg["paths"]["processed"])

    def progress(i, n):
        if i % 25 == 0 or i == n:
            print(f"  {i}/{n} held out", file=sys.stderr)

    errors = run(tables, cfg, args.analogs, args.embedder, progress)
    summary = summarize(errors, args.boot, args.seed)
    print_summary(summary, errors, out)
    path = args.out or cfg["paths"]["cache"] / "evaluation" / "errors.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    errors.to_csv(path, index=False)
    print(f"Per-analog errors: {path}", file=out)
    return errors, summary


if __name__ == "__main__":
    main()
