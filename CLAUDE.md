# Pharma Phriends: Launch Analog and Input Tool

Team project. Helps a pharma forecaster choose and defend two launch-forecast inputs: the **ceiling** (peak patients, M) and the **trajectory** (uptake shape, Bass p/q from analog launches).

## Read first
1. [docs/user_journey.md](docs/user_journey.md): what the tool does, step by step (draft; changes via PR)
2. [docs/data_sources.md](docs/data_sources.md): what we pull, source rules, freshness checks
3. [docs/data_model.md](docs/data_model.md): tables, dependencies, workstreams, build status
4. [docs/decisions.md](docs/decisions.md): decision log and open questions
5. [docs/implementation_plan.md](docs/implementation_plan.md): how the Analog Finder (`analog_finder/`) is built: 17 steps, one PR each, agreed decisions D1–D8, shared contracts between modules

**The docs are the spec.** Build code to match them. If the design needs to change, change the doc in the same PR.
## Fixed scope
- US only; novel NDA/BLA brands (NME or new biologic), first indication, no generic entry in the first 3 years
- Pharmacy-dispensed, self-administered (oral or self-injected); no clinic-administered drugs
- Unit = dispensed prescriptions (TRx); analog curves are Medicaid (SDUD), Medicare Part D for cross-checks only
- Analog pool: launches from 2010 onward
- Out of scope for now: fills conversion, access scenarios, Monte Carlo

## Conventions
- Key: `analog_id` = `brand_key` + `route_group` (e.g. `skyrizi_sc`). One analog = brand × route group.
- Time series in long format: `analog_id, source, payer, period, metric, value, pulled_at`
- Never mix Medicaid and Medicare in one curve
- Suppressed SDUD rows (< 11 Rx) are imputed at 5 Rx (bounds 1 and 10, kept as `trx_low` / `trx_high`); `trx` is that mid estimate and `trx_reported` the visible sum. A quarter with no SDUD row is 0 TRx. Both readings are model assumptions, not confirmed with CMS
- Indication, dosing and class come from the **original** approval label (Drugs@FDA ORIG), never DailyMed (current label)
- Agent-extracted values are saved with quote + source link and need human approval before use; the agent fetches from the approved-source list only (data_sources.md) and never overwrites an approved row
- The Analog Finder matches on approved evidence only. Ranking is deterministic; the language model writes summary cards and doesn't re-rank (D4)
- Folders: `data/raw/<source>/` downloads, unchanged, plus a manifest (gitignored); `data/reference/` manual / approved tables; `data/processed/` tables built by code; `data/scenarios/<scenario>/` per-forecast outputs (committed for `torevia` only); `data/cache/` embedding cache (gitignored)
- Code: `pipeline/` builds the data; `analog_finder/` (planned) reads `data/processed/` and never changes the pipeline
- Secrets in `.env` (gitignored); see `.env.example`

## Status & handoff
**Last update: 2026-11-18 (Joshua, `jm/step-02-07-finder-core`).** Keep "Current state" current; add a dated line to the log when you hand off.

