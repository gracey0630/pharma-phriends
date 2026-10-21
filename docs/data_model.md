# Data Model & Workstreams

Tables, columns, sources, dependencies and owners, following the [user journey](user_journey.md): (1) define the drug → (2) find analogs → (3) size the market → (4) review uptake → (5) illustrative curve. Source details: [data_sources.md](data_sources.md). Decisions and open questions: [decisions.md](decisions.md).

**Conventions**
- **One analog = brand × route group.** Key: `analog_id` = `brand_key` + `route_group` (e.g. `skyrizi_sc`).
- Time series use long format: `analog_id, source, payer, period, metric, value, pulled_at`.
- Manual / approved tables live in `data/reference/`; built tables in `data/processed/`, overwritten every run.
- ⚠️ = check the input is current before building (see [data_sources.md](data_sources.md)).

## v1 analog table (current spec)

**Decision 2026-10-21:** v1 keeps only the 23 columns of the team's analog schema (Google Sheet "data schema for analogs"). The larger set of tables further down is the longer-term design. Tables marked *deferred* in the build status aren't being built for v1.

`data/processed/analogs.csv` has one row per `analog_id` (the key) followed by exactly these 23 columns, with the sheet's names and order. Build it with `python -m pipeline.build`.

| # | Column | Filled from | Coverage |
|---|---|---|---|
| 1 | ndc | All 9-digit NDCs (labeler + product) in the route group, `; `-separated. Detail is in `ndc_map.csv` | all |
| 2 | route of administration | Route group from NDC Directory `ROUTENAME`: `oral` or `sc` | all |
| 3 | manufacturer/sponsor/company at approval | Drugs@FDA `SponsorName` of the original application | all |
| 4 | Rx | Total Medicaid TRx to date (SDUD, national, FFSU + MCOU). The quarterly series is in `sdud_quarterly.csv` | all with SDUD |
| 5 | generic name | NME compilation `Active Ingredient/Moiety` | all |
| 6 | application number | NDA/BLA numbers whose NDCs are in this route group | all |
| 7 | submission classification | Drugs@FDA submission class of the ORIG approval | all |
| 8 | line of therapy | ORIG label indication (label read) | seed 8 |
| 9 | approval date | Earliest ORIG + AP submission in Drugs@FDA | all |
| 10 | cost per unit | Empty; open question | none |
| 11 | market size | Empty; open question (workstream E epi funnel) | none |
| 12 | brand name | NME compilation `Proprietary Name` | all |
| 13 | start marketing date | Earliest `STARTMARKETINGDATE` across the route group's NDCs | all |
| 14 | market category | NDC Directory `MARKETINGCATEGORYNAME` | all |
| 15 | dosage form | NDC Directory `DOSAGEFORMNAME` values | all |
| 16 | indication | NME compilation `Approved Use(s)` (indication at original approval) | all |
| 17 | # competitors at launch | Label read. Branded advanced systemic therapies (biologic or novel oral) approved for the same first indication before launch; excludes biosimilars and withdrawn drugs | seed 8 |
| 18 | novel drugs | `True` for every row: the pool comes from the NME compilation | all |
| 19 | launch date | Label read: first commercial availability (press release / trade press). `YYYY-MM` when only the month is known | seed 7 (Cosentyx not found) |
| 20 | class (narrow) | RxClass ATC level 4, e.g. `L04AC Interleukin inhibitors` | all RxClass knows |
| 21 | dosing frequency | Label read (ORIG label, dosage and administration) | seed 8 |
| 22 | fills per patient | Empty; open question | none |
| 23 | generic / exclusivity date | First quarter (`YYYYQn`) in which a generic (ANDA, same active ingredient) or biosimilar (351(k) referencing the brand) NDC is dispensed in Medicaid SDUD; blank = none yet. Approval and NDC listing aren't used because generics are often approved and listed years before patents let them launch | all |

"Seed 8" are the prototype brands: Otezla, Cosentyx, Taltz, Siliq, Tremfya, Skyrizi, Sotyktu, Ibrance. Label-read values live in `data/reference/analog_evidence.csv` with a quote and link. They are copied into `analogs.csv` even before approval, and `checks.md` lists every analog with unapproved values.

**Supporting files** (`data/processed/`, rebuilt every run):
- `sdud_quarterly.csv`: analog × quarter, long format; metrics `trx`, `units`, `reimbursed_usd`, `suppressed_rows`
- `ndc_map.csv`: analog × NDC, with `listing` (current / excluded / sdud only) and `match_method`
- `candidate_pool.csv`, `generic_ndcs.csv`: intermediates
- `checks.md`: validation report

