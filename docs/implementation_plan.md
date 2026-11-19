# Analog Finder — Implementation Plan

Nov 17, 2026

## Context and goal

We build the Analog Finder as a new folder, `analog_finder/`, one component at a time in the order below. Each step merges as its own PR, with tests and docs, before the next step starts.

**Why now:** the data pipeline (`pipeline/`) is built:

- 426 analogs, 261 of them usable
- launch curves and Bass fits
- `analog_features`
- seed label reads

Journey step 2 (find comparable launches) and step 4 (weighted uptake curve) don't exist as code yet. In `data_model.md`, `target_drug`, `analog_recommendations` and `analog_weights` are all not started.

**The two stages in the diagram:**

1. **Label Research Agent:** take the analog list, pull facts from approved sources only, write a labeled CSV that a person reviews.
2. **Analog Finder:** embed the analogs and the target drug, rank them by similarity, write a summary for each of the top 5, have the forecaster confirm or reject each (a rejection fetches the next candidate), then show the uptake curve weighted by similarity.

**Finished means:** `python -m analog_finder.finder --scenario torevia` runs end to end on the example drug, the Streamlit app runs both stages, and all checks in [Final verification](#final-verification) pass. A rejected candidate loops back to a new summary, and only confirmed analogs reach the weighted curve.

**How we build it:** components are built in dependency order, each one finished properly rather than stubbed first. Every step ends with something runnable, so the step after it builds on working code. The CLI grows with each Stage 2 step: after step N it runs through stage N and stops.

## Decisions (agreed)

The team agreed to every proposal for D1–D8. These are now the rules the code follows. Step 0 writes them into `decisions.md` and updates `user_journey.md`, because the docs are the spec.

| # | Topic | Rule |
| --- | --- | --- |
| D1 | Hard filters | Hard filters run before the embedding step. They're agreed rules and keep unusable curves out of the top 5. |
| D2 | Which flags exclude | Reuse the `checks.md` funnel (the 261 usable analogs), which already excludes generic entry and late launch. No new exclusion rule. Label expansion and multi-route are warnings only. Revisit once approval letters are read. |
| D3 | Shortlist and approval | Top 5 shown, confirmed one at a time. A rejection fetches the next-ranked candidate. The forecaster can stop at 3–5 confirmed. |
| D4 | Language model's role | v1: the model writes summaries only, no re-rank. Ranking stays deterministic and testable. `rerank.py` is a pass-through for a later re-rank. |
| D5 | Curve weights | Weight = similarity score, normalized over the confirmed analogs. The forecaster can override a weight with a reason. |
| D6 | Similarity | Hybrid score: RxBERT text similarity on a profile text, plus one score per structured feature, combined with weights users can set. |
| D7 | Feature preferences | Preferences are the weights in that combination. Defaults sit in `config/scoring.yaml`; any scenario can override them. ATC class and area get low defaults (EDA: class medians don't beat the overall median). |
| D8 | Evidence used in matching | Approved values only. FDA indication text and ATC class work now. Line of therapy, dosing and competitors count once approved. |

## Folder layout and where data goes

Everything new lives in `analog_finder/`. It reads `data/processed/` and doesn't change the pipeline. Two changes from the earlier draft: the confirm/reject logic gets its own module (`finder/loop.py`) so the CLI and the app share it, and the app is split into one file per page so two people never edit the same file.

```
analog_finder/
├── README.md                 how to run each stage; contracts; links to component specs
├── requirements.txt          extra pinned deps, separate from the pipeline:
│                             google-genai, transformers, torch, streamlit, pyyaml, pytest
├── config/
│   ├── approved_sources.yaml the diagram's "Approved source list" (data_sources.md 6–10)
│   └── scoring.yaml          filter switches, feature weights (D7), top_k = 5, embedding model
├── scenarios/
│   └── torevia.yaml          target_drug profile + optional preference weights
├── io.py                     load processed tables + APPROVED evidence; write scenario outputs
├── llm.py                    thin Gemini wrapper; FakeLLM for tests and offline runs
│
├── finder/                   STAGE 2: Analog Finder
│   ├── target.py             load and check the target drug
│   ├── filters.py            hard filters (D1, D2); holdout removal
│   ├── embed.py              profile text → vector (TF-IDF and RxBERT, swappable)
│   ├── score.py              hybrid similarity + per-feature breakdown
│   ├── rerank.py             pass-through placeholder for a later re-rank (D4)
│   ├── loop.py               NEW: candidate queue, confirm / reject / next, decision log
│   ├── curve.py              weights + weighted uptake curve + band + Bass table
│   ├── summarize.py          one summary card per candidate
│   └── __main__.py           python -m analog_finder.finder --scenario torevia
│
├── research/                 STAGE 1: Label Research Agent
│   ├── queue.py              which analogs and fields still need reads
│   ├── sources.py            fetch only from approved sources (rejects anything else)
│   ├── extract.py            per field → value, quote, source_url, source_type
│   ├── verify.py             is the quote verbatim on the source page?
│   └── __main__.py           python -m analog_finder.research ...
│
├── app/                      Streamlit, one file per page
│   ├── Home.py               streamlit run analog_finder/app/Home.py
│   └── pages/
│       ├── 1_Review.py       Stage 1 review screen
│       └── 2_Finder.py       finder + confirm loop + curve
├── evaluate.py               leave-one-out holdout
├── tests/                    pytest, no network
└── docs/components/          one short spec per component (template in Working agreements)
```

| What | Where | In git? |
| --- | --- | --- |
| Stage 1 output | The existing `data/reference/analog_evidence.csv`, as new rows with `approved=false`. Never overwrites an approved row. | Yes |
| Embedding cache | `data/cache/analog_embeddings.npz`, rebuilt in minutes | No |
| Per-forecast outputs | `data/scenarios/<scenario>/`: `analog_recommendations.csv`, `analog_weights.csv`, `uptake_curve.csv` (columns as in `data_model.md`) | Yes, for the demo scenario only |

## Build sequence

We build in 17 steps, each finished and merged before the next. The order follows the data: the deterministic finder first, so the CLI runs end to end on Torevia at step 7, then the research agent, then the interactive app, then scaling up.

| Phase | Step | Component | Checkpoint after this step |
| --- | --- | --- | --- |
| A · Foundations | 0 | Docs as spec | Docs describe what we build |
| | 1 | Plumbing | `pytest` passes offline |
| B · Finder core (offline, deterministic) | 2 | Target drug | Torevia loads and validates |
| | 3 | Hard filters + holdout | Torevia's 5 analogs pass the filters |
| | 4 | Profile text + TF-IDF embeddings | CLI runs through embedding |
| | 5 | Hybrid scoring | CLI prints a ranked list |
| | 6 | Confirm loop (CLI) | `--auto-confirm` confirms top 5 |
| | 7 | Weights + uptake curve | **CLI runs end to end** (checks 2, 3) |
| | 8 | Evaluation harness | Check 6 (TF-IDF, structured only) |
| | 9 | RxBERT embedder | Check 6 with RxBERT; defaults set |
| C · Research agent (Stage 1 + review) | 10 | Approved-source gate + queue | Unlisted sites refused |
| | 11 | Extraction + quote checks | Check 4 |
| | 12 | Review screen (app page 1) | Torevia's 20 values reviewed |
| D · Interactive finder | 13 | Summaries | Cards in CLI, offline template works |
| | 14 | Finder screen (app page 2) | Check 5 |
| E · Close out | 15 | Scale Stage 1 + re-tune | Evaluation rerun on 41 nervous-system analogs |
| | 16 | Final docs + demo | All checks pass on a fresh clone |

Stage 1 (phase C) needs only the plumbing from step 1. If the team later wants two people working at once, phase C can run alongside phase B without changing anything else in the plan.

## Step-by-step detail

Each step lists its goal, the files it builds, what goes in and comes out, what it depends on, the questions the builder should settle first (write the answers into the component spec), and when it counts as done. Schemas referenced here are spelled out in [Shared contracts](#shared-contracts).

### Phase A — Foundations

#### Step 0. Write the agreed spec into the docs

**Goal:** the docs describe what we're about to build, before any code.

**Builds:** `decisions.md` (log D1–D8), `user_journey.md` (step 2: top 5 + confirm loop; step 4: similarity weights; remove the settled open question), `data_model.md` (`target_drug`, `analog_recommendations`, `analog_weights` columns; the agent in `analog_evidence`; `data/cache/` and `data/scenarios/`), `docs/analog_finder_architecture.png`, `.gitignore` (`data/cache/`), `.env.example` (`GEMINI_MODEL`, `SEC_USER_AGENT`).

**Depends on:** PR #6 (`c/seed-review`) merged first, so its quote checker is on main.

**Questions to settle:**

- Are the output columns in `data_model.md` complete for the schemas in Shared contracts (decision reason, weight override, band columns)? Add what's missing here, not later.

**Done when:** docs merged; every later step can point to them as the spec.

#### Step 1. Plumbing: config, data loading, language model wrapper

**Goal:** one place to load config, processed tables and approved evidence, and one wrapper for Gemini, so later steps never reimplement them.

**Builds:** `requirements.txt`, `config/scoring.yaml`, `config/approved_sources.yaml`, `io.py`, `llm.py` (`GeminiLLM` + `FakeLLM`), `tests/conftest.py` with small fixture tables.

**Input:** `data/processed/` (analog_features, candidate_pool, launch_curves, bass_fits, analogs); `data/reference/analog_evidence.csv`.

**Output:** `io.load_tables()`, `io.load_approved_evidence()` (wide: one row per analog, one column per approved field), `io.load_config(scenario)` (defaults merged with scenario overrides), `io.write_scenario_outputs()`; `llm.get_llm()` returning Gemini when a key is set, else `FakeLLM`.

**Questions to settle:**

- Two approved rows for the same analog and field: which wins (latest `approved_at`)?
- Scenario overrides: do they replace only the keys they name (recommended) or the whole block?
- What does `FakeLLM` return: fixed JSON per prompt type, so tests are deterministic?

**Done when:** `pytest` passes offline; loading Torevia's config prints merged weights.

### Phase B — Analog Finder core (deterministic, offline)

#### Step 2. Target drug

**Goal:** load the drug we're forecasting and check it has what the finder needs.

**Builds:** `finder/target.py`, `scenarios/torevia.yaml` (fields from `example_drug.md`).

**Input:** scenario YAML. **Output:** a `Target` record (Shared contracts).

**Questions to settle:**

- Which fields are required (indication text, ATC 4, route group) and which are optional?
- Pre-launch values such as # competitors and order of entry are estimates for a target. Do we allow them, and mark them as estimates?
- Is route group derived the same way the pipeline derives it for analogs? It must be, or the filter will silently drop matches.

**Done when:** a bad or missing required field fails with a clear message; tests cover both.

#### Step 3. Hard filters and holdout

**Goal:** reduce 426 analogs to usable ones in the target's route group, carrying warnings.

**Builds:** `finder/filters.py`; CLI `--holdout <analog_id>`.

**Input:** analog tables + `Target`. **Output:** candidate table with warning flags (Shared contracts).

**Questions to settle:**

- Does the filter read the funnel's existing "usable" result, or recompute it? Reading it is safer: one definition.
- Holdout runs before filtering. Does it also need to remove the held-out analog's evidence rows from any fitted step (TF-IDF vocabulary)?
- What happens if fewer than about 10 candidates survive (top 5 plus replacements)? Warn and continue, or stop?

**Done when:** Latuda, Rexulti, Vraylar, Caplyta and Lybalvi pass for Torevia; `--holdout latuda_oral` removes Latuda; tests cover each flag.

#### Step 4. Profile text and TF-IDF embeddings

**Goal:** turn each analog and the target into comparable vectors, starting with the simple baseline.

**Builds:** `finder/embed.py` with `build_profile_text()` and an `Embedder` interface; `TfidfEmbedder`; embedding cache.

**Input:** candidate table + approved evidence + `Target`. **Output:** `{analog_id: vector}` plus the target vector.

**Questions to settle:**

- Exact profile template: indication at approval, ATC 4/3 class names, route and dosage form, then approved line of therapy, dosing and competitors. A missing field: drop the sentence (recommended) or write "unknown"?
- TF-IDF: fit on the analog corpus only, then transform the target? Fitting on both changes every vector each time the target changes.
- Cache key: model name + hash of the profile text, so an approval invalidates only that analog.

**Done when:** the CLI with `--embedder tfidf` stops after embedding and reports the count; tests check the template and the cache.

#### Step 5. Hybrid scoring

**Goal:** rank candidates by the weighted average of feature similarities (D6, D7).

**Builds:** `finder/score.py`, `finder/rerank.py` (pass-through), feature weights in `scoring.yaml`.

**Input:** candidate table, vectors, `Target`, merged weights. **Output:** ranked score table with the per-feature breakdown.

$$
\text{similarity} = \frac{\sum_i w_i \, s_i}{\sum_i w_i}
$$

The sums run over features that both the target and the analog have. A missing feature is left out, not scored as a mismatch.

**Questions to settle:**

- How each feature becomes a 0–1 score: text = cosine rescaled to 0–1; ATC 4, ATC 3, area = 1/0; line of therapy = exact match, or partial credit for an adjacent line?; dosing frequency = ordinal distance?; # competitors = 1 / (1 + |difference|)?; order of entry = same scheme?
- An analog scored on 2 features can outrank one scored on 7. Do we require a minimum `n_features_used`, or shrink scores with few features?
- Tie-break by `analog_id` so runs are reproducible.

**Done when:** tests cover the formula, missing features and weight overrides; Torevia's 5 known analogs rank near the top with TF-IDF.

#### Step 6. Confirm loop (command line)

**Goal:** the D3 loop as plain code, shared later by the app.

**Builds:** `finder/loop.py` (`CandidateQueue`); CLI `--auto-confirm` and an interactive prompt.

**Input:** ranked score table. **Output:** decision log written as `analog_recommendations.csv`.

**Questions to settle:**

- Reject reasons: free text, or a short fixed list plus text (easier to analyse later)?
- What happens when the candidates run out? Can a rejected analog be restored?
- Can a session resume from an existing `analog_recommendations.csv`?

**Done when:** a test rejects candidate 2 and sees candidate 6 offered; `--auto-confirm` confirms the top 5.

#### Step 7. Weights and uptake curve

**Goal:** turn confirmed analogs into the weighted curve (D5).

**Builds:** `finder/curve.py`.

**Input:** confirmed analogs + scores, launch curves, Bass fits, optional weight overrides. **Output:** `analog_weights.csv`, `uptake_curve.csv`, Bass table.

**Questions to settle:**

- Analogs with fewer than 21 non-provisional quarters: average over the analogs available in each quarter, and record `n_analogs` per quarter?
- With an override, are the other weights rescaled so the total stays 1?
- Is the band the plain min–max of the confirmed analogs (as agreed), even when one analog has a tiny weight?

**Done when:** the full CLI writes all three outputs to `data/scenarios/torevia/`; weights sum to 1; tests cover overrides and short curves.

#### Step 8. Evaluation harness

**Goal:** measure whether the finder beats the median-of-all-analogs baseline (0.18 of peak in the EDA).

**Builds:** `evaluate.py`.

**Input:** all usable analogs; a choice of embedder and weights. **Output:** a table of error per method and baseline.

**Questions to settle:**

- Which analogs are held out: only those with at least Q0–Q12 of data?
- ATC 4 baseline when the held-out analog is alone in its class: fall back to the overall median?
- Is the result stable enough to pick weights from 261 holdouts, or do we report a spread?

**Done when:** `python -m analog_finder.evaluate` prints TF-IDF and structured-only errors next to both baselines; the all-analog baseline comes out near 0.18.

#### Step 9. RxBERT embedder

**Goal:** add the pharma text model and let the evaluation decide the default.

**Builds:** `RxBertEmbedder` in `embed.py`; `--embedder rxbert`.

**Questions to settle:**

- RxBERT is a fill-mask model. How do we pool a sentence vector: mean of the last hidden layer (recommended) or the CLS token?
- The model card states no license. Who checks, and is TF-IDF the demo default until it's cleared?
- Profile texts over 512 tokens: truncate, or chunk and average?

**Done when:** the evaluation table includes RxBERT; `scoring.yaml` defaults updated to the best method, with the numbers recorded in `decisions.md`.

### Phase C — Label Research Agent (Stage 1)

#### Step 10. Approved-source fetching and the work queue

**Goal:** a single gate that every fetch goes through, and a list of what still needs reading.

**Builds:** `research/sources.py`, `research/queue.py`; reuses `pipeline.common` throttling, caching and manifest.

**Input:** `approved_sources.yaml`; `analog_features.csv` (where `enough_data`) joined with `candidate_pool.csv`; existing evidence. **Output:** `fetch(url)` that refuses unlisted sites; a queue of (analog_id, field) pairs with no approved value.

**Questions to settle:**

- Allow-list matching: exact host, or host plus subdomains? Is a redirect re-checked against the list? (It should be.)
- Gemini web search returns URLs we don't control. Filter them through `sources.py` before fetching, and log what was dropped?
- Queue order: Torevia's 5 analogs, then the 41 nervous-system analogs, then the rest. Configurable by flag?

**Done when:** tests show an unlisted URL and an unlisted redirect both refused; `queue` for `latuda_oral` lists its 4 fields.

#### Step 11. Extraction and quote checks

**Goal:** fill the four label-read fields with a value, a verbatim quote and a link, written as unapproved rows.

**Builds:** `research/extract.py`, `research/verify.py` (reusing PR #6's quote checker), `research/__main__.py`.

| Field | Approved source | How |
| --- | --- | --- |
| Line of therapy | Original approval (ORIG) label, Indications | `pipeline.labels` downloads the label; Gemini returns value + verbatim quote as structured JSON |
| Dosing frequency | ORIG label, Dosage and Administration | Same as above |
| Launch date | Press release or SEC filing (first commercial availability) | SEC EDGAR full-text search + Gemini web search, kept only if the site is approved; page fetched and quote checked. "Expected to be available" is labeled a forecast, never a launch date |
| # competitors at launch | Drugs@FDA approval history | Gemini proposes the list; code checks each approval date against Drugs@FDA. Marked `[derived, verify each date]` |

**Input:** queue items. **Output:** evidence rows (Shared contracts) appended to `analog_evidence.csv` with `approved=false`.

**Depends on:** the line-of-therapy category change, as its own PR before this step (decisions.md open question, 2026-11-18): line of therapy stored as `first` / `later` / `any` / `not stated`, returned by the agent with its quote and approved by the reviewer; `score.py` matches on the category and keeps its keyword reader as a cross-check. It changes Shared contracts (approved evidence, `Target`) and categorizes the seed 8 values.

**Questions to settle:**

- What counts as a competitor: same ATC 4, same indication, or both? This decides the number, so agree it before extraction.
- Quote-check normalization: whitespace, hyphenation and PDF line breaks. Where is the line between "verbatim" and "partial"?
- Re-runs: skip an (analog, field) that already has an unapproved row with the same value, so the CSV doesn't fill with duplicates?
- No ORIG label found: write nothing, or a row saying so for the reviewer?

**Done when:** `python -m analog_finder.research --analogs latuda_oral` adds rows with quotes; label quotes check as verbatim; `git diff` shows no approved row changed; tests run on `FakeLLM` and saved pages.

#### Step 12. Review screen (app page 1)

**Goal:** a person approves, edits or rejects each value before anything uses it.

**Builds:** `app/Home.py`, `app/pages/1_Review.py`.

**Input:** unapproved evidence rows. **Output:** the same rows updated with `approved=true`, `approved_by`, `approved_at`, or marked rejected.

**Questions to settle:**

- If a reviewer edits a value, does the agent's quote stay attached, or must they paste their own?
- Two people reviewing at once means two edited copies of a CSV in git. Rule: one person reviews and commits a given batch.
- Sort order: by analog, so a reviewer reads one label once for several fields?

**Done when:** approving one row saves it as approved; Torevia's 20 values are reviewed; spreadsheet review still works on the same file.

### Phase D — Interactive finder

#### Step 13. Summaries

**Goal:** a short card per candidate explaining why it ranked where it did.

**Builds:** `finder/summarize.py` (template card first, then Gemini).

**Input:** one score-table row with its breakdown, the `Target`, the analog's flags and approved evidence. **Output:** a summary card (Shared contracts).

**Questions to settle:**

- How do we stop the model stating facts it wasn't given? Pass facts as JSON only, and check after generation that every drug name and number in the text is in the input.
- Cache cards by (scenario, analog_id, hash of inputs) so a rejection loop doesn't re-call the API for cards already written.
- Card length and tone: who signs off on the template?

**Done when:** the CLI shows a card for each of the top 5 and for a replacement after a rejection; without an API key, template cards appear and everything still runs.

#### Step 14. Finder screen (app page 2)

**Goal:** the forecaster runs the D3 loop and sees the D5 curve in the browser.

**Builds:** `app/pages/2_Finder.py`, using `loop.py`, `summarize.py` and `curve.py` unchanged.

**Questions to settle:**

- Where does loop state live across Streamlit reruns: session state, rebuilt from `analog_recommendations.csv` on load?
- Weight override: a number input plus a required reason field, saved to `analog_weights.csv`?
- Should the page show the curve before 5 are confirmed (from 3, per D3)?

**Done when:** rejecting a candidate shows the 6th-ranked one with a new card; confirming 5 shows the weighted curve, band, Bass table and caveats.

### Phase E — Scale up and close out

#### Step 15. Scale Stage 1 and re-tune

**Goal:** enough approved structured features that the hybrid score has something to work with.

**Builds:** no new modules. Run Stage 1 on the 41 usable nervous-system analogs (164 values to review), rerun `evaluate.py`, update `scoring.yaml` defaults.

**Questions to settle:**

- Who reviews the 164 values, and in what batches?
- Rule for changing defaults: adopt a new weighting only if its error beats the current one by a margin we set now, not after seeing results.

**Done when:** the evaluation table is rerun and recorded in `decisions.md`, with the defaults it chose.

#### Step 16. Final docs and demo

**Builds:** `analog_finder/README.md` (how to run, contracts, links to component specs), `CLAUDE.md` current state and a log line, committed demo outputs in `data/scenarios/torevia/`.

**Done when:** every check in Final verification passes on a fresh clone.

## Shared contracts

These are the handoffs between modules, and changing one breaks the step downstream. A PR that changes a contract updates this table and the affected tests in the same PR. Where a file is described in `data_model.md`, that doc wins; Step 0 makes the two match. The column lists below are proposals for the builder of each step to confirm.

| Handoff | From → to | Shape |
| --- | --- | --- |
| Merged config | `io.load_config` → all | dict: `filters`, `weights` (feature → float), `top_k`, `embedder`, `embedding_models`, `paths` (absolute), `scenario` |
| Approved evidence (wide) | `io` → embed, score, summarize | one row per `analog_id` (the index); columns `line_of_therapy`, `dosing_frequency`, `launch_date`, `n_competitors_at_launch` (the evidence field names), each with `<field>_quote` and `<field>_url`; NaN when not approved |
| `Target` | `target.py` → filters, embed, score, summarize | `name`, `indication_text`, `atc4`, `atc3`, `area`, `route_group`, `dosage_form`, optional `line_of_therapy`, `dosing_frequency`, `n_competitors` (+ `is_estimate`), `order_of_entry`, `preferences` |
| Candidate table | `filters.py` → embed, score | one row per usable analog in the route group: `analog_id`, `drug_name`, `atc4`, `atc3`, `area` (codes, `; `-separated for multi-class analogs), `atc4_name`, `atc3_name`, `area_name`, `route_group`, `dosage_form`, `indication_text`, plus flags `warn_label_expansion`, `warn_multi_route`, `low_volume`, `peak_not_confirmed`, `weak_bass_fit` |
| Profile text | `embed.build_profile_text` | `str`, same template for target and analogs; fields with no approved value are omitted |
| `Embedder` | `embed.py` → score | `.fit(texts)`, `.encode(texts) -> np.ndarray`, `.name`; cache key = `name` + text hash |
| Score table | `score.py` → rerank, loop, summarize, evaluate | sorted by `similarity` desc, then `analog_id`: `analog_id`, `rank`, `similarity`, one `s_<feature>` column per feature (NaN if not used), `n_features_used` |
| Decision log | `loop.py` → `analog_recommendations.csv` | `scenario`, `analog_id`, `rank`, `similarity`, `decision` (shown / confirmed / rejected), `reason`, `decided_by`, `decided_at` |
| Weights | `curve.py` → `analog_weights.csv` | `analog_id`, `similarity`, `weight` (sums to 1), `override_weight`, `override_reason` |
| Uptake curve | `curve.py` → `uptake_curve.csv` | `quarter` (0–20), `weighted_share_of_peak`, `band_min`, `band_max`, `n_analogs`, `n_upper_bound` |
| Summary card | `summarize.py` → CLI, app | `analog_id`, `headline`, `similarities[]`, `differences[]`, `score_breakdown`, `flags[]`, `sources[]` (quote, url), `generated_by` (gemini / template) |
| Evidence row | `research/` → `analog_evidence.csv` | existing columns from `pipeline/build.py`, plus `quote`, `source_url`, `source_type`, `quote_check` (verbatim / partial / not_checked), `extracted_by` (agent / seed / human), `approved`, `approved_by`, `approved_at` |
| LLM | `llm.py` → extract, summarize | `.generate_json(prompt, schema) -> dict`, `.name`; the schema's `title` names the prompt type; `FakeLLM` returns fixed fixtures by that title (a schema skeleton when there is none); `LLMError` when an answer lacks the schema's required keys |

## Evaluation

The finder counts as an improvement if its weighted curve predicts a held-out analog's first 3 years better than the median of all analogs (error 0.18 of peak in Grace's `analog_similarity` EDA). This also answers the user journey's open question on evaluation.

- **Method:** hold out one usable analog, run filters, scoring and the top 5 with auto-confirm, then predict the held-out analog's Q0–Q12 share of peak from the weighted curve.
- **Error:** mean absolute gap in share of peak, the same measure the EDA used.
- **Baselines:** the median of all analogs, and the median of the held-out analog's ATC 4 class.
- **Comparisons:** TF-IDF (Step 8), structured features only (Step 8), RxBERT (Step 9). The results set the default weights in `scoring.yaml`.
- **When it runs:** first in Step 8, again in Step 9, and again in Step 15 once Stage 1 covers the nervous-system pool. Structured features are thin until then, so early results will understate the hybrid score.

## Working agreements

One step = one branch = one PR, merged in step order. Whoever picks up a step owns it until it merges.

**Git**

- Branch from the latest `main`: `<initials>/step-<NN>-<name>`, e.g. `ab/step-05-scoring`.
- Each PR contains code, tests, its component spec, and every doc it changes. That's the existing CLAUDE.md rule.
- At least one other team member reviews before merge. The reviewer runs the step's "Done when" check, not just reads the diff.
- `pytest analog_finder/tests` stays green on `main` after every merge, offline.
- Each Stage 2 step leaves `python -m analog_finder.finder --scenario torevia --embedder tfidf` running as far as that step goes.
- Never commit `.env`, `data/cache/` or your own `SEC_USER_AGENT`.

**Component spec** (first commit of each step, in `docs/components/<name>.md`, half a page at most):

```markdown
# <component>
Purpose: one sentence
Input: what it reads (link to Shared contracts)
Output: what it returns or writes (link to Shared contracts)
Depends on: steps / files
Decisions made: answers to this step's "Questions to settle"
Open questions: anything still undecided, with who decides
Done when: copied from the plan, ticked at merge
```

**Shared files** (edits by anyone, so coordinate before changing):

| File | Rule |
| --- | --- |
| Shared contracts (this doc) | Change it in the same PR as the code, and flag it in the PR title |
| `config/scoring.yaml` | Weights change only through an evaluation result recorded in `decisions.md` |
| `llm.py` | Interface changes need a heads-up to whoever owns extract and summarize |
| `analog_evidence.csv` | One reviewer per batch commits it; never edit approved rows by hand |
| `data_model.md`, `decisions.md` | Append, don't rewrite; one line per decision with the step number |

**Reuse, no new code:**

- `pipeline/common.py`: `env()` for keys; throttled, cached downloads with a manifest; data paths; quarter helpers.
- `pipeline/labels.py`: finding and downloading the ORIG label, plus PR #6's quote check.
- `pipeline/bass.py`: `bass_cdf` to draw fitted curves.
- `pipeline/build.py`: the `analog_evidence` loader and column list, so there is one schema.
- `data/processed/`: analog_features, candidate_pool, launch_curves, bass_fits, analogs. Approved evidence is joined in when the finder runs, so an approval shows up without a full `pipeline.build`.

The Gemini model and package versions are checked against current docs when each step is written.

## Final verification

The project is done when all six checks pass on a fresh clone. Each check first becomes possible at the step shown, and should be run then, not saved for the end.

| # | Check | First possible at |
| --- | --- | --- |
| 1 | `pytest analog_finder/tests` passes offline with `FakeLLM`, covering: filters and scoring math; a rejection pulling the next candidate; weights summing to 1; the approved-source list refusing other sites; the quote checker | Grows with every step; complete at 13 |
| 2 | `python -m analog_finder.finder --scenario torevia --auto-confirm --embedder tfidf` writes `data/scenarios/torevia/` with 5 confirmed analogs, weights summing to 1, and a Q0–Q20 curve with a band. Latuda, Rexulti, Vraylar, Caplyta and Lybalvi pass the filters | 7 |
| 3 | `--holdout latuda_oral` leaves Latuda out of every output | 7 |
| 4 | `python -m analog_finder.research --analogs latuda_oral` adds `approved=false` rows with quotes; label quotes check as verbatim; `git diff` shows no approved row changed | 11 |
| 5 | `streamlit run analog_finder/app/Home.py`: approve one row and see it saved; in the finder, reject a candidate and see the 6th-ranked one with a new summary; confirm 5 and see the weighted curve | 14 |
| 6 | `python -m analog_finder.evaluate` prints the holdout error for each method next to the all-analog baseline, which comes out near 0.18 | 8 (RxBERT row from 9) |

## Sources

- RxBERT model card (Hugging Face), `seldas/rxbert-v1`
- Wu et al., RxBERT paper (PMC)
- Repo docs on `main` at `13f90f1`: `user_journey.md`, `data_model.md`, `decisions.md`, `example_drug.md`; the EDA write-ups on `eda`; PR #6 on `c/seed-review`
- Earlier draft of this plan (superseded by this version)