### Current state
**What exists** (`data/processed/`, specs in [data_model.md](docs/data_model.md)):
- `analogs.csv`: the v1 analog table, 426 analogs (332 oral, 94 sc) × the 23 schema-sheet columns. The pool is every NME / new BLA in the FDA NME compilation approved 2010–2025, split by route group.
- `sdud_quarterly.csv`: Medicaid TRx by quarter, 2010Q1–2026Q1 (406 analogs have Rx, 28 of them only in suppressed rows). `ndc_map.csv`: 1,513 NDCs and how each was matched.
- `launch_curves.csv`: TRx and share of peak, Q0–Q20; share of the Q0–Q28 peak. `analog_features.csv`: launch quarter, peak (`peak_confirmed`), data quality, distortion flags, `enough_data`. `bass_fits.csv`: p, q, m for the 268 analogs with enough data.
- `indication_history.csv`: possible label expansions. `medicaid_enrollment.csv`: enrollment by quarter with shock windows.
- `checks.md`: validation report. **261 analogs** pass the rules code can apply (213 oral, 48 sc); it also lists every NME brand left out of the pool, with the reason.
- `data/reference/analog_evidence.csv`: label reads (line of therapy, dosing, launch date, # competitors) for the 8 seed brands (Otezla, Cosentyx, Taltz, Siliq, Tremfya, Skyrizi, Sotyktu, Ibrance). 31 values with quotes and links; **27 approved** (Gabrielle, 2026-10-26), 4 launch dates waiting (below). `python -m pipeline.labels --check` checks every label quote against its label.
- Code: `pipeline/` (`fda`, `sdud`, `ndc`, `rxclass`, `enrollment`, `curves`, `features`, `bass`, `labels`, `build`, `checks`).
- **Analog Finder (`analog_finder/`), in progress:** steps 1–7 built. Plumbing (`io.py`, `llm.py`, config); the finder core in `finder/`: `target.py` (Torevia's profile in `scenarios/torevia.yaml`), `filters.py`, `embed.py` (TF-IDF), `score.py`, `rerank.py` (pass-through), `loop.py`, `curve.py`, and the CLI (`python -m analog_finder.finder`), which runs end to end offline. Demo outputs in `data/scenarios/torevia/`. Not built yet: evaluation (step 8), RxBERT (9), Stage 1 Label Research Agent (10–12), summary cards (13), Streamlit app (12, 14). Plan in [implementation_plan.md](docs/implementation_plan.md); component specs in `analog_finder/docs/components/`.

**How to run**
- Setup: Python 3.12+ (`python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt`).
- `python -m pipeline.build` rebuilds everything. The first run downloads ~600 MB (mostly SDUD) and takes about an hour; later runs take ~2 min from `data/raw/`.
- `--refresh` re-downloads every source; do this before any final build.
- `data/processed/` is committed, so you only need to rebuild to change or refresh the data.
- Label helper: `python -m pipeline.labels <ApplNo>` downloads the ORIG label and extracts its text.
- Analog Finder: `pip install -r analog_finder/requirements.txt`; `pytest analog_finder/tests` (offline, no key needed); `python -m analog_finder.io --scenario torevia` prints the merged config and what loads; `python -m analog_finder.finder --scenario torevia` runs the finder (interactive confirm loop; `--auto-confirm`, `--holdout <analog_id>`, `--until filters|embed|score|loop`, `--resume`).

**Known issues** (details in `checks.md`)
- **Label-read columns** are filled for the 8 seed brands only (blank for the other 418); 27 of their 31 values are approved and in `analog_features`. Launch quarter is the approved launch date for Taltz, Siliq and Ibrance (same quarter as before) and the first SDUD quarter for every other analog.
- **Seed launch dates:** Cosentyx's wasn't found (sources say Jan or Mar 2015). Otezla, Tremfya, Skyrizi and Sotyktu rest on pre-launch statements ("expected to be available", marked `[excerpt, verify]`); Medicaid data agrees within a quarter, but they stay unapproved until an actual launch announcement is found. Ibrance has one suppressed SDUD row in 2014Q2, before its 2015 approval (`checks.md` flags its launch date vs. first SDUD quarter).
- **SC pool includes clinic-administered products** (e.g. Prolia, Evenity, Leqvio). No flag yet.
- **Out of the pool for now:** 16 injectables Drugs@FDA lists only as `INJECTABLE;INJECTION` (e.g. Tanzeum, Winrevair), until their labels are read; Belviq (withdrawn, no route anywhere).
- **Late launches:** `late_launch` flags 19 analogs whose first Medicaid quarter is > 1 year after approval: the route came later (e.g. `entyvio_sc`, `actemra_sc`) or Medicaid uptake started late (e.g. `fycompa_oral`). `checks.md` lists 15 by start marketing date instead.
- **Enough-data rule:** 96 analogs have < 12 SDUD quarters; 37 have > 20% of Q3–Q20 TRx imputed. 25 analogs pass the cap at 1 Rx per suppressed row but not at 10, so their status depends on the estimate. The first-wave HCV orals are back in the pool, and with them more rise-and-fall curves Bass can't fit.
- **Suppression assumptions:** we assume a quarter with no SDUD row means 0 Rx and that a suppressed row is < 11 Rx. Neither is confirmed with CMS (decisions.md, 2026-11-01).
- **Weak Bass fits:** 106 of 268 (38 of them `low_volume`).
- **`label_expansion_in_window` over-flags:** it counts every efficacy supplement. Approval letters say which ones added an indication.
- **Peak not confirmed:** share of peak is against the Q0–Q28 peak (decisions.md 2026-11-14). 97 of the 261 usable analogs (2019+ launches) don't have the full window yet, so their share of peak is an upper bound ("≤ X"), including Caplyta and Lybalvi. 105 still peak at the last quarter of their window.
- **No ATC class:** 26 analogs. 9 still have several classes after the ATC fix, mostly combination products (listed in `checks.md`).
- **Coverage gaps:** the NME compilation ends at 2025, so 2026 approvals aren't in the pool. The Purple Book URL is per month (update it in `pipeline/fda.py`).
- **Empty on purpose:** `cost per unit` (empty for now), `market size` and `fills per patient` (dropped). Whether to remove the dropped columns is an open question.

**Pick up here**

**First, whoever picks up next: review the steps 2–7 PR** (`jm/step-02-07-finder-core`, by Joshua; one PR for six steps, one commit each, agreed as an exception to one-PR-per-step). Run: `pip install -r analog_finder/requirements.txt` (adds scikit-learn), `pytest analog_finder/tests` (133 pass, offline), `python -m analog_finder.finder --scenario torevia --auto-confirm --embedder tfidf` (5 confirmed, three outputs), and the same with `--holdout latuda_oral` (Latuda in no output). Step 8 builds on it.

1. **Plan step 0, finish:** draw `docs/analog_finder_architecture.png`.
2. **Plan step 8 (evaluation harness),** then 9 (RxBERT): leave-one-out on the usable analogs, TF-IDF and structured-only vs the all-analog median (≈ 0.18) and ATC 4 baselines. The scoring weights in `config/scoring.yaml` are still the provisional defaults until this result is logged in decisions.md. Also open from step 5: should approved evidence that mismatches rank an analog below one with no evidence ([score.md](analog_finder/docs/components/score.md))?
3. **C, labels** (the bottleneck for analog matching: the EDA found class and area don't predict uptake, so line of therapy, competition and dosing have to; see [data_model.md](docs/data_model.md#label-reads-plan)). Once built, the Label Research Agent does these reads (plan steps 10–12, 15); until then, manual reads go in `analog_evidence.csv` as `approved=false` rows with quote and link.
   1. **Finish the seed 8:** find actual launch announcements for Otezla, Tremfya, Skyrizi, Sotyktu, and Cosentyx's launch date.
   2. **Example drug's analogs first:** 4 fields each for Torevia's 5 analogs (Latuda, Rexulti, Vraylar, Caplyta, Lybalvi), then the 41 usable nervous-system analogs.
   3. **Extend** to the rest of the 261 usable analogs.
   4. **Other label reads:** self-injected vs clinic-given for every sc analog (self-administered flag); route of the 16 `INJECTABLE;INJECTION` brands; approval letters for efficacy supplements (which ones added an indication).
4. **C, review process:** new rows go in with `approved=false`; run `python -m pipeline.labels --check` before review, so the reviewer only judges whether each value fits its quote. Launch dates and competitor counts aren't label quotes and need a person to check the source. The app's review page (plan step 12) replaces the spreadsheet once built.
5. **B:** add same-class competitors and `units_per_rx` to SDUD.
6. **A/D:** add a self-administered flag (or exclude clinic-administered SC drugs). Decide what to do with the missing ATC classes. Read the route of the 16 injectables to bring the sc ones into the pool.
7. **EDA:** owners rerun their notebooks on the new tables and update their write-ups (`launch_eda` is done). `pool_funnel`, `suppression` and the `volume_vs_shape` simulation still use the old blank-quarter rule and need their owners' updates. Notebooks that read `share_of_peak` (`launch_eda`, `analog_similarity`, `volume_vs_shape`) shift with the Q0–Q28 peak (2026-11-14) once `main` is merged into `eda`.
8. **Team:** remove the dropped columns from `analogs.csv`, or keep them empty (open question in decisions.md). Settle the RxBERT license and the agent's competitor definition (open questions in decisions.md, needed by plan steps 9 and 11).

### Log
Newest first.
- **2026-11-18, Analog Finder steps 2–7, finder core (Joshua, `jm/step-02-07-finder-core`):** target drug (Torevia's profile), hard filters + holdout, TF-IDF profile embeddings, hybrid scoring, confirm loop and the weighted uptake curve; `python -m analog_finder.finder --scenario torevia` runs end to end offline. 133 tests. Decisions per step in decisions.md (2026-11-18) and `analog_finder/docs/components/`. `pipeline/checks.py`: the funnel rules moved into `funnel_steps()` / `usable()` so the finder shares them; `checks.md` unchanged. Torevia (TF-IDF, provisional weights): Rexulti, Vraylar, Nuplazid, Caplyta, Latuda, Lybalvi rank 1–6; the demo outputs reject Nuplazid (Parkinson's psychosis) and confirm the 5 expected analogs; year-3 weighted share ≤ 0.48 of peak (band 0.19–0.80). Holdout runs write to gitignored `data/scenarios/<scenario>-holdout-<ids>/`. Shared contracts: candidate table and `uptake_curve` gain columns (additive).
- **2026-11-17, Analog Finder step 1, plumbing (Christina, `ch/step-01-plumbing`):** added `analog_finder/` with config (`scoring.yaml`, `approved_sources.yaml`), `scenarios/torevia.yaml`, `io.py`, `llm.py` and 37 offline tests; spec in `analog_finder/docs/components/plumbing.md`. Approved evidence: the latest `approved_at` wins (file order until that column exists). Scenario overrides change only the keys they name; unknown keys fail. Default weights are provisional until step 5. Plan contract: the evidence field is `n_competitors_at_launch`. No pipeline code or data changed.
- **2026-11-17, implementation plan (Christina, `main`, PR #7):** added [implementation_plan.md](docs/implementation_plan.md) for the Analog Finder and wrote its agreed decisions D1–D8 and the evaluation method into the docs (plan step 0): decisions.md, user_journey.md (v2), data_model.md (`target_drug`, `analog_recommendations`, `analog_weights`, new `uptake_curve`, `data/scenarios/`, `data/cache/`), data_sources.md (approved-source list), example_drug.md. Old versions are in `docs/archive/`. Main changes from the v1 journey: no agent re-rank; top 5 confirmed one at a time; curve weights = normalized similarity; label expansion and multi-route are warnings, not exclusions. `.gitignore` (`data/cache/`), `.env.example` (`GEMINI_MODEL`, `SEC_USER_AGENT`) and README updated for the finder. No code or data changed. Merged without a PR review: the team agreed the plan together in person.
- **2026-11-17, PR #6 merged; `main` merged into `c/seed-review` first (Christina):** resolved PR #6's conflicts. `data/processed/` taken from `main` (suppression imputation, Q0–Q28 peak), then rebuilt from the 2026-10-30/31 raw pulls so the 27 approved seed values reach `analog_features` and `checks.md`. Only the 8 seed analogs' rows changed; curves and Bass fits are unchanged (the approved launch dates fall in the same quarter as before). The branch's own 2026-10-26 rebuild was superseded; its newer NDC listings were already on `main`. Pick-up list and label-reads plan updated for the chosen example drug and the 261-analog pool.
- **2026-11-14, Q0–Q28 peak (Grace, `main`):** `share_of_peak` now divides by the Q0–Q28 peak, not the Q0–Q20 peak (decisions.md 2026-11-14; EDA `peak_window` §5). New `peak_confirmed` flag: 164 of 261 usable analogs have the full window; the other 97 show share of peak as an upper bound. Bass is still fitted on Q0–Q20: p and q unchanged for 86–90% of analogs, median m 1.00 → 0.89, m's floor 0.5 → 0.1, weak fits 107 → 106 (Farxiga no longer on a bound). Year-3 share for the demo analogs: Latuda 0.37, Rexulti 0.59, Vraylar 0.19, Caplyta ≤ 0.54, Lybalvi ≤ 0.80 (`example_drug.md`). Only `launch_curves`, `analog_features`, `bass_fits` and `checks.md` were rebuilt, from the committed upstream tables, because my `data/raw/` is older than the 2026-10-30/31 pulls; a full `--refresh` build gives the same peak rule.
- **2026-11-01, suppression rebuild and EDA rerun (Christina, `main`):** suppressed SDUD rows are now imputed at 5 Rx and no row = 0 TRx (decisions.md 2026-10-30). Rebuilt from sources pulled 2026-10-30/31, not a final `--refresh`. 250 → 261 usable analogs, 256 → 268 Bass fits. The first-wave HCV orals return, so anti-infective stats shift sharply (median R² 0.83 → 0.32); the 5 demo analogs barely move. EDA findings hold except that class medians are now about level with the overall median, not worse. Oncology is 37 of 64 weak fits (was 41 of 62).
- **2026-10-27, example drug (Christina, `main`):** the team agreed on the demo's example drug, Torevia (velapiprazole): a fictional oral antipsychotic for adult schizophrenia, 7th branded entrant, launching 2027-01. Profile, expected analogs (Latuda, Rexulti, Vraylar, Caplyta, Lybalvi), illustrative ceiling inputs and caveats in [docs/example_drug.md](docs/example_drug.md). Settles "one area or two" (decisions.md): one area, nervous system. Next: label reads for those 5 analogs.
- **2026-10-26, seed label review (Gabrielle, `c/seed-review`):** approved 27 of the 31 seed values after checking each against its source (all 16 label quotes verbatim in the ORIG labels; Taltz, Siliq, Ibrance launch dates from company statements; competitor counts against Drugs@FDA dates). Taltz launch date now sourced from Lilly's SEC filing; Ilumya and Cimzia dates corrected in the competitor quotes. Added `python -m pipeline.labels --check`.
- **2026-10-23, ATC class fix (Grace, `main`):** each analog's ATC class is now its own, not one from a combination product or a topical form. 16 analogs corrected, e.g. the SGLT2 and DPP-4 drugs (were "combinations"), Victoza and Adlyxin (were insulins), Jakafi and Daliresp (were dermatology, so their area changes).
- **2026-10-22, route fallback (Grace, `a/route-fallback`):** brands whose NDCs give no route now take it from Drugs@FDA, adding 34 analogs (e.g. Trikafta, Symdeko, Ocaliva). 7 existing analogs corrected: Lynparza, Esbriet, Zejula and Zykadia now launch from their original capsules. `checks.md` lists every brand left out of the pool.
- **2026-10-22, tables for EDA (Grace, `b/launch-curves`):** added `launch_curves`, `analog_features`, `bass_fits`, `indication_history` and `medicaid_enrollment`, plus the pool funnel in `checks.md`. Fixed arbitrary picks between same-day approvals (submission classification) and tied peak quarters.
- **2026-10-21, first data build (Jmazher12, `a/analog-table-v1`):** the pipeline and the v1 analog table (23 schema columns), SDUD by quarter, the NDC map, and label reads for the 8 seed brands.

## Workflow
- **Small tasks go straight to `main`:** doc edits, open questions, approving or fixing a few `analog_evidence` rows, a small bug fix in one module. `git pull` first, keep the commit small, push right away.
- **Use a branch + PR** (`<workstream>/<topic>`, e.g. `b/sdud-ndc-map`) for work that takes more than a day, adds or reworks a `pipeline/` module, changes a rule in the docs, or rebuilds `data/processed/` (big diffs that collide easily).
- **Analog Finder steps:** one step = one branch = one PR, merged in plan order, branch `<initials>/step-<NN>-<name>` (e.g. `ab/step-05-scoring`). Each PR has code, tests, its component spec (`analog_finder/docs/components/<name>.md`) and every doc it changes; another team member reviews and runs the step's "Done when" check. `pytest analog_finder/tests` stays green offline on `main`. Full rules: [implementation_plan.md](docs/implementation_plan.md#working-agreements).
- Either way, add a dated line to the Status & handoff log for anything a teammate should know about, so the log is the one place to see what changed.
- When you add or change a table, update its data_model.md build status; when you settle an open question, log it in decisions.md and remove the question. Same commit or PR.