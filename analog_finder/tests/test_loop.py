import pandas as pd
import pytest

from analog_finder.finder import loop


def _scores(n=8):
    return pd.DataFrame({"analog_id": [f"a{i}" for i in range(1, n + 1)], "rank": range(1, n + 1),
                         "similarity": [1 - i / 10 for i in range(n)]})


def _queue(n=8, **kw):
    return loop.CandidateQueue(_scores(n), "s", clock=lambda: "2026-11-18T00:00:00+00:00", **kw)


def test_top_k_shown_first():
    q = _queue()
    assert q.open == ["a1", "a2", "a3", "a4", "a5"] and q.remaining == ["a6", "a7", "a8"]
    assert list(q.to_frame().decision) == ["shown"] * 5


def test_reject_candidate_2_offers_candidate_6():
    q = _queue()
    nxt = q.reject("a2", "indication", note="Parkinson's psychosis", by="jm")
    assert nxt == "a6"
    assert q.open == ["a1", "a3", "a4", "a5", "a6"] and q.rejected == ["a2"]
    log = q.to_frame()
    assert log.iloc[-2][["analog_id", "decision", "reason", "decided_by"]].tolist() == \
        ["a2", "rejected", "indication: Parkinson's psychosis", "jm"]
    assert log.iloc[-1][["analog_id", "decision", "rank"]].tolist() == ["a6", "shown", 6]


def test_auto_confirm_confirms_top_5():
    q = _queue()
    q.auto_confirm()
    assert q.confirmed == ["a1", "a2", "a3", "a4", "a5"] and q.done
    assert list(q.to_frame().columns) == loop.LOG_COLUMNS


def test_stop_needs_three_confirmed():
    q = _queue()
    q.confirm("a1")
    q.confirm("a2")
    assert not q.can_stop
    q.confirm("a3")
    assert q.can_stop and not q.done


def test_running_out_warns_and_restore_brings_back():
    q = _queue(n=6)
    q.reject("a1", "data")
    with pytest.warns(UserWarning, match="no candidates left"):
        assert q.reject("a2", "data") is None
    assert q.open == ["a3", "a4", "a5", "a6"]
    q.restore("a2")
    assert "a2" in q.open and q.to_frame().iloc[-1].reason == loop.RESTORED


@pytest.mark.parametrize("action, message", [
    (lambda q: q.confirm("a7"), "pending, not shown"),
    (lambda q: q.confirm("zz"), "not a candidate"),
    (lambda q: q.reject("a1", "because"), "unknown reason"),
    (lambda q: q.reject("a1", "other"), "needs a note"),
    (lambda q: q.restore("a1"), "shown, not rejected"),
])
def test_invalid_actions(action, message):
    with pytest.raises(loop.LoopError, match=message):
        action(_queue())


def test_resume_replays_the_log():
    q = _queue()
    q.confirm("a1", by="jm")
    q.reject("a2", "line", by="jm")
    saved = q.to_frame()
    r = loop.CandidateQueue.from_log(_scores(), "s", saved)
    assert r.confirmed == ["a1"] and r.rejected == ["a2"] and r.open == ["a3", "a4", "a5", "a6"]
    assert r.to_frame().equals(saved)
    assert r.reject("a3", "data") == "a7"  # continues where it left off


def test_resume_with_changed_candidates_fails():
    q = _queue()
    saved = q.to_frame()
    with pytest.raises(loop.LoopError, match="aren't candidates"):
        loop.CandidateQueue.from_log(_scores().iloc[1:], "s", saved)
