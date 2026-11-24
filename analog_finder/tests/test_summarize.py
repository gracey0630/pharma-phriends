"""Summary cards (step 13): offline, on the shared finder fixtures."""
import json

import pandas as pd
import pytest

from analog_finder import llm
from analog_finder.finder import embed, filters, score, summarize

WEIGHTS = {"text": 1.0, "atc4": 0.25, "atc3": 0.25, "area": 0.1, "line_of_therapy": 1.0, "dosing_frequency": 1.0,
           "n_competitors": 1.0, "order_of_entry": 0.0}


@pytest.fixture
def ranked(finder_tables, schizo_target):
    c = filters.candidates(finder_tables, schizo_target)
    e = embed.embed(c, None, schizo_target, finder_tables["analog_features"], embed.TfidfEmbedder())
    s = score.score(c, e, None, schizo_target, WEIGHTS, use_evidence=False)
    names = embed.class_names(finder_tables["analog_features"])
    return c.set_index("analog_id"), s.set_index("analog_id"), names


def make(ranked, target, analog_id, summarizer=None, evidence=None, use_evidence=False):
    cands, scores, names = ranked
    row = {"analog_id": analog_id, **scores.loc[analog_id].to_dict()}
    cand = {"analog_id": analog_id, **cands.loc[analog_id].to_dict()}
    return (summarizer or summarize.Summarizer()).card(row, cand, target, WEIGHTS, evidence, use_evidence, names)


def test_indication_words_drop_brand_and_boilerplate():
    words = summarize.indication_words(
        "NUPLAZID is indicated for the treatment of hallucinations and delusions associated with Parkinson’s "
        "disease psychosis. The efficacy was established in a 6-week trial.", "Nuplazid")
    assert words == ["hallucinations", "delusions", "parkinson", "psychosis"]


def test_template_card_same_class(ranked, schizo_target):
    card = make(ranked, schizo_target, "o01_oral")
    assert card["generated_by"] == "template"
    assert card["headline"].startswith(f"#{card['rank']} Oone, similarity ")
    assert "same ATC 4 class (Other antipsychotics)" in card["headline"]
    assert "Same ATC 4 class: Other antipsychotics" in card["similarities"]
    assert "Both indicated for: schizophrenia" in card["similarities"]
    assert not any(d.startswith("Different ATC 4") for d in card["differences"])


def test_template_card_different_class_and_words(ranked, schizo_target):
    card = make(ranked, schizo_target, "o05_oral")  # antidepressant: same area, other class, other disease
    assert "Different ATC 4 class: Other antidepressants (target: Other antipsychotics)" in card["differences"]
    assert any("major" in d and "depressive" in d for d in card["differences"])
    assert "Same therapeutic area: Nervous system" in card["similarities"]
    no_class = make(ranked, schizo_target, "o11_oral")
    assert "No ATC class on record for this analog" in no_class["differences"]
    assert no_class["headline"].endswith("indication text only.")


def test_breakdown_adds_up_to_the_similarity(ranked, schizo_target):
    for analog_id in ["o01_oral", "o05_oral", "o11_oral"]:
        card = make(ranked, schizo_target, analog_id)
        b = card["score_breakdown"]
        got = sum(v["score"] * v["weight"] for v in b.values()) / sum(v["weight"] for v in b.values())
        assert got == pytest.approx(card["similarity"], abs=2e-3)
        assert "order_of_entry" not in b  # weight 0: not part of the score


def test_flags_in_words(ranked, schizo_target):
    assert "possible label expansion in the first 3 years" in make(ranked, schizo_target, "o02_oral")["flags"]
    assert "peak not confirmed yet (share of peak is an upper bound)" in make(ranked, schizo_target,
                                                                              "o04_oral")["flags"]
    assert make(ranked, schizo_target, "o01_oral")["flags"] == []


