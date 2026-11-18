"""The finder CLI end to end on the fixture tables (offline), with outputs in a temp folder."""
import io as stdio

import pandas as pd
import pytest

from analog_finder import io
from analog_finder.finder import __main__ as cli


@pytest.fixture
def run_cli(finder_tables, tmp_path, monkeypatch):
    real = io.load_config

    def load_config(scenario=None, **kw):
        cfg = real(scenario, **kw)
        cfg["paths"]["scenarios_out"] = tmp_path / "scenarios"
        cfg["paths"]["cache"] = tmp_path / "cache"
        return cfg

    monkeypatch.setattr(cli.io, "load_config", load_config)

    def run(*argv, answers=()):
        answers = iter(answers)
        out = stdio.StringIO()
        state = cli.run(cli.parse_args(["--scenario", "torevia", *argv]), tables=finder_tables, out=out,
                        ask=lambda prompt: next(answers))
        return state, out.getvalue(), tmp_path / "scenarios"
    return run


def test_until_stages(run_cli):
    state, text, _ = run_cli("--until", "filters")
    assert "Filters: 12 candidates" in text and "embedding" not in state
    state, text, _ = run_cli("--until", "embed")
    assert "Embeddings: 12 analogs + target (tfidf)" in text and "scores" not in state
    state, text, _ = run_cli("--until", "score")
    assert "Top 10 of 12 by similarity" in text and len(state["scores"]) == 12


def test_auto_confirm_writes_the_decision_log(run_cli):
    state, text, out = run_cli("--auto-confirm")
    log = pd.read_csv(out / "torevia" / "analog_recommendations.csv")
    assert (log.decision == "confirmed").sum() == 5
    assert list(log[log.decision == "confirmed"].analog_id) == list(state["scores"].analog_id[:5])
    assert "Confirmed 5:" in text


def test_interactive_reject_offers_the_sixth(run_cli):
    # confirm #1, reject #2 (reason 1, with a note), then confirm everything else
    state, text, out = run_cli(answers=["c", "r", "1", "Parkinson's psychosis", "c", "c", "c", "c"])
    q = state["queue"]
    ranked = list(state["scores"].analog_id)
    assert q.rejected == [ranked[1]] and ranked[5] in q.confirmed and len(q.confirmed) == 5
    assert "next candidate offered: #6" in text
    log = pd.read_csv(out / "torevia" / "analog_recommendations.csv")
    assert log[log.decision == "rejected"].reason.tolist() == ["indication: Parkinson's psychosis"]
    assert set(log.decided_by.dropna()) == {"forecaster"}


def test_stop_after_three_and_resume(run_cli):
    state, _, out = run_cli(answers=["c", "c", "c", "s"])
    assert len(state["queue"].confirmed) == 3
    state, _, _ = run_cli("--resume", answers=["c", "c"])
    assert len(state["queue"].confirmed) == 5


def test_bad_answers_record_nothing(run_cli):
    state, text, _ = run_cli(answers=["x", "s", "r", "9", "r", "5", "", "c", "c", "c", "c", "c"])
    assert "type c or r" in text and "not a reason number" in text and "needs a note" in text
    assert state["queue"].rejected == [] and len(state["queue"].confirmed) == 5


def test_holdout_writes_to_its_own_folder(run_cli):
    state, _, out = run_cli("--auto-confirm", "--holdout", "o01_oral")
    assert state["output"] == "torevia-holdout-o01_oral"
    log = pd.read_csv(out / "torevia-holdout-o01_oral" / "analog_recommendations.csv")
    assert "o01_oral" not in set(log.analog_id)
    assert not (out / "torevia").exists()


def test_full_run_writes_weights_and_curve(run_cli):
    state, text, out = run_cli("--auto-confirm")
    w = pd.read_csv(out / "torevia" / "analog_weights.csv")
    u = pd.read_csv(out / "torevia" / "uptake_curve.csv")
    assert list(w.analog_id) == state["queue"].confirmed and w.weight.sum() == pytest.approx(1)
    assert list(u.quarter) == list(range(21))
    assert ((u.band_min <= u.weighted_share_of_peak + 1e-9) & (u.weighted_share_of_peak <= u.band_max + 1e-9)).all()
    assert "Caveats:" in text and "Bass fits of the confirmed analogs" in text


def test_until_loop_skips_the_curve(run_cli):
    state, _, out = run_cli("--auto-confirm", "--until", "loop")
    assert "weights" not in state and not (out / "torevia" / "analog_weights.csv").exists()
