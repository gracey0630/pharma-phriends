"""Analog Finder command line: python -m analog_finder.finder --scenario torevia

Runs the finder stage by stage (docs/implementation_plan.md, steps 2-7):
target drug -> hard filters -> embeddings -> scores -> confirm loop.

Outputs go to data/scenarios/<scenario>/ (analog_recommendations.csv). A run with --holdout writes to
data/scenarios/<scenario>-holdout-<ids>/ instead (gitignored), so evaluation runs never overwrite the demo outputs.
"""
import argparse
import sys

import pandas as pd

from analog_finder import io
from analog_finder.finder import embed, filters, loop, rerank, score
from analog_finder.finder.target import load_target

STAGES = ["filters", "embed", "score", "loop"]
FLAG_LABELS = {"warn_label_expansion": "possible label expansion in Q0-Q12", "warn_multi_route": "multi-route brand",
               "low_volume": "low Medicaid volume", "peak_not_confirmed": "peak not confirmed (share is <= X)",
               "weak_bass_fit": "weak Bass fit"}


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
    emb = embed.embed(cands, evidence, target, tables["analog_features"], embed.get_embedder(name, cfg), cache)
    print(f"Embeddings: {len(emb['analog_ids'])} analogs + target ({name})", file=out)
    state.update(evidence=evidence, embedding=emb, embedder=name)
    if args.until == "embed":
        return state

    scores = rerank.rerank(score.score(cands, emb, evidence, target, cfg["weights"]), target, cands)
    state["scores"] = scores
    print_ranking(scores, cands, out)
    if args.until == "score":
        return state

    queue = make_queue(args, cfg, scores, state["output"])
    if args.auto_confirm:
        queue.auto_confirm()
    else:
        interact(queue, cands, args.decided_by, out, ask, lambda: save_log(queue, cfg, state["output"]))
    paths = save_log(queue, cfg, state["output"])
    names = cands.set_index("analog_id").drug_name
    print(f"\nConfirmed {len(queue.confirmed)}: {', '.join(names[a] for a in queue.confirmed)}", file=out)
    if queue.rejected:
        print(f"Rejected {len(queue.rejected)}: {', '.join(names[a] for a in queue.rejected)}", file=out)
    print(f"Decision log: {paths['analog_recommendations']}", file=out)
    state["queue"] = queue
    return state


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


def card(analog_id, queue, cands):
    """A plain-text candidate card: rank, similarity, the features that were scored, warning flags."""
    s = queue.scores.loc[analog_id]
    c = cands.set_index("analog_id").loc[analog_id]
    used = [f"{k[2:]} {s[k]:.2f}" for k in queue.scores.columns if k.startswith("s_") and s[k] == s[k]]
    flags = [label for col, label in FLAG_LABELS.items() if bool(c[col])]
    indication = c.indication_text if len(c.indication_text) <= 160 else c.indication_text[:160] + "..."
    lines = [f"#{int(s['rank'])} {c.drug_name} ({analog_id})   similarity {s['similarity']:.3f}",
             f"   class: {c.atc4_name or 'none'}",
             f"   indication: {indication}",
             f"   scored on: {', '.join(used)}"]
    if flags:
        lines.append(f"   flags: {'; '.join(flags)}")
    return "\n".join(lines)


def interact(queue, cands, by, out, ask, save):
    """Ask about each open candidate in rank order until none are open or the forecaster stops."""
    reasons = list(loop.REJECT_REASONS)
    while not queue.done:
        analog_id = queue.open[0]
        print("\n" + card(analog_id, queue, cands), file=out)
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
    run(parse_args(argv))


if __name__ == "__main__":
    main()
