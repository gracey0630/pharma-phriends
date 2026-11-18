"""Analog Finder command line: python -m analog_finder.finder --scenario torevia

Runs the finder stage by stage (docs/implementation_plan.md, steps 2-7): target drug -> hard filters -> embeddings.
"""
import argparse
import sys

from analog_finder import io
from analog_finder.finder import embed, filters
from analog_finder.finder.target import load_target

STAGES = ["filters", "embed"]


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="python -m analog_finder.finder", description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", required=True, help="analog_finder/scenarios/<scenario>.yaml")
    ap.add_argument("--holdout", action="append", default=[], metavar="ANALOG_ID",
                    help="remove this analog before filtering (evaluation); repeatable")
    ap.add_argument("--embedder", choices=["tfidf", "rxbert"], default=None,
                    help="text embedder (default: config/scoring.yaml)")
    ap.add_argument("--until", choices=STAGES, default=STAGES[-1], help="stop after this stage")
    return ap.parse_args(argv)


def run(args, tables=None, out=sys.stdout):
    cfg = io.load_config(args.scenario)
    target = load_target(args.scenario)
    tables = tables if tables is not None else io.load_tables(cfg["paths"]["processed"])
    print(f"Target: {target.name} ({target.atc4}, {target.route_group})", file=out)

    cands = filters.candidates(tables, target, cfg["filters"], holdout=args.holdout, top_k=cfg["top_k"])
    held = f", holdout {', '.join(args.holdout)}" if args.holdout else ""
    print(f"Filters: {len(cands)} candidates ({target.route_group}, usable{held})", file=out)
    state = {"config": cfg, "target": target, "candidates": cands}
    if args.until == "filters":
        return state

    name = args.embedder or cfg["embedder"]
    evidence = io.load_approved_evidence(cfg["paths"]["reference"])
    cache = embed.EmbeddingCache(cfg["paths"]["cache"])
    emb = embed.embed(cands, evidence, target, tables["analog_features"], embed.get_embedder(name, cfg), cache)
    print(f"Embeddings: {len(emb['analog_ids'])} analogs + target ({name})", file=out)
    state.update(evidence=evidence, embedding=emb, embedder=name)
    return state


def main(argv=None):
    run(parse_args(argv))


if __name__ == "__main__":
    main()
