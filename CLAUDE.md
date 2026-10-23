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
- Folders: `data/raw/<source>/` downloads, unchanged, plus a manifest (gitignored); `data/reference/` manual / approved tables; `data/processed/` tables built by code; `eda/` notebooks and write-ups (rules in [eda/README.md](eda/README.md))
- Secrets in `.env` (gitignored); see `.env.example`

## Status & handoff
**Last update: 2026-10-23 (Gabrielle, branch `eda`).** Keep "Current state" current; add a dated line to the log when you hand off.

### Current state
**What exists** (`data/processed/`, specs in [data_model.md](docs/data_model.md)):
- `analogs.csv`: the v1 analog table, 426 analogs (332 oral, 94 sc) × the 23 schema-sheet columns. The pool is every NME / new BLA in the FDA NME compilation approved 2010–2025, split by route group.
- `sdud_quarterly.csv`: Medicaid TRx by quarter, 2010Q1–2026Q1 (378 analogs have Rx). `ndc_map.csv`: 1,511 NDCs and how each was matched.
- `launch_curves.csv`: TRx and share of peak, Q0–Q20. `analog_features.csv`: launch quarter, data quality, distortion flags, `enough_data`. `bass_fits.csv`: p, q, m for the 256 analogs with enough data.
- `indication_history.csv`: possible label expansions. `medicaid_enrollment.csv`: enrollment by quarter with shock windows.
- `checks.md`: validation report. **250 analogs** pass the rules code can apply (202 oral, 48 sc); it also lists every NME brand left out of the pool, with the reason.
- `data/reference/analog_evidence.csv`: label reads (line of therapy, dosing, launch date, # competitors) for the 8 seed brands (Otezla, Cosentyx, Taltz, Siliq, Tremfya, Skyrizi, Sotyktu, Ibrance). 31 values with quotes and links, **none approved yet**.
- Code: `pipeline/` (`fda`, `sdud`, `ndc`, `rxclass`, `enrollment`, `curves`, `features`, `bass`, `labels`, `build`, `checks`).

**How to run**
- Setup: Python 3.12+ (`python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt`).
- `python -m pipeline.build` rebuilds everything. The first run downloads ~600 MB (mostly SDUD) and takes about an hour; later runs take ~2 min from `data/raw/`.
- `--refresh` re-downloads every source; do this before any final build.
- `data/processed/` is committed, so you only need to rebuild to change or refresh the data.
- Label helper: `python -m pipeline.labels <ApplNo>` downloads the ORIG label and extracts its text.

**Known issues** (details in `checks.md`)
- **Label-read columns** are filled for the 8 seed brands only (blank for the other 418), and none are approved. Launch quarter is therefore the first SDUD quarter for every analog.
- **Seed launch dates:** Cosentyx's wasn't found (sources say Jan or Mar 2015); some quotes come from trade-press excerpts (marked `[excerpt, verify]`) and need checking against the original release. Ibrance has one suppressed SDUD row in 2014Q2, before its 2015 approval.
- **SC pool includes clinic-administered products** (e.g. Prolia, Evenity, Leqvio). No flag yet.
- **Out of the pool for now:** 16 injectables Drugs@FDA lists only as `INJECTABLE;INJECTION` (e.g. Tanzeum, Winrevair), until their labels are read; Belviq (withdrawn, no route anywhere).
- **Late launches:** `late_launch` flags 19 analogs whose first Medicaid quarter is > 1 year after approval: the route came later (e.g. `entyvio_sc`, `actemra_sc`) or Medicaid uptake started late (e.g. `fycompa_oral`). `checks.md` lists 15 by start marketing date instead.
- **Enough-data rule:** 96 analogs have < 12 SDUD quarters; 85 have blank quarters after Q2. It leaves out drugs that faded fast (e.g. the first-wave HCV orals), so the usable pool leans towards launches that lasted.
- **`label_expansion_in_window` over-flags:** it counts every efficacy supplement. Approval letters say which ones added an indication.
- **Peak inside Q0–Q20:** many curves peak at Q20, some possibly from the COVID enrollment growth (open question in decisions.md).
- **No ATC class:** 26 analogs.
- **Coverage gaps:** the NME compilation ends at 2025, so 2026 approvals aren't in the pool. The Purple Book URL is per month (update it in `pipeline/fda.py`).
- **Empty on purpose:** `cost per unit` (empty for now), `market size` and `fills per patient` (dropped). Whether to remove the dropped columns is an open question.

**Pick up here**
1. **C, review:** approve or fix the 31 seed values in `analog_evidence.csv` (set `approved=true`, `approved_by=<name>`), then rebuild.
2. **C, extend:** label reads for the rest of the pool, starting with the 250 analogs left in the `checks.md` funnel. Add `analog_id`, `field`, `value`, `quote`, `source_url` rows with `approved=false`.
3. **B:** add same-class competitors and `units_per_rx` to SDUD.
4. **A/D:** add a self-administered flag (or exclude clinic-administered SC drugs). Decide what to do with the missing ATC classes. Read the route of the 16 injectables to bring the sc ones into the pool.
5. **EDA:** pick an `open` topic from the registry in [eda/README.md](eda/README.md) (e.g. the Q0–Q20 peak question, Bass fit quality), claim it there, and follow its naming and write-up format.
6. **Team:** remove the dropped columns from `analogs.csv`, or keep them empty (open question in decisions.md).

### Log
Newest first.
- **2026-10-23, volume vs shape EDA (Joshua, `eda`):** `eda/volume_vs_shape_joshua.ipynb`, summarised in `eda/eda_joshua.md`. Bass fit quality is mostly a Medicaid-volume effect (counting noise reproduces it), including oncology's weak fits; small drugs also start faster and peak sooner. Proposes a low-volume flag and volume as a similarity feature.
- **2026-10-23, first EDAs (Christina and Gabrielle, `eda`):** Christina's broad first pass in `eda/launch_eda_christina.ipynb`; `eda/` with naming rules, write-up format and a topic registry ([eda/README.md](eda/README.md)); notebooks on the pool funnel, Medicaid gaps (suppression) and late launches, summarised in `eda/eda_gabrielle.md`. Added `jupyterlab` to requirements.
- **2026-10-22, route fallback (Grace, `a/route-fallback`):** brands whose NDCs give no route now take it from Drugs@FDA, adding 34 analogs (e.g. Trikafta, Symdeko, Ocaliva). 7 existing analogs corrected: Lynparza, Esbriet, Zejula and Zykadia now launch from their original capsules. `checks.md` lists every brand left out of the pool.
- **2026-10-22, tables for EDA (Grace, `b/launch-curves`):** added `launch_curves`, `analog_features`, `bass_fits`, `indication_history` and `medicaid_enrollment`, plus the pool funnel in `checks.md`. Fixed arbitrary picks between same-day approvals (submission classification) and tied peak quarters.
- **2026-10-21, first data build (Jmazher12, `a/analog-table-v1`):** the pipeline and the v1 analog table (23 schema columns), SDUD by quarter, the NDC map, and label reads for the 8 seed brands.

## Workflow
- Branch per task: `<workstream>/<topic>` (e.g. `b/sdud-ndc-map`); merge to `main` via PR
- A PR that adds or changes a table updates its row in the data_model.md build status
- A PR that settles an open question adds a row to the decisions.md log and removes the question
- **EDA:** before starting one, read [eda/README.md](eda/README.md) and work on the shared `eda` branch (pull first) and check its registry so no topic is done twice; claim the topic in the registry and push the claim before starting. Name files `eda/<topic>_<name>.ipynb` plus one `eda/eda_<name>.md` write-up per person in the shared format, since everyone's EDAs get combined