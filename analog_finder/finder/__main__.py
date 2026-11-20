"""Analog Finder command line: python -m analog_finder.finder --scenario torevia

Runs the finder stage by stage (docs/implementation_plan.md, steps 2-7):
target drug -> hard filters -> embeddings -> scores -> confirm loop -> weights + uptake curve.

Outputs go to data/scenarios/<scenario>/: analog_recommendations.csv, analog_weights.csv, uptake_curve.csv.
A run with --holdout writes to data/scenarios/<scenario>-holdout-<ids>/ instead (gitignored), so evaluation runs
never overwrite the demo outputs.
"""
import argparse
import sys

import pandas as pd

from analog_finder import io
from analog_finder.finder import curve, embed, filters, loop, rerank, score, summarize
from analog_finder.finder.target import load_target

STAGES = ["filters", "embed", "score", "loop", "curve"]


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="python -m analog_finder.finder", description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", required=True, help="analog_finder/scenarios/<scenario>.yaml")
    ap.add_argument("--holdout", action="append", default=[], metavar="ANALOG_ID",
                    help="remove this analog before filtering (evaluation); repeatable")
    ap.add_argument("--embedder", choices=["tfidf", "rxbert"], default=None,
                    help="text embedder (default: config/scoring.yaml)")
    ap.add_argument("--until", choices=STAGES, default=STAGES[-1], help="stop after this stage")
    ap.add_argument("--auto-confirm", action="store_true", help="confirm the top k without asking")
    ap.add_argument("--resume", action="store_true", help="continue from the saved analog_recommendations.csv")
    ap.add_argument("--decided-by", default="forecaster", help="name recorded with each decision")
    ap.add_argument("--summaries", choices=summarize.MODES, default=None,
                    help="candidate cards: template (offline), gemini, or auto (default: config/scoring.yaml)")
    return ap.parse_args(argv)


def output_name(scenario, holdout):
    return f"{scenario}-holdout-{'-'.join(holdout)}" if holdout else scenario


def run(args, tables=None, out=sys.stdout, ask=input):
    cfg = io.load_config(args.scenario)
    target = load_target(args.scenario)
    tables = tables if tables is not None else io.load_tables(cfg["paths"]["processed"])
    print(f"Target: {target.name} ({target.atc4}, {target.route_group})", file=out)

    cands = filters.candidates(tables, target, cfg["filters"], holdout=args.holdout, top_k=cfg["top_k"])
    held = f", holdout {', '.join(args.holdout)}" if args.holdout else ""
    print(f"Filters: {len(cands)} candidates ({target.route_group}, usable{held})", file=out)
    state = {"config": cfg, "target": target, "candidates": cands, "output": output_name(args.scenario, args.holdout)}
    if args.until == "filters":
        return state

    name = args.embedder or cfg["embedder"]
    evidence = io.load_approved_evidence(cfg["paths"]["reference"])
    cache = embed.EmbeddingCache(cfg["paths"]["cache"])
    use_ev = cfg["use_evidence"]
    emb = embed.embed(cands, evidence, target, tables["analog_features"], embed.get_embedder(name, cfg), cache,
                      use_evidence=use_ev)
    print(f"Embeddings: {len(emb['analog_ids'])} analogs + target ({name}; approved evidence "
          f"{'used' if use_ev else 'not used: use_evidence is off'})", file=out)
    state.update(evidence=evidence, embedding=emb, embedder=name)
    if args.until == "embed":
        return state

    scores = rerank.rerank(score.score(cands, emb, evidence, target, cfg["weights"], use_evidence=use_ev),
                           target, cands)
    state["scores"] = scores
    print_ranking(scores, cands, out)
    if args.until == "score":
        return state

    summarizer = summarize.Summarizer(args.summaries or cfg.get("summaries", "template"),
                                      cache_dir=cfg["paths"]["cache"], scenario=args.scenario)
    show = card_maker(summarizer, scores, cands, target, cfg, evidence, embed.class_names(tables["analog_features"]))
    state["cards"] = show.cards
    queue = make_queue(args, cfg, scores, state["output"])
    if args.auto_confirm:
        queue.auto_confirm()
        print("\nCandidate cards (" + summarizer.generator + "):", file=out)
        for a in queue.confirmed:
            print("\n" + show(a), file=out)
    else:
        interact(queue, cands, args.decided_by, out, ask, lambda: save_log(queue, cfg, state["output"]), show)
    paths = save_log(queue, cfg, state["output"])
    names = cands.set_index("analog_id").drug_name
    print(f"\nConfirmed {len(queue.confirmed)}: {', '.join(names[a] for a in queue.confirmed)}", file=out)
    if queue.rejected:
        print(f"Rejected {len(queue.rejected)}: {', '.join(names[a] for a in queue.rejected)}", file=out)
    print(f"Decision log: {paths['analog_recommendations']}", file=out)
    state["queue"] = queue
    if args.until == "loop" or not queue.confirmed:
        return state

    overrides = io.load_scenario(args.scenario).get("weight_overrides")
    weight_table = curve.weights(queue.confirmed, scores, overrides)
    upper = set(cands.analog_id[cands.peak_not_confirmed])
    uptake = curve.uptake_curve(weight_table, tables["launch_curves"], upper)
    bass = curve.bass_table(weight_table, tables["bass_fits"], cands)
    paths = io.write_scenario_outputs(state["output"], {"analog_weights": weight_table, "uptake_curve": uptake},
                                      cfg["paths"]["scenarios_out"])
    print_curve(weight_table, uptake, bass, names, upper, out)
    print(f"Outputs: {paths['analog_weights'].parent}", file=out)
    state.update(weights=weight_table, uptake_curve=uptake, bass=bass)
    return state


