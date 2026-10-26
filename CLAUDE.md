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
**Last update: 2026-10-26 (Gabrielle, branch `c/seed-review`).** Keep "Current state" current; add a dated line to the log when you hand off.

### Current state
**What exists** (`data/processed/`, specs in [data_model.md](docs/data_model.md)):
- `analogs.csv`: the v1 analog table, 426 analogs (332 oral, 94 sc) × the 23 schema-sheet columns. The pool is every NME / new BLA in the FDA NME compilation approved 2010–2025, split by route group.
- `sdud_quarterly.csv`: Medicaid TRx by quarter, 2010Q1–2026Q1 (378 analogs have Rx). `ndc_map.csv`: 1,511 NDCs and how each was matched.
- `launch_curves.csv`: TRx and share of peak, Q0–Q20. `analog_features.csv`: launch quarter, data quality, distortion flags, `enough_data`. `bass_fits.csv`: p, q, m for the 256 analogs with enough data.
- `indication_history.csv`: possible label expansions. `medicaid_enrollment.csv`: enrollment by quarter with shock windows.
- `checks.md`: validation report. **250 analogs** pass the rules code can apply (202 oral, 48 sc); it also lists every NME brand left out of the pool, with the reason.
- `data/reference/analog_evidence.csv`: label reads (line of therapy, dosing, launch date, # competitors) for the 8 seed brands (Otezla, Cosentyx, Taltz, Siliq, Tremfya, Skyrizi, Sotyktu, Ibrance). 31 values with quotes and links; **27 approved** (Gabrielle, 2026-10-26), 4 launch dates waiting (below). `python -m pipeline.labels --check` checks every label quote against its label.
- Code: `pipeline/` (`fda`, `sdud`, `ndc`, `rxclass`, `enrollment`, `curves`, `features`, `bass`, `labels`, `build`, `checks`).

**How to run**
- Setup: Python 3.12+ (`python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt`).
- `python -m pipeline.build` rebuilds everything. The first run downloads ~600 MB (mostly SDUD) and takes about an hour; later runs take ~2 min from `data/raw/`.
- `--refresh` re-downloads every source; do this before any final build.
- `data/processed/` is committed, so you only need to rebuild to change or refresh the data.
- Label helper: `python -m pipeline.labels <ApplNo>` downloads the ORIG label and extracts its text.

**Known issues** (details in `checks.md`)
- **Label-read columns** are filled for the 8 seed brands only (blank for the other 418). 27 of their 31 values are approved, but `data/processed/` hasn't been rebuilt since, so `analog_features` doesn't show them yet. Launch quarter is the approved launch date for Taltz, Siliq and Ibrance (same quarter as their first SDUD quarter) and the first SDUD quarter for every other analog.
- **Seed launch dates:** Cosentyx's wasn't found (sources say Jan or Mar 2015). Otezla, Tremfya, Skyrizi and Sotyktu rest on pre-launch statements ("expected to be available", marked `[excerpt, verify]`); Medicaid data agrees within a quarter, but they stay unapproved until an actual launch announcement is found. Ibrance has one suppressed SDUD row in 2014Q2, before its 2015 approval.
- **SC pool includes clinic-administered products** (e.g. Prolia, Evenity, Leqvio). No flag yet.
- **Out of the pool for now:** 16 injectables Drugs@FDA lists only as `INJECTABLE;INJECTION` (e.g. Tanzeum, Winrevair), until their labels are read; Belviq (withdrawn, no route anywhere).
- **Late launches:** `late_launch` flags 19 analogs whose first Medicaid quarter is > 1 year after approval: the route came later (e.g. `entyvio_sc`, `actemra_sc`) or Medicaid uptake started late (e.g. `fycompa_oral`). `checks.md` lists 15 by start marketing date instead.
- **Enough-data rule:** 96 analogs have < 12 SDUD quarters; 85 have blank quarters after Q2. It leaves out drugs that faded fast (e.g. the first-wave HCV orals), so the usable pool leans towards launches that lasted.
- **`label_expansion_in_window` over-flags:** it counts every efficacy supplement. Approval letters say which ones added an indication.
- **Peak inside Q0–Q20:** many curves peak at Q20, some possibly from the COVID enrollment growth (open question in decisions.md).
- **No ATC class:** 26 analogs. 9 still have several classes after the ATC fix, mostly combination products (listed in `checks.md`).
- **Coverage gaps:** the NME compilation ends at 2025, so 2026 approvals aren't in the pool. The Purple Book URL is per month (update it in `pipeline/fda.py`).
- **Empty on purpose:** `cost per unit` (empty for now), `market size` and `fills per patient` (dropped). Whether to remove the dropped columns is an open question.

**Pick up here**
1. **C, labels** (the bottleneck for analog matching: the EDA found class and area don't predict uptake, so line of therapy, competition and dosing have to; see [data_model.md](docs/data_model.md#label-reads-plan)):
   1. **Rebuild** so the 27 approved seed values reach `analog_features` (`python -m pipeline.build`; needs `data/raw/`).
   2. **Finish the seed 8:** find actual launch announcements for Otezla, Tremfya, Skyrizi, Sotyktu, and Cosentyx's launch date.
   3. **Team: pick the example drug's therapeutic area**, then read labels for that area's usable analogs first (4 fields each). Enough to test whether matching on these fields beats class matching.
   4. **Extend** to the rest of the 250 usable analogs.
   5. **Other label reads:** self-injected vs clinic-given for every sc analog (self-administered flag); route of the 16 `INJECTABLE;INJECTION` brands; approval letters for efficacy supplements (which ones added an indication).
2. **C, review process:** new rows go in with `approved=false`; run `python -m pipeline.labels --check` before review, so the reviewer only judges whether each value fits its quote. Launch dates and competitor counts aren't label quotes and need a person to check the source.
3. **B:** add same-class competitors and `units_per_rx` to SDUD.
4. **A/D:** add a self-administered flag (or exclude clinic-administered SC drugs). Decide what to do with the missing ATC classes. Read the route of the 16 injectables to bring the sc ones into the pool.
5. **EDA:** pool and therapeutic-area comparison on the new tables, including the Q0–Q20 peak question.
6. **Team:** remove the dropped columns from `analogs.csv`, or keep them empty (open question in decisions.md).

### Log
Newest first.
- **2026-10-26, seed label review (Gabrielle, `c/seed-review`):** approved 27 of the 31 seed values after checking each against its source (all 16 label quotes verbatim in the ORIG labels; Taltz, Siliq, Ibrance launch dates from company statements; competitor counts against Drugs@FDA dates). Taltz launch date now sourced from Lilly's SEC filing; Ilumya and Cimzia dates corrected in the competitor quotes. Added `python -m pipeline.labels --check`. Not rebuilt yet.
- **2026-10-23, ATC class fix (Grace, `main`):** each analog's ATC class is now its own, not one from a combination product or a topical form. 16 analogs corrected, e.g. the SGLT2 and DPP-4 drugs (were "combinations"), Victoza and Adlyxin (were insulins), Jakafi and Daliresp (were dermatology, so their area changes).
- **2026-10-22, route fallback (Grace, `a/route-fallback`):** brands whose NDCs give no route now take it from Drugs@FDA, adding 34 analogs (e.g. Trikafta, Symdeko, Ocaliva). 7 existing analogs corrected: Lynparza, Esbriet, Zejula and Zykadia now launch from their original capsules. `checks.md` lists every brand left out of the pool.
- **2026-10-22, tables for EDA (Grace, `b/launch-curves`):** added `launch_curves`, `analog_features`, `bass_fits`, `indication_history` and `medicaid_enrollment`, plus the pool funnel in `checks.md`. Fixed arbitrary picks between same-day approvals (submission classification) and tied peak quarters.
- **2026-10-21, first data build (Jmazher12, `a/analog-table-v1`):** the pipeline and the v1 analog table (23 schema columns), SDUD by quarter, the NDC map, and label reads for the 8 seed brands.

## Workflow
- Branch per task: `<workstream>/<topic>` (e.g. `b/sdud-ndc-map`); merge to `main` via PR
- A PR that adds or changes a table updates its row in the data_model.md build status
- A PR that settles an open question adds a row to the decisions.md log and removes the question