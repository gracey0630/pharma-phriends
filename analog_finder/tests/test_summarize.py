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


# --- fact check (PR #17 review) -------------------------------------------------------------------------------

NAMES = {"drugs": frozenset({"abilify", "aripiprazole", "zyprexa"}), "companies": frozenset({"otsuka", "catalyst"})}


def facts_of(ranked, target, analog_id):
    cands, scores, names = ranked
    return summarize.facts({"analog_id": analog_id, **scores.loc[analog_id].to_dict()},
                           {"analog_id": analog_id, **cands.loc[analog_id].to_dict()}, target, WEIGHTS,
                           target_class_names=names)


def check(ranked, target, *texts):
    body = {"headline": texts[0], "similarities": list(texts[1:]), "differences": []}
    return summarize.fact_check(body, facts_of(ranked, target, "o01_oral"), NAMES)


@pytest.mark.parametrize("text", [
    "Shares the Other antipsychotics class with Tgt.",
    "Treats hallucinations and delusions, like the target.",           # first word capitalized; plain words
    "Approved for schizophrenia, as Tgt will be.",
    "Ranked #1 with similarity 1.0: same ATC 4 class and same ATC 3 class.",
    "Text similarity 1.00; the ATC 4 class carries weight 0.25 (25%).",
    "Both are in the Nervous system area. Its uptake is in Medicaid data.",
    "Oone works as a catalyst for comparison.",                         # a company word, but not capitalized
])
def test_honest_wording_passes(ranked, schizo_target, text):
    assert check(ranked, schizo_target, text) == []


@pytest.mark.parametrize("text, problem", [
    ("Oone is made by Otsuka.", "name Otsuka"),
    ("Otsuka also makes Oone.", "name Otsuka"),                        # a company at the start of a sentence
    ("Abilify was approved first.", "name Abilify"),                    # a drug at the start of a sentence
    ("Oone works like aripiprazole.", "name aripiprazole"),            # a drug in lower case
    ("Oone is like Zyprexa.", "name Zyprexa"),
    ("Oone is sold by a Japanese company.", "name Japanese"),          # capitalized mid-sentence, not in the facts
    ("Oone was approved in 2015.", "number 2015"),
    ("Oone reached 0.5 of peak.", "number 0.5"),                        # no fact rounds to 0.5 (1, 0.25, 0.1)
    ("Oone peaked at 42% in year 2.", "number 42%"),
    ("Oone is in ATC 7.", "number 7"),                                  # ATC levels are 1-5
])
def test_invented_names_and_numbers_fail(ranked, schizo_target, text, problem):
    problems = check(ranked, schizo_target, text)
    assert any(p.startswith(problem + " ") for p in problems), problems


@pytest.mark.parametrize("text, percent, ok", [
    ("0.523", "", True), ("0.52", "", True), ("0.5", "", True),        # rounded to the text's decimals
    ("52", "%", True), ("52.3", "%", True),                             # as a percentage
    ("0.6", "", False), ("0.53", "", False), ("1", "", False),          # 0.52 isn't "1"
    ("52", "", False),                                                  # 52 without % isn't 0.523
])
def test_number_rule(text, percent, ok):
    from decimal import Decimal
    assert summarize.number_ok(text, percent, {Decimal("0.523")}) is ok


def test_number_rule_whole_numbers_and_boundaries():
    from decimal import Decimal
    assert summarize.number_ok("6", "", {Decimal("6.0")}) and summarize.number_ok("0", "", {Decimal("0")})
    assert summarize.number_ok("0.07", "", {Decimal("0.075")})          # the template's 0.0746 -> 0.075 -> "0.07"
    assert summarize.number_ok("0.08", "", {Decimal("0.075")})


def test_template_cards_always_pass_the_fact_check(ranked, schizo_target):
    cands, scores, _ = ranked
    for analog_id in scores.index:
        f = facts_of(ranked, schizo_target, analog_id)
        assert summarize.fact_check(summarize.template_card(f), f, NAMES) == [], analog_id


def test_known_names_from_the_pool_and_drugsfda(tmp_path):
    processed, raw = tmp_path / "processed", tmp_path / "raw"
    processed.mkdir()
    pd.DataFrame({"brand_name": ["Rexulti"], "generic_name": ["brexpiprazole"],
                  "sponsor": ["OTSUKA PHARMACEUTICAL CO LTD"], "dosage_form": ["TABLET"],
                  "indication": ["REXULTI is indicated for schizophrenia and rheumatoid arthritis"]}) \
        .to_csv(processed / "candidate_pool.csv", index=False)
    summarize.known_names.cache_clear()
    pool_only = summarize.known_names(processed, raw)
    assert pool_only == {"drugs": {"rexulti", "brexpiprazole"}, "companies": {"otsuka"}}
    (raw / "drugsfda" / "unzipped").mkdir(parents=True)
    (raw / "drugsfda" / "unzipped" / "Products.txt").write_text(
        "ApplNo\tProductNo\tForm\tStrength\tReferenceDrug\tDrugName\tActiveIngredient\tReferenceStandard\n"
        "021436\t001\tTABLET;ORAL\t2MG\t1\tABILIFY\tARIPIPRAZOLE\t0\n"
        "018337\t001\tTABLET;ORAL\t500MG\t0\tARTHRITIS PAIN\tACETAMINOPHEN\t0\n"
        "018337\t002\tTABLET;ORAL\t1MG\t0\tSODIUM CHLORIDE\tSODIUM CHLORIDE\t0\n", encoding="latin-1")
    summarize.known_names.cache_clear()
    n = summarize.known_names(processed, raw)
    assert {"abilify", "aripiprazole", "acetaminophen"} <= n["drugs"]
    assert not {"arthritis", "pain", "sodium", "chloride"} & n["drugs"]  # disease and salt words aren't names
    summarize.known_names.cache_clear()


def test_cache_key_changes_with_the_model_and_the_prompt(ranked, schizo_target, monkeypatch):
    f = facts_of(ranked, schizo_target, "o01_oral")
    key = summarize.cache_key(f, "gemini-a")
    assert summarize.cache_key(f, "gemini-a") == key != summarize.cache_key(f, "gemini-b")
    monkeypatch.setattr(summarize, "PROMPT", summarize.PROMPT + "Be brief.\n")
    assert summarize.cache_key(f, "gemini-a") != key


def test_a_new_model_writes_a_new_card(ranked, schizo_target, tmp_path):
    body = {"headline": "Oone ranks first: same class, schizophrenia.", "similarities": [], "differences": []}
    for name in ("gemini-a", "gemini-b"):
        fake = llm.FakeLLM({"summary_card": body})
        fake.name = name
        make(ranked, schizo_target, "o01_oral", summarize.Summarizer("gemini", llm=fake, cache_dir=tmp_path,
                                                                      scenario="torevia", names=NAMES))
        assert len(fake.calls) == 1                                    # not served from the other model's card
    assert len(list((tmp_path / "cards" / "torevia").glob("o01_oral-*.json"))) == 2