# --- curve ----------------------------------------------------------------------------------------------------

def _share(value, bounded):
    return "" if value != value else f"{'<=' if bounded else '  '}{value:.2f}"


def print_curve(weight_table, uptake, bass, names, upper, out):
    print("\nWeights (similarity, normalized; D5):", file=out)
    for r in weight_table.itertuples(index=False):
        note = f"  override: {r.override_reason}" if r.override_reason else ""
        print(f"   {names[r.analog_id]:<22}{r.weight:6.3f}   similarity {r.similarity:.3f}{note}", file=out)
    print("\nSimilarity-weighted uptake curve (share of peak; band = min-max of the confirmed analogs):", file=out)
    print(f"   {'quarter':>7}  {'weighted':>8}  {'band':>13}  analogs", file=out)
    for r in uptake[uptake.quarter.isin([0, 2, 4, 8, 12, 16, 20])].itertuples(index=False):
        bound = r.n_upper_bound > 0
        band = "" if r.band_min != r.band_min else f"{r.band_min:.2f}-{r.band_max:.2f}"
        note = f"  ({r.n_upper_bound} with peak not confirmed: <=)" if bound else ""
        print(f"   {'Q' + str(r.quarter):>7}  {_share(r.weighted_share_of_peak, bound):>8}  {band:>13}  "
              f"{r.n_analogs}{note}", file=out)
    print("\nBass fits of the confirmed analogs (bass_fits.csv):", file=out)
    print(f"   {'analog':<22}{'p':>8}{'q':>8}{'m':>7}{'R2':>7}  flags", file=out)
    for r in bass.itertuples(index=False):
        flags = ", ".join(f for f, on in [("weak fit", r.weak_fit_flag), ("low volume", r.low_volume),
                                          ("peak not confirmed", r.analog_id in upper)] if on is True or on == 1)
        nums = (f"{r.p:8.4f}{r.q:8.3f}{r.m:7.2f}{r.fit_quality:7.3f}" if r.p == r.p else f"{'no fit':>30}")
        print(f"   {names[r.analog_id]:<22}{nums}  {flags}", file=out)
    print("\nCaveats:", file=out)
    for c in curve.CAVEATS:
        print(f"   - {c}", file=out)


# --- ranking and loop -----------------------------------------------------------------------------------------