## Rules (agree before building)

| Rule | Definition |
|---|---|
| Analog pool | Novel NDA/BLA, first indication, pharmacy-dispensed route group, launched 2010 onward |
| Enough data | ≥ 12 quarters of SDUD TRx after launch; no suppressed quarters after Q2 |
| Brand → NDC | Application number in NDC Directory + excluded file, plus SDUD NDCs with same labeler + name; split by route group; audited in `ndc_map` |
| TRx | SDUD prescriptions, all NDCs in the route group, national, FFSU + MCOU, per quarter |
| Launch date | Press release / SEC filing (approved evidence); cross-check: first quarter with TRx > 0 |
| Uptake curve | TRx ÷ peak TRx, by quarter since launch, Q0–Q20 |
| Agent features | Only attributes knowable for the target drug before launch |
| Payer | Analog curves are Medicaid; never mix with Medicare |

## Dependencies

```
Raw pulls (day 1)
  ├─► candidate_pool ⚠️ ─┬─► ndc_map ─► sdud_quarterly ─┬─► launch_curves ─► bass_fits
  │                      │                              │
  │                      ├─► analog_evidence (agent + human review) ─► drug_master ─┐
  │                      ├─► indication_history ───────────────────────────────────┤
  │                      └─► exclusivity ──────────────────────────────────────────┴─► analog_features
  ├─► medicaid_enrollment (flag) ────────────────────────────────────────────────────┘
  └─► target_drug (forecaster) ─► market_size ; epi_funnel (optional)

Query time:  target_drug + analog_features ─► analog_recommendations ─► (approved 3–5) ─► bass_fits ─► analog_weights ─► illustrative curve
```
Critical path: FDA files → `candidate_pool` → `ndc_map` → `sdud_quarterly` → `analog_features`. Longest task: `analog_evidence` review.

## Build status

Update in the PR that changes a table. Status: not started / in progress / built (matches this spec).

| Table | Workstream | Journey step | Status |
|---|---|---|---|
| Download/cache module + manifest | 0 | — | built (`pipeline/common.py`) |
| **`analogs` (v1 analog table, 23 sheet columns)** | A–C | 2 | **built**; label-read columns for seed 8 only |
| `candidate_pool` | A | 2 | built (`pipeline/fda.py`); pool rule above, oral + sc |
| `indication_history` | A | 2 | deferred (v1) |
| `exclusivity` | A | 2 | replaced in v1 by the generic / exclusivity date column |
| `drug_master` | A | 2 | deferred (v1: `analogs` plays this role) |
| `ndc_map` | B | 2 | built (`pipeline/fda.py` + `pipeline/ndc.py`) |
| `sdud_quarterly` | B | 2, 4 | built for pool analogs (`pipeline/sdud.py`); same-class competitors not yet added |
| `medicaid_enrollment` | B | 2 | deferred (v1) |
| `launch_curves` | B | 4 | not started |
| `analog_evidence` | C | 2 | in progress: 4 fields × seed 8 analogs, none approved yet |
| `analog_features` | D | 2 | not started |
| `analog_recommendations` | D | 2 | not started |
| `target_drug` | E | 1 | not started |
| `market_size` | E | 3 | not started |
| `epi_funnel` | E | 3 | not started (prototype for Ibrance 1L mBC in `6e92c63`) |
| `bass_fits` | E | 4 | not started |
| `analog_weights` | E | 4 | not started |

---

## Data tables (built ahead of time)

### `candidate_pool`: one row per analog_id passing the hard filters ⚠️
| Column | Source |
|---|---|
| analog_id, brand_key, route_group | Derived |
| brand_name, generic_name, first_indication, priority / breakthrough / accelerated / orphan | NME compilation |
| application_numbers, sponsor, approval_date, submission_class | Drugs@FDA |
| dosage_form, market_category | Drugs@FDA Products, NDC Directory |

### `analog_evidence`: one row per analog_id × field (agent-extracted, human-approved)
Fields: indication / target patients, line_of_therapy, dosing_frequency, days_supply, class_narrow, class_broad, competitors_at_launch, n_competitors_at_launch, efficacy_safety_vs_soc, launch_date, first_in_class, boxed_warning, rems.

| Column | Source |
|---|---|
| analog_id, field, value | Agent extraction |
| quote, source_url, source_type | Original label, ClinicalTrials.gov, press release / SEC filing, Novel Drug Approvals, REMS list |
| extracted_by, extracted_at | Agent / person |
| approved, approved_by | Human review |

