import json
from types import SimpleNamespace

import pytest

from analog_finder import llm

CARD = {
    "title": "summary_card", "type": "object", "required": ["headline", "similarities"],
    "properties": {
        "headline": {"type": "string"},
        "similarities": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "n_shared": {"type": "integer"},
        "extra": {"type": "object", "properties": {"flag": {"type": "boolean"}, "note": {"type": ["null", "string"]}}},
    },
}


# --- FakeLLM ----------------------------------------------------------------------------------------------

def test_fake_returns_fixture_by_schema_title():
    fixture = {"headline": "Close match", "similarities": ["same class"]}
    fake = llm.FakeLLM({"summary_card": fixture})
    assert fake.generate_json("prompt 1", CARD) == fixture
    assert fake.calls == [("summary_card", "prompt 1")]


def test_fake_fixture_is_copied():
    fake = llm.FakeLLM({"summary_card": {"headline": "x", "similarities": []}})
    fake.generate_json("p", CARD)["similarities"].append("mutated")
    assert fake.generate_json("p", CARD)["similarities"] == []


def test_fake_without_fixture_returns_schema_skeleton():
    assert llm.FakeLLM().generate_json("p", CARD) == {
        "headline": "", "similarities": [], "confidence": "high", "n_shared": 0,
        "extra": {"flag": False, "note": ""}}


def test_fake_fixture_missing_required_key_fails():
    with pytest.raises(llm.LLMError, match="similarities"):
        llm.FakeLLM({"summary_card": {"headline": "x"}}).generate_json("p", CARD)


def test_fake_is_deterministic():
    assert llm.FakeLLM().generate_json("p", CARD) == llm.FakeLLM().generate_json("other prompt", CARD)


# --- get_llm ----------------------------------------------------------------------------------------------

def _env(values):
    return lambda name, default=None: values.get(name, default)


def test_get_llm_without_key_is_fake(monkeypatch):
    monkeypatch.setattr(llm, "env", _env({}))
    fake = llm.get_llm({"summary_card": {"headline": "x", "similarities": []}})
    assert isinstance(fake, llm.FakeLLM)
    assert fake.generate_json("p", CARD)["headline"] == "x"


def test_get_llm_with_key_but_no_model_fails(monkeypatch):
    monkeypatch.setattr(llm, "env", _env({"GEMINI_API_KEY": "k"}))
    with pytest.raises(ValueError, match="GEMINI_MODEL"):
        llm.get_llm()


# --- GeminiLLM (stub client, no network) ------------------------------------------------------------------

class StubModels:
    def __init__(self, text):
        self.text, self.requests = text, []

    def generate_content(self, model, contents, config):
        self.requests.append(SimpleNamespace(model=model, contents=contents, config=config))
        return SimpleNamespace(text=self.text)


def _gemini(text):
    models = StubModels(text)
    return llm.GeminiLLM("key", "gemini-test", client=SimpleNamespace(models=models)), models


def test_gemini_requests_json_with_schema():
    gem, models = _gemini(json.dumps({"headline": "h", "similarities": ["a"]}))
    assert gem.generate_json("the prompt", CARD) == {"headline": "h", "similarities": ["a"]}
    req = models.requests[0]
    assert req.model == "gemini-test" and req.contents == "the prompt"
    assert req.config.response_mime_type == "application/json"
    assert req.config.response_json_schema == CARD
    assert req.config.temperature == 0
    assert gem.name == "gemini:gemini-test"


@pytest.mark.parametrize("text", ["not json", None, json.dumps(["a list"]), json.dumps({"headline": "h"})])
def test_gemini_unusable_answer_fails(text):
    gem, _ = _gemini(text)
    with pytest.raises(llm.LLMError):
        gem.generate_json("p", CARD)