def _cells(row, feats):
    return " ".join(f"{'':>8}" if row[c] != row[c] else f"{row[c]:8.2f}" for c in feats)  # NaN != NaN: blank


def print_ranking(scores, cands, out, n=10):
    """The top n with the per-feature breakdown (blank = feature not used for that analog)."""
    names = cands.set_index("analog_id").drug_name
    feats = [c for c in scores.columns if c.startswith("s_")]
    print(f"\nTop {n} of {len(scores)} by similarity:", file=out)
    print(f"{'rank':>4}  {'analog':<22}{'similarity':>10}  " + " ".join(f"{c[2:][:8]:>8}" for c in feats), file=out)
    for row in scores.head(n).to_dict("records"):
        print(f"{row['rank']:>4}  {names[row['analog_id']]:<22}{row['similarity']:10.3f}  {_cells(row, feats)}",
              file=out)


def make_queue(args, cfg, scores, output):
    path = cfg["paths"]["scenarios_out"] / output / "analog_recommendations.csv"
    if args.resume:
        if not path.exists():
            raise SystemExit(f"--resume: no saved decisions at {path}")
        saved = pd.read_csv(path, dtype={"reason": str, "decided_by": str, "decided_at": str})
        return loop.CandidateQueue.from_log(scores, args.scenario, saved, top_k=cfg["top_k"])
    return loop.CandidateQueue(scores, args.scenario, top_k=cfg["top_k"])


def save_log(queue, cfg, output):
    return io.write_scenario_outputs(output, {"analog_recommendations": queue.to_frame()},
                                     cfg["paths"]["scenarios_out"])


def card_maker(summarizer, scores, cands, target, cfg, evidence, class_names):
    """show(analog_id) -> the candidate's card as text (step 13); the card dicts are kept in show.cards."""
    by_id = scores.set_index("analog_id")
    cand = cands.set_index("analog_id")

    def show(analog_id):
        if analog_id not in show.cards:
            row = {"analog_id": analog_id, **by_id.loc[analog_id].to_dict()}
            show.cards[analog_id] = summarizer.card(
                row, {"analog_id": analog_id, **cand.loc[analog_id].to_dict()}, target, cfg["weights"], evidence,
                cfg["use_evidence"], class_names)
        return summarize.render(show.cards[analog_id])
    show.cards = {}
    return show


def interact(queue, cands, by, out, ask, save, show):
    """Ask about each open candidate in rank order until none are open or the forecaster stops."""
    reasons = list(loop.REJECT_REASONS)
    while not queue.done:
        analog_id = queue.open[0]
        print("\n" + show(analog_id), file=out)
        stop = "/[s]top" if queue.can_stop else ""
        choice = ask(f"[c]onfirm/[r]eject{stop} ({len(queue.confirmed)} confirmed): ").strip().lower()[:1]
        if choice == "c":
            queue.confirm(analog_id, by)
        elif choice == "r":
            for i, key in enumerate(reasons, 1):
                print(f"   {i}. {loop.REJECT_REASONS[key]}", file=out)
            pick = ask("reason number: ").strip()
            if not (pick.isdigit() and 1 <= int(pick) <= len(reasons)):
                print("   not a reason number; nothing recorded", file=out)
                continue
            key = reasons[int(pick) - 1]
            note = ask("note (required for other): " if key == "other" else "note (optional): ")
            if key == "other" and not note.strip():
                print("   'other' needs a note; nothing recorded", file=out)
                continue
            nxt = queue.reject(analog_id, key, note, by)
            if nxt:
                print(f"   next candidate offered: #{int(queue.scores.loc[nxt, 'rank'])}", file=out)
        elif choice == "s" and queue.can_stop:
            break
        else:
            print("   type c or r" + (" or s" if queue.can_stop else ""), file=out)
            continue
        save()


def main(argv=None):
    try:
        run(parse_args(argv))
    except summarize.SummaryError as e:
        raise SystemExit(f"error: {e}") from None


if __name__ == "__main__":
    main()