def test_evidence_and_sources(ranked, schizo_target):
    ev = pd.DataFrame({"line_of_therapy": ["any"], "line_of_therapy_quote": ["indicated for schizophrenia"],
                       "line_of_therapy_url": ["https://www.accessdata.fda.gov/o03.pdf"],
                       "dosing_frequency": ["once daily"], "dosing_frequency_quote": ["once daily"],
                       "dosing_frequency_url": ["https://www.accessdata.fda.gov/o03.pdf"],
                       "n_competitors_at_launch": ["2"], "n_competitors_at_launch_quote": [""],
                       "n_competitors_at_launch_url": [""]},
                      index=pd.Index(["o03_oral"], name="analog_id"))
    off = make(ranked, schizo_target, "o03_oral", evidence=ev)
    assert "Dosing: once daily (target: once daily); not used in matching yet" in off["differences"]
    assert [s["field"] for s in off["sources"]] == ["line_of_therapy", "dosing_frequency"]  # no quote/url: left out
    on = make(ranked, schizo_target, "o03_oral", evidence=ev, use_evidence=True)
    assert "Dosing: once daily (target: once daily)" in on["similarities"]
    assert "# competitors at launch: 2 (target: 6)" in on["differences"]


def test_render_is_plain_text(ranked, schizo_target):
    text = summarize.render(make(ranked, schizo_target, "o02_oral"))
    lines = text.splitlines()
    assert lines[0].startswith("#") and lines[1].startswith("   alike:")
    assert any(l.startswith("   scored on:") and "indication text" in l for l in lines)
    assert any(l.startswith("   flags:") for l in lines)


# --- settings and the model path ----------------------------------------------------------------------------

def test_no_key_means_template(monkeypatch):
    monkeypatch.setattr(llm, "env", lambda name, default=None: None)
    assert summarize.Summarizer("auto").generator == "template"
    with pytest.raises(summarize.SummaryError, match="GEMINI_API_KEY"):
        summarize.Summarizer("gemini")
    with pytest.raises(summarize.SummaryError, match="one of"):
        summarize.Summarizer("gpt")


def test_model_card_is_cached(ranked, schizo_target, tmp_path):
    body = {"headline": "Oone ranks first: same class, schizophrenia.", "similarities": ["Same class"],
            "differences": []}
    fake = llm.FakeLLM({"summary_card": body})
    s = summarize.Summarizer("gemini", llm=fake, cache_dir=tmp_path, scenario="torevia")
    first = make(ranked, schizo_target, "o01_oral", s)
    again = make(ranked, schizo_target, "o01_oral", s)
    assert first["generated_by"] == "fake" and first["headline"] == body["headline"] and again == first
    assert len(fake.calls) == 1  # the second card came from the cache
    title, prompt = fake.calls[0]
    assert title == "summary_card" and json.loads(prompt.split("FACTS:\n", 1)[1])["drug_name"] == "Oone"
    assert first["score_breakdown"] and first["flags"] == []  # always from the data
    assert len(list((tmp_path / "cards" / "torevia").glob("o01_oral-*.json"))) == 1


@pytest.mark.parametrize("body, problem", [
    ({"headline": "Oone is like Zyprexa.", "similarities": [], "differences": []}, "name Zyprexa"),
    ({"headline": "Oone peaked at 42% in year 2.", "similarities": [], "differences": []}, "number 42"),
])
def test_model_text_with_unknown_facts_falls_back(ranked, schizo_target, body, problem):
    s = summarize.Summarizer("gemini", llm=llm.FakeLLM({"summary_card": body}))
    card = make(ranked, schizo_target, "o01_oral", s)
    assert card["generated_by"].startswith("template (model output failed the fact check")
    assert problem in card["generated_by"] and "same ATC 4 class" in card["headline"]


def test_model_error_falls_back(ranked, schizo_target):
    class Broken:
        name = "gemini"

        def generate_json(self, prompt, schema):
            raise llm.LLMError("not JSON")

    card = make(ranked, schizo_target, "o01_oral", summarize.Summarizer("gemini", llm=Broken()))
    assert card["generated_by"] == "template (model call failed: LLMError)"