### `ndc_map`: one row per analog_id × NDC ⚠️
| Column | Source |
|---|---|
| ndc9, labeler_name, strength, dosage_form, route | NDC Directory + excluded file, SDUD |
| start_marketing_date, end_marketing_date | NDC Directory + excluded file |
| match_method, in_fda_list | Derived |
| first_sdud_quarter, rx_total | SDUD |

### `sdud_quarterly`: analog_id × quarter, long format ⚠️
Includes **same-class competitors** (needed to check peak share against analog peaks).

| Metric | Source |
|---|---|
| trx, units, reimbursed_usd, suppressed_rows | SDUD |
| units_per_rx | Derived (days-supply check) |

### `indication_history`: one row per analog_id × approved indication ⚠️
| Column | Source |
|---|---|
| indication, line_of_therapy | Label at that approval (agent + review) |
| approval_date, submission_type | Drugs@FDA Submissions (ORIG / EFFICACY) |
| q_since_launch | Derived |

### `exclusivity`: one row per analog_id × record ⚠️
| Column | Source |
|---|---|
| record_type, expiry_date, first_generic_date | Orange Book, Purple Book |

### `medicaid_enrollment`: one row per quarter ⚠️
| Column | Source |
|---|---|
| period, enrollees | Medicaid & CHIP enrollment |

### `drug_master`: one row per analog_id
| Column | Source |
|---|---|
| candidate_pool columns | candidate_pool |
| approved values from analog_evidence (one column per field) | analog_evidence (`approved = true`) |
| atc_narrow, atc_broad | RxClass ⚠️ (checks class_narrow / class_broad) |
| entry_order_in_class, entry_order_in_indication, entry_order_at_line | Derived (the three meanings of "first") |

### `launch_curves`: analog_id × quarter since launch
| Column | Source |
|---|---|
| q_since_launch (0–20), period, trx, suppressed_rows | sdud_quarterly + launch_date |
| share_of_peak | Derived |
| trx_per_1k_enrollees (optional) | + medicaid_enrollment |
| label_expansion_flag | indication_history |

### `analog_features`: one row per analog_id. Input to the analog agent
| Column | Source |
|---|---|
| drug_master columns (match fields) | drug_master |
| launch_quarter, days_approval_to_launch, quarters_of_data, peak_trx | sdud_quarterly, launch_curves |
| **Data quality:** suppressed_quarters, provisional_quarters, ndc_match_issues, fields_not_approved | sdud_quarterly, ndc_map, analog_evidence |
| **Distortion flags:** label_expansion_in_window, generic_entry_in_window, enrollment_shock_in_window, rems, limited_distribution | indication_history, exclusivity, medicaid_enrollment, analog_evidence |
| enough_data | Derived (rule above) |

---

## Scenario and output tables (created per forecast)

| Table | One row per | Columns | Created by |
|---|---|---|---|
| `target_drug` | scenario | indication, target_patient_definition, class_narrow, class_broad, route_group, dosage_form, line_of_therapy, entry_order, first_definition (class / indication / line), expected_n_entrants, n_competitors_at_launch, efficacy_safety_vs_soc, dosing_frequency, days_supply, dosing_vs_alternatives, launch_date | Forecaster (step 1) |
| `analog_recommendations` | scenario × analog | filter_pass, similarity_score, agent_rank, reasoning, evidence_links, approved | Code filters + scores; agent re-ranks; forecaster approves 3–5 (step 2) |
| `market_size` | scenario | entry_order, n_entrants_low/high, alpha_low/high, peak_share_low/base/high, differentiation_adj + reason, M_low/base/high | Forecaster inputs + Zipf code (step 3) |
| `epi_funnel` (optional) | indication × step | stage, low/base/high, source_url, source_file, source_type | Manual from SEER / CDC / literature (step 3) |
| `bass_fits` | analog | p, q, fit_quality, weak_fit_flag, dropped | Code from launch_curves (step 4) |
| `analog_weights` | scenario × analog | weight, reasoning | Agent recommends, code computes (step 4) |

---

## Workstreams

