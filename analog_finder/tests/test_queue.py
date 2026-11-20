"""The work queue (step 10): offline, on the shared finder fixtures."""
import io as _io

import pandas as pd
import pytest

from analog_finder.research import queue
from analog_finder.research.sources import Source
from pipeline.build import EVIDENCE_COLS

SOURCES = [Source("ORIG labels", 6, ("www.accessdata.fda.gov",), ("line_of_therapy", "dosing_frequency")),
           Source("SEC EDGAR", 8, ("www.sec.gov",), ("launch_date",)),
           Source("Drugs@FDA", 2, ("www.accessdata.fda.gov",), ("n_competitors_at_launch",))]


@pytest.fixture
def tables(finder_tables):
    t = dict(finder_tables)
    pool = t["candidate_pool"].copy()
    pool["application_number"] = [f"NDA{200000 + i}" for i in range(len(pool))]
    t["candidate_pool"] = pool
    return t


def ev(*rows):
    out = []
    for analog_id, field, approved in rows:
        r = dict.fromkeys(EVIDENCE_COLS, "")
        r.update(analog_id=analog_id, field=field, value="v", approved=approved)
        out.append(r)
    return pd.DataFrame(out, columns=EVIDENCE_COLS)


def test_one_analog_lists_its_four_fields(tables):
    q = queue.build_queue(tables, ev(), analogs=["o01_oral"], sources=SOURCES)
    assert list(q.field) == ["line_of_therapy", "n_competitors_at_launch", "launch_date", "dosing_frequency"]
    assert set(q.status) == {"todo"} and q.application_number.iloc[0] == "NDA200000"
    assert q.set_index("field").sources["launch_date"] == "SEC EDGAR"


def test_company_sources_listed_only_for_their_analog(tables):
    srcs = SOURCES + [Source("Acme releases", 8, ("news.acme.com",), ("launch_date",), ("o02_oral",), ("/press/",))]
    q = queue.build_queue(tables, ev(), analogs=["o01_oral", "o02_oral"], fields=["launch_date"], sources=srcs)
    assert q.set_index("analog_id").sources.to_dict() == {"o01_oral": "SEC EDGAR", "o02_oral": "SEC EDGAR; Acme releases"}


def test_orig_application_from_indication_history(tables):
    t = dict(tables)
    pool = t["candidate_pool"].copy()
    pool.loc[pool.analog_id == "o02_oral", "application_number"] = "NDA100002; NDA300002"
    t["candidate_pool"] = pool
    assert queue.build_queue(t, ev(), analogs=["o02_oral"], sources=SOURCES).orig_application.iloc[0] == "NDA100002"
    t["indication_history"] = pd.DataFrame({
        "analog_id": ["o02_oral"] * 3, "application_number": ["NDA300002", "NDA100002", "NDA300002"],
        "submission_type": ["ORIG", "SUPPL", "ORIG"], "kind": ["original", "efficacy supplement", "original"],
        "approval_date": ["2015-01-01", "2016-01-01", "2014-06-01"]})
    q = queue.build_queue(t, ev(), analogs=["o02_oral", "o01_oral"], sources=SOURCES)
    got = q.drop_duplicates("analog_id").set_index("analog_id").orig_application
    assert got["o02_oral"] == "NDA300002"  # the earliest ORIG approval, not the first listed
    assert got["o01_oral"] == "NDA200000"  # no history row: first listed


def test_pool_is_the_usable_analogs(tables):
    q = queue.build_queue(tables, ev(), sources=SOURCES)
    # 12 usable oral + 1 usable sc; late_oral, gen_oral, thin_oral fail the funnel
    assert q.analog_id.nunique() == 13 and not {"late_oral", "gen_oral", "thin_oral"} & set(q.analog_id)
    assert len(queue.build_queue(tables, ev(), analogs=["late_oral"], sources=SOURCES)) == 4  # asked for by name


