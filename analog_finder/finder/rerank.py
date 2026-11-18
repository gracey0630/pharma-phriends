"""Re-rank the scored candidates: a pass-through in v1.

D4 (docs/decisions.md): in v1 the language model writes summaries only and does not re-rank, so the ranking stays
deterministic and testable. A later re-rank (reorder or drop only, never add) replaces `rerank` here, keeping its
signature, so the loop and the CLI don't change.
"""


def rerank(scores, target=None, candidates=None):
    """Return the score table unchanged (same rows, same order)."""
    return scores
