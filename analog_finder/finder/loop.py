"""The confirm loop (D3): show the top k candidates, confirm or reject each; a rejection offers the next-ranked one.

CandidateQueue holds the state and the decision log, so the CLI (step 6) and the app's finder page (step 14) share
one implementation. Every event is a log row (Shared contracts; data_model.md `analog_recommendations`):
  scenario, analog_id, rank, similarity, decision (shown / confirmed / rejected), reason, decided_by, decided_at
A session can resume by replaying a saved log (from_log). The forecaster may stop with min_confirmed (3) or more.

Spec: analog_finder/docs/components/loop.md
"""
import warnings
from datetime import datetime, timezone

import pandas as pd

LOG_COLUMNS = ["scenario", "analog_id", "rank", "similarity", "decision", "reason", "decided_by", "decided_at"]
# Reject reasons: a short fixed list (easy to count later) plus free text; "other" needs the text.
REJECT_REASONS = {
    "indication": "different indication or patients",
    "line": "different line of therapy",
    "distorted": "distorted curve (label expansion / generic)",
    "data": "data quality",
    "other": "other",
}
RESTORED = "restored"


class LoopError(ValueError):
    """An action that doesn't fit the queue's state (e.g. confirming an analog that isn't shown)."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CandidateQueue:
    def __init__(self, scores, scenario, top_k=5, min_confirmed=3, clock=_now):
        if scores.empty:
            raise LoopError("no scored candidates")
        self.scores = scores.set_index("analog_id")
        self.order = list(scores.sort_values("rank").analog_id)
        self.scenario = scenario
        self.top_k = top_k
        self.min_confirmed = min_confirmed
        self.clock = clock
        self.state = dict.fromkeys(self.order, "pending")  # pending -> shown -> confirmed / rejected
        self.log = []
        for analog_id in self.order[:top_k]:
            self._show(analog_id)

    # --- state ------------------------------------------------------------------------------------------------

    def _record(self, analog_id, decision, reason="", by=""):
        r = self.scores.loc[analog_id]
        self.log.append({"scenario": self.scenario, "analog_id": analog_id, "rank": int(r["rank"]),
                         "similarity": float(r["similarity"]), "decision": decision, "reason": reason,
                         "decided_by": by, "decided_at": self.clock()})

    def _show(self, analog_id, reason="", by=""):
        self.state[analog_id] = "shown"
        self._record(analog_id, "shown", reason, by)

    def _expect(self, analog_id, state):
        if analog_id not in self.state:
            raise LoopError(f"{analog_id} is not a candidate")
        if self.state[analog_id] != state:
            raise LoopError(f"{analog_id} is {self.state[analog_id]}, not {state}")

    def _ids(self, state):
        return [a for a in self.order if self.state[a] == state]

    @property
    def open(self):
        """Shown and not yet decided, in rank order."""
        return self._ids("shown")

    @property
    def confirmed(self):
        return self._ids("confirmed")

    @property
    def rejected(self):
        return self._ids("rejected")

    @property
    def remaining(self):
        """Not shown yet: the replacements still available."""
        return self._ids("pending")

    @property
    def can_stop(self):
        return len(self.confirmed) >= self.min_confirmed

    @property
    def done(self):
        return not self.open

    # --- actions ----------------------------------------------------------------------------------------------

    def confirm(self, analog_id, by=""):
        self._expect(analog_id, "shown")
        self.state[analog_id] = "confirmed"
        self._record(analog_id, "confirmed", by=by)

    def reject(self, analog_id, reason, note="", by=""):
        """Reject a shown candidate and offer the next-ranked one. Returns its analog_id, or None (warning) when the
        candidates have run out. reason: a key of REJECT_REASONS; note: free text (required for "other")."""
        self._expect(analog_id, "shown")
        if reason not in REJECT_REASONS:
            raise LoopError(f"unknown reason '{reason}'; expected one of {list(REJECT_REASONS)}")
        note = (note or "").strip()
        if reason == "other" and not note:
            raise LoopError("reason 'other' needs a note saying why")
        self.state[analog_id] = "rejected"
        self._record(analog_id, "rejected", f"{reason}: {note}" if note else reason, by)
        nxt = self.remaining[0] if self.remaining else None
        if nxt is None:
            warnings.warn("no candidates left to replace the rejected one; restore one or stop", stacklevel=2)
        else:
            self._show(nxt)
        return nxt

    def restore(self, analog_id, by=""):
        """Bring a rejected analog back as a shown candidate."""
        self._expect(analog_id, "rejected")
        self._show(analog_id, RESTORED, by)

    def auto_confirm(self, by="auto"):
        """Confirm every open candidate (the top k on a fresh queue)."""
        for analog_id in self.open:
            self.confirm(analog_id, by)

    def to_frame(self):
        return pd.DataFrame(self.log, columns=LOG_COLUMNS)

    # --- resume -----------------------------------------------------------------------------------------------

    @classmethod
    def from_log(cls, scores, scenario, log, top_k=5, min_confirmed=3, clock=_now):
        """Rebuild a queue by replaying a saved decision log on the same scores. The saved rows are kept as they
        were (times and names); new actions append to them. Raises if the log names an analog that isn't scored
        (the candidates changed, e.g. a different holdout)."""
        q = cls(scores, scenario, top_k, min_confirmed, clock)
        unknown = sorted(set(log.analog_id) - set(q.state))
        if unknown:
            raise LoopError(f"saved log names analogs that aren't candidates now: {unknown}")
        q.log = []
        q.state = dict.fromkeys(q.order, "pending")
        for row in log.fillna("").to_dict("records"):
            a, decision = row["analog_id"], row["decision"]
            q.state[a] = {"shown": "shown", "confirmed": "confirmed", "rejected": "rejected"}[decision]
            q.log.append({c: row[c] for c in LOG_COLUMNS})
        return q