def test_approved_values_leave_the_queue_and_unapproved_wait_for_review(tables):
    e = ev(("o01_oral", "line_of_therapy", "true"), ("o01_oral", "dosing_frequency", "false"),
           ("o01_oral", "launch_date", "TRUE"))
    q = queue.build_queue(tables, e, analogs=["o01_oral"], sources=SOURCES).set_index("field")
    assert list(q.index) == ["n_competitors_at_launch", "dosing_frequency"]
    assert q.status.to_dict() == {"n_competitors_at_launch": "todo", "dosing_frequency": "pending_review"}


def test_tiers_order_expected_then_same_area_then_rest(tables, schizo_target):
    q = queue.build_queue(tables, ev(), target=schizo_target, expected=["o03_oral", "o07_oral"], sources=SOURCES)
    first = q.drop_duplicates("analog_id").set_index("analog_id").priority
    assert list(first.index[:2]) == ["o03_oral", "o07_oral"] and set(first[:2]) == {1}  # o07 is diabetes: still 1
    nervous = {"o01_oral", "o02_oral", "o04_oral", "o05_oral", "o06_oral"}
    assert set(first.index[first == 2]) == nervous
    assert first.is_monotonic_increasing
    assert set(queue.build_queue(tables, ev(), sources=SOURCES).priority) == {3}  # no scenario: no tiers


def test_tier_2_needs_the_target_route_group(tables, schizo_target):
    """An analog the finder can't pick for this target (other route group) isn't read early (step 11 follow-up)."""
    feats = tables["analog_features"].copy()
    feats.loc[feats.analog_id == "o05_oral", "route_group"] = "sc"
    q = queue.build_queue({**tables, "analog_features": feats}, ev(), target=schizo_target, sources=SOURCES)
    tiers = q.drop_duplicates("analog_id").set_index("analog_id").priority
    assert tiers["o05_oral"] == 3 and tiers["o04_oral"] == 2


def test_expected_analog_kept_even_if_the_funnel_drops_it(tables, schizo_target):
    q = queue.build_queue(tables, ev(), target=schizo_target, expected=["late_oral"], sources=SOURCES)
    assert q.set_index("analog_id").priority.get("late_oral").tolist() == [1, 1, 1, 1]
    assert "gen_oral" not in set(q.analog_id)  # not expected, not usable: left out
    with pytest.raises(queue.QueueError, match="expected analog"):
        queue.build_queue(tables, ev(), expected=["nope_oral"], sources=SOURCES)


def test_fields_subset_and_errors(tables):
    q = queue.build_queue(tables, ev(), analogs=["o01_oral"], fields=["launch_date"], sources=SOURCES)
    assert list(q.field) == ["launch_date"]
    with pytest.raises(queue.QueueError, match="unknown field"):
        queue.build_queue(tables, ev(), fields=["indication"], sources=SOURCES)
    with pytest.raises(queue.QueueError, match="not in analog_features"):
        queue.build_queue(tables, ev(), analogs=["nope_oral"], sources=SOURCES)


def test_print_queue_counts(tables, schizo_target):
    q = queue.build_queue(tables, ev(("o03_oral", "launch_date", "false")), target=schizo_target,
                          expected=["o03_oral"], sources=SOURCES)
    out = _io.StringIO()
    queue.print_queue(q, out, limit=3)
    text = out.getvalue()
    assert text.startswith(f"{len(q)} label reads for 13 analogs")
    assert "tier 1 (expected analog): 1 analog; 1 pending review, 3 todo" in text
    assert f"... {len(q) - 3} more" in text
    out = _io.StringIO()
    queue.print_queue(q.iloc[0:0], out)
    assert "Nothing to read" in out.getvalue()


def test_torevia_scenario_lists_expected_analogs():
    from analog_finder import io
    assert io.load_scenario("torevia")["expected_analogs"] == [
        "latuda_oral", "rexulti_oral", "vraylar_oral", "caplyta_oral", "lybalvi_oral"]
