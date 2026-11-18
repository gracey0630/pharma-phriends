# plumbing (step 1)
Purpose: one place to load config, processed tables and approved evidence, and one wrapper for the language model, so later steps never reimplement them.

Input:
- `analog_finder/config/scoring.yaml` (defaults) and `analog_finder/scenarios/<scenario>.yaml` (overrides)
- `data/processed/`: analog_features, candidate_pool, launch_curves, bass_fits, analogs
- `data/reference/analog_evidence.csv`
- `.env`: `GEMINI_API_KEY`, `GEMINI_MODEL` (optional)

Output ([Shared contracts](../../../docs/implementation_plan.md#shared-contracts)):
- `io.load_config(scenario)` → merged config: `filters`, `weights`, `top_k`, `embedder`, `embedding_models`, `paths` (absolute), `scenario`
- `io.load_tables()` → `{name: DataFrame}` for the five processed tables
- `io.load_approved_evidence(analog_ids=None)` → wide approved evidence, index `analog_id`, columns `<field>`, `<field>_quote`, `<field>_url` for `line_of_therapy`, `n_competitors_at_launch`, `launch_date`, `dosing_frequency`
- `io.write_scenario_outputs(scenario, {name: df})` → `data/scenarios/<scenario>/<name>.csv`, names limited to `analog_recommendations`, `analog_weights`, `uptake_curve`
- `llm.get_llm()` → `GeminiLLM` when `GEMINI_API_KEY` is set, else `FakeLLM`; both have `.generate_json(prompt, schema) -> dict` and `.name`
- `python -m analog_finder.io --scenario torevia` prints the merged config and what loads

Depends on: step 0 docs; `pipeline/build.py` (`EVIDENCE_COLS`, `EVIDENCE_FIELDS`: one evidence schema); `pipeline/common.py` (`ROOT`, `env()`).

Decisions made:
- **Two approved rows for one analog and field:** the latest `approved_at` wins. Rows without `approved_at` (all current rows: the column doesn't exist yet) count as oldest, and ties go to the later row in the file, as in `pipeline/features.py`. Once step 11 adds `approved_at`, a dated approval beats an undated one.
- **Scenario overrides replace only the keys they name**, recursing into nested blocks. `preferences` overrides feature weights; `config` overrides any other `scoring.yaml` key. An unknown key is an error, so a typo (`atc_4`) fails instead of being ignored. Weights must be numbers ≥ 0.
- **FakeLLM** returns a fixture keyed by the schema's `title` (the prompt type, e.g. `summary_card`), deep-copied; with no fixture it returns a skeleton of the schema (first enum value, `""`, `0`, `False`, `[]`). Deterministic and offline. Both LLMs check the schema's `required` keys are present and raise `LLMError` otherwise.
- **Gemini** is called with `response_mime_type="application/json"`, `response_json_schema=<schema>`, temperature 0 (google-genai 3.4.0). A key without `GEMINI_MODEL` is an error, not a silent default, because model ids change.
- **Evidence field name** is `n_competitors_at_launch` (as in `analog_evidence.csv` and data_model.md), not `n_competitors`; the plan's contract is updated to match. The scoring feature stays `n_competitors`.
- **Default weights in `scoring.yaml` are provisional** (low for ATC class and area, 1.0 otherwise) until step 5 confirms them.
- **Dependencies** live in `analog_finder/requirements.txt` (`-r ../requirements.txt` plus google-genai, pyyaml, pytest); scikit-learn, transformers, torch and streamlit are added by the steps that need them.

Open questions:
- Rows marked rejected in review (step 12) need a representation in `analog_evidence.csv`; until then "not approved" covers them. Decides: step 12 owner.
- `pipeline/features.py` resolves duplicate approvals by file order only; once `approved_at` exists, it should use the same rule as `io`. Decides: step 11 owner.

Done when: `pytest analog_finder/tests` passes offline ✅ (37 tests); loading Torevia's config prints merged weights ✅ (`python -m analog_finder.io --scenario torevia`).
