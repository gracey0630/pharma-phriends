"""One interface to the language model: `.generate_json(prompt, schema) -> dict`.

GeminiLLM calls Gemini with structured JSON output. FakeLLM returns fixed answers, so tests and runs without an
API key are deterministic and offline. Callers use get_llm() and never import google-genai themselves.

Each schema carries a `title` (e.g. "evidence_extraction", "summary_card"): it names the prompt type, which is how
FakeLLM picks its fixture.
"""
import copy
import json

from pipeline.common import env


class LLMError(RuntimeError):
    """The model's answer couldn't be used (not JSON, or missing required keys)."""


def _check_required(answer, schema):
    if not isinstance(answer, dict):
        raise LLMError(f"expected a JSON object for '{schema.get('title', '?')}', got {type(answer).__name__}")
    missing = [k for k in schema.get("required", []) if k not in answer]
    if missing:
        raise LLMError(f"answer for '{schema.get('title', '?')}' is missing required keys {missing}")
    return answer


def skeleton(schema):
    """A minimal value that matches a JSON schema: first enum value, "", 0, False, [] or an object of those."""
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type", "object")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "null")
    if kind == "object":
        return {k: skeleton(v) for k, v in schema.get("properties", {}).items()}
    return {"string": "", "integer": 0, "number": 0, "boolean": False, "array": [], "null": None}[kind]


class FakeLLM:
    """Offline stand-in. Returns `fixtures[schema['title']]` (a deep copy), else a skeleton of the schema.

    `calls` records (title, prompt) for every call, so tests can check what was asked.
    """
    name = "fake"

    def __init__(self, fixtures=None):
        self.fixtures = fixtures or {}
        self.calls = []

    def generate_json(self, prompt, schema):
        title = schema.get("title", "")
        self.calls.append((title, prompt))
        answer = copy.deepcopy(self.fixtures[title]) if title in self.fixtures else skeleton(schema)
        return _check_required(answer, schema)


class GeminiLLM:
    """Gemini via the google-genai SDK, with JSON output constrained to the schema. Temperature 0."""

    def __init__(self, api_key, model, client=None):
        if not model:
            raise ValueError("GEMINI_MODEL is not set: add it to .env (see .env.example)")
        if client is None:
            from google import genai  # imported here so offline runs and tests don't need the SDK loaded
            client = genai.Client(api_key=api_key)
        self.client = client
        self.model = model
        self.name = f"gemini:{model}"

    def generate_json(self, prompt, schema):
        from google.genai import types
        config = types.GenerateContentConfig(
            response_mime_type="application/json", response_json_schema=schema, temperature=0)
        response = self.client.models.generate_content(model=self.model, contents=prompt, config=config)
        try:
            answer = json.loads(response.text)
        except (TypeError, json.JSONDecodeError) as e:
            raise LLMError(f"Gemini returned no valid JSON for '{schema.get('title', '?')}': {e}") from e
        return _check_required(answer, schema)


def get_llm(fixtures=None):
    """GeminiLLM when GEMINI_API_KEY is set (.env or environment), else FakeLLM(fixtures)."""
    key = env("GEMINI_API_KEY")
    if not key:
        return FakeLLM(fixtures)
    return GeminiLLM(key, env("GEMINI_MODEL"))