| Workstream | Owns | Pulls | Waits on | Start |
|---|---|---|---|---|
| **0. Setup** | Download/cache module + manifest | — | — | Day 1 (half day) |
| **A. FDA & candidate pool** | `candidate_pool`, `indication_history`, `drug_master`, `exclusivity` | NME compilation, Drugs@FDA, NDC + excluded, RxClass, Orange/Purple Book | Setup | Day 1 |
| **B. Medicaid utilization** | `ndc_map`, `sdud_quarterly`, `launch_curves`, `medicaid_enrollment` | SDUD whole years, enrollment | candidate_pool (for ndc_map) | Day 1 (downloads) |
| **C. Evidence extraction & review** | `analog_evidence` (extraction agent + review UI/sheet) | Original labels, ClinicalTrials.gov, press releases / SEC, Novel Drug Approvals, REMS | candidate_pool | Day 1 (field definitions); extract once pool exists |
| **D. Analog agent** | `analog_features`, `analog_recommendations` (filters, similarity score, agent re-rank) | — | A, B, C | Day 1 (design scoring on draft data) |
| **E. Market size & uptake** | `target_drug` schema, `market_size`, `epi_funnel`, `bass_fits`, `analog_weights` | SEER / CDC / literature (optional) | launch_curves (for bass_fits) | Day 1 (Zipf + Bass code) |

**Handoffs to agree on day 1**
| Handoff | From → To | Fix early |
|---|---|---|
| `analog_id` + `candidate_pool` | A → B, C, D | Route groups, filter rule (draft by day 2) |
| `analog_evidence` fields + allowed values | C → A, D | Line of therapy, dosing, class, "first" definitions |
| `target_drug` columns | E → D | Same fields and values as `analog_evidence` (so they can be compared) |
| Long format | B → D, E | Column names above |

**Milestones:** (1) analog agent: `target_drug` + `analog_features` → `analog_recommendations`; (2) uptake review: `launch_curves` → `bass_fits`, `analog_weights`; (3) ceiling: `market_size`; (4) illustrative curve.

**Out of scope for now:** fills conversion, access scenarios, Monte Carlo (Part D spending, formulary files).

## Validation checks (after every build)
- Candidate with no SDUD rows, or launch before approval
- SDUD NDCs for a candidate's labeler/name missing from `ndc_map`
- Launch date (evidence) vs. first SDUD quarter differ by > 1 quarter
- Units per Rx far from label days supply
- Unapproved evidence fields in `analog_features`
- ⚠️ Any raw file older than the source's latest release

---

## Crosswalk: original analog schema → tables

Where each column of the first analog schema (Google Sheet "data schema for analogs") lives in the longer-term model. **For v1 the sheet columns are used directly**; see [v1 analog table](#v1-analog-table-current-spec). This crosswalk is kept for when the larger tables are built.

| Sheet column | Table.column | Note |
|---|---|---|
| ndc | `ndc_map.ndc9` | |
| route of administration | `candidate_pool.route_group`, `ndc_map.route` | |
| manufacturer/sponsor/company at approval | `candidate_pool.sponsor` (+ `ndc_map.labeler_name`) | |
| Rx | `sdud_quarterly` (`trx`), `launch_curves.trx` | Medicaid SDUD only; Part D is a cross-check |
| generic name | `candidate_pool.generic_name` | |
| application number | `candidate_pool.application_numbers` | |
| submission classification | `candidate_pool.submission_class` | |
| line of therapy | `analog_evidence` → `drug_master.line_of_therapy` | Agent-extracted, human-approved |
| approval date | `candidate_pool.approval_date` | |
| cost per unit | — | **Open:** pricing is out of scope |
| market size | `epi_funnel`, `market_size` | **Open:** CT.gov not currently used for this |
| brand name | `candidate_pool.brand_name` | |
| start marketing date | `ndc_map.start_marketing_date` → `analog_features.days_approval_to_launch` | |
| market category | `candidate_pool.market_category` | |
| dosage form | `candidate_pool.dosage_form`, `ndc_map.dosage_form` | |
| indication | `candidate_pool.first_indication`, `analog_evidence` (indication / target patients) | ORIG label, not DailyMed |
| # competitors at launch | `analog_evidence` → `drug_master.n_competitors_at_launch` | |
| novel drugs | `candidate_pool` filter (NME compilation); `first_in_class` from Novel Drug Approvals | |
| launch date | `analog_evidence` → `drug_master.launch_date` | |
| class (narrow) | `analog_evidence` → `drug_master.class_narrow`, checked against `atc_narrow` | **Open:** sheet says DailyMed MoA |
| dosing frequency | `analog_evidence` → `drug_master.dosing_frequency`; `sdud_quarterly.units_per_rx` check | |
| fills per patient | — | **Open:** not in any table (fills conversion out of scope) |
| generic / exclusivity date | `exclusivity` | |
