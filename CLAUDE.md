# Pharma Phriends: Launch Analog and Input Tool

Team project. Helps a pharma forecaster choose and defend two launch-forecast inputs: the **ceiling** (peak patients, M) and the **trajectory** (uptake shape, Bass p/q from analog launches).

## Read first
1. [docs/user_journey.md](docs/user_journey.md): what the tool does, step by step (draft; changes via PR)
2. [docs/data_sources.md](docs/data_sources.md): what we pull, source rules, freshness checks
3. [docs/data_model.md](docs/data_model.md): tables, dependencies, workstreams, build status
4. [docs/decisions.md](docs/decisions.md): decision log and open questions

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
- Suppressed SDUD values stay blank, never 0
- Indication, dosing and class come from the **original** approval label (Drugs@FDA ORIG), never DailyMed (current label)
- Agent-extracted values are saved with quote + source link and need human approval before use
- Folders: `data/raw/<source>/` downloads, unchanged, plus a manifest (gitignored); `data/reference/` manual / approved tables; `data/processed/` tables built by code
- Secrets in `.env` (gitignored); see `.env.example`

## Status & handoff
**Last update: 2026-10-22, tables for EDA (Grace, branch `b/launch-curves`, stacked on `a/analog-table-v1`).** Newest entry first; add yours on top when you hand off.

### 2026-10-22: tables for EDA (Grace)
- **New tables** in `data/processed/` (specs in [data_model.md](docs/data_model.md); rules in the 2026-10-22 rows of [decisions.md](docs/decisions.md)):
  - `launch_curves`: TRx and share of peak, Q0–Q20.
  - `analog_features`: launch, data quality, distortion flags, `enough_data`.
  - `bass_fits`: p, q, m for analogs with enough data.
  - `indication_history`: possible label expansions from Drugs@FDA.
  - `medicaid_enrollment`: by quarter, with shock windows.
- **Pool after the rules code can apply** (`checks.md`): 392 → 373 with SDUD → 354 launched within a year of approval → 354 no generic in Q0–Q12 → **235 with enough data** (190 oral, 45 sc). 243 Bass fits, 94 weak.
- **Launch quarter** is the first SDUD quarter for all 373 analogs (no launch dates approved yet).
- **Watch:**
  - 89 of the 201 full-window curves peak at Q20 (open question in decisions.md).
  - `label_expansion_in_window` over-flags (counts every efficacy supplement).
  - `multi_route` counts IV forms added later.
- **Fixed:** same-day ORIG approvals were picked arbitrarily, so `submission classification` flipped for 10 analogs between builds.
- **Rebuild:** ~2 min from `data/raw/`.

### 2026-10-21: first data build (Jmazher12, `a/analog-table-v1`)

#### What exists
- **v1 analog table:** `data/processed/analogs.csv`, one row per `analog_id` with exactly the 23 columns of the team's analog schema sheet (names and order unchanged). Column sources: [data_model.md → v1 analog table](docs/data_model.md#v1-analog-table-current-spec). Decision: v1 uses **only** these columns.
- **Pool:** 391 analogs (303 oral, 88 sc) = every NME / new BLA in the FDA NME compilation approved 2010–2025, split by route group. 350 have Medicaid Rx.
- **Rx by quarter:** `data/processed/sdud_quarterly.csv` (long format, SDUD 2010Q1–2026Q1, national, FFSU + MCOU). Suppressed quarters are blank.
- **NDCs:** `data/processed/ndc_map.csv`, 1,414 NDCs, each with how it was matched.
- **Label reads:** `data/reference/analog_evidence.csv` covers line of therapy, dosing frequency, launch date and # competitors at launch for the 8 seed brands (Otezla, Cosentyx, Taltz, Siliq, Tremfya, Skyrizi, Sotyktu, Ibrance). There are 31 values, each with a quote and link, and **none approved yet**.
- **Validation report:** `data/processed/checks.md`.
- **Code:** `pipeline/` (`fda`, `sdud`, `ndc`, `rxclass`, `labels`, `build`, `checks`).

#### How to run
- Setup: Python 3.12+ (`python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt`).
- `python -m pipeline.build` rebuilds everything. The first run downloads ~600 MB (mostly SDUD) and takes about an hour; later runs take ~30 s from `data/raw/`.
- `--refresh` re-downloads every source; do this before any final build.
- `data/processed/` is committed, so you only need to rebuild to change or refresh the data.
- Label helper: `python -m pipeline.labels <ApplNo>` downloads the ORIG label and extracts its text.

#### Empty on purpose
`cost per unit`, `market size` and `fills per patient` are empty columns. Market size and fills per patient are dropped; cost per unit is empty for now (decisions.md, 2026-10-22). Whether to remove the dropped columns is an open question.

#### Known issues (details in `checks.md`)
- **Label-read columns** are filled for the 8 seed brands only; blank for the other 383.
- **Cosentyx launch date not found:** sources disagree (Jan vs Mar 2015). Its first SDUD row is 2015Q1.
- **Launch date quotes:** some come from trade-press excerpts (marked `[excerpt, verify]`). Check them against the original release before approving.
- **Ibrance** has one suppressed SDUD row in 2014Q2, before its 2015 approval.
- **SC pool includes clinic-administered products** (e.g. Prolia, Evenity, Leqvio). No flag yet for self-administered vs clinic.
- **Not first-indication launches (16 analogs):** the route came > 1 year after approval (e.g. `entyvio_sc`, `ozempic_oral`, `actemra_sc`).
- **Enough-data rule:** 87 analogs have < 12 SDUD quarters; 65 have suppressed quarters after Q2.
- **No ATC class:** 21 analogs.
- **Coverage gaps:** the NME compilation ends at 2025, so 2026 approvals aren't in the pool. The Purple Book URL is per month (update it in `pipeline/fda.py`).

#### Pick up here (updated 2026-10-22)
1. **C, review:** approve or fix the 31 seed values in `analog_evidence.csv` (set `approved=true`, `approved_by=<name>`), then rebuild.
2. **C, extend:** label reads for the rest of the pool, starting with the 235 analogs left in the `checks.md` funnel. Add `analog_id`, `field`, `value`, `quote`, `source_url` rows with `approved=false`.
3. **B:** add same-class competitors and `units_per_rx` to SDUD.
4. **A/D:** add a self-administered flag (or exclude clinic-administered SC drugs). Decide what to do with the 21 missing ATC classes.
5. **EDA:** pool and therapeutic-area comparison on the new tables, including the Q0–Q20 peak question.
6. **Team:** remove the dropped columns from `analogs.csv`, or keep them empty (open question in decisions.md).

## Workflow
- Branch per task: `<workstream>/<topic>` (e.g. `b/sdud-ndc-map`); merge to `main` via PR
- A PR that adds or changes a table updates its row in the data_model.md build status
- A PR that settles an open question adds a row to the decisions.md log and removes the question