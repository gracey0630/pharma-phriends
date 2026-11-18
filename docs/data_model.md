# Data Model & Workstreams

Tables, columns, sources, dependencies and owners, following the [user journey](user_journey.md): (1) define the drug → (2) find analogs → (3) size the market → (4) review uptake → (5) illustrative curve. Source details: [data_sources.md](data_sources.md). Decisions and open questions: [decisions.md](decisions.md). How the query-time tables are built (`analog_finder/`, steps, module contracts): [implementation_plan.md](implementation_plan.md). Earlier versions of this doc: [archive/](archive/).

**Conventions**
- **One analog = brand × route group.** Key: `analog_id` = `brand_key` + `route_group` (e.g. `skyrizi_sc`).
- Time series use long format: `analog_id, source, payer, period, metric, value, pulled_at`.
- Manual / approved tables live in `data/reference/`; built tables in `data/processed/`, overwritten every run.
- Per-forecast tables live in `data/scenarios/<scenario>/` (written by `analog_finder`; committed for the demo scenario `torevia` only). The scenario's input profile is `analog_finder/scenarios/<scenario>.yaml`.
- `data/cache/` holds rebuildable caches (`analog_embeddings.npz`, keyed by embedder name + profile-text hash) and is gitignored.
- Where this doc and the plan's [Shared contracts](implementation_plan.md#shared-contracts) both describe a file, this doc wins; change both in the same PR.
- ⚠️ = check the input is current before building (see [data_sources.md](data_sources.md)).

## v1 analog table (current spec)

**Decision 2026-10-21:** v1 keeps only the 23 columns of the team's analog schema (Google Sheet "data schema for analogs"). The larger set of tables further down is the longer-term design. Tables marked *deferred* in the build status aren't being built for v1.

`data/processed/analogs.csv` has one row per `analog_id` (the key) followed by exactly these 23 columns, with the sheet's names and order. Build it with `python -m pipeline.build`.

**Why it matters:** the team's 23-column table with one row per candidate launch, which forecasters read to see what each analog is.

| # | Column | Filled from | Coverage |
|---|---|---|---|
| 1 | ndc | All 9-digit NDCs (labeler + product) in the route group, `; `-separated. Detail is in `ndc_map.csv` | all |
| 2 | route of administration | Route group from NDC Directory `ROUTENAME`: `oral` or `sc`; Drugs@FDA Products route when no NDC under the application has one ([data_sources.md](data_sources.md)) | all |
| 3 | manufacturer/sponsor/company at approval | Drugs@FDA `SponsorName` of the original application | all |
| 4 | Rx | Total Medicaid TRx to date (SDUD, national, FFSU + MCOU), mid estimate (suppressed rows at 5 Rx). The quarterly series is in `sdud_quarterly.csv` | all with SDUD |
| 5 | generic name | NME compilation `Active Ingredient/Moiety` | all |
| 6 | application number | NDA/BLA numbers whose NDCs are in this route group | all |
| 7 | submission classification | Drugs@FDA submission class of the ORIG approval | all |
| 8 | line of therapy | ORIG label indication (label read) | seed 8 |
| 9 | approval date | Earliest ORIG + AP submission in Drugs@FDA | all |
| 10 | cost per unit | Empty for now; if filled later, add cost per Rx alongside ([decisions](decisions.md)) | none |
| 11 | market size | Empty; dropped, sizing is per forecast in `market_size` ([decisions](decisions.md)) | none |
| 12 | brand name | NME compilation `Proprietary Name` | all |
| 13 | start marketing date | Earliest `STARTMARKETINGDATE` across the route group's NDCs | all |
| 14 | market category | NDC Directory `MARKETINGCATEGORYNAME` | all |
| 15 | dosage form | NDC Directory `DOSAGEFORMNAME` values | all |
| 16 | indication | NME compilation `Approved Use(s)` (indication at original approval) | all |
| 17 | # competitors at launch | Label read. Branded advanced systemic therapies (biologic or novel oral) approved for the same first indication before launch; excludes biosimilars and withdrawn drugs | seed 8 |
| 18 | novel drugs | `True` for every row: the pool comes from the NME compilation | all |
| 19 | launch date | Label read: first commercial availability (press release / trade press). `YYYY-MM` when only the month is known | seed 7 (Cosentyx not found) |
| 20 | class (narrow) | RxClass ATC level 4, e.g. `L04AC Interleukin inhibitors`; the brand's own class, not those of combination products or topical forms ([data_sources.md](data_sources.md)) | all RxClass knows |
| 21 | dosing frequency | Label read (ORIG label, dosage and administration) | seed 8 |
| 22 | fills per patient | Empty; dropped ([decisions](decisions.md)) | none |
| 23 | generic / exclusivity date | First quarter (`YYYYQn`) in which a generic (ANDA, same active ingredient) or biosimilar (351(k) referencing the brand) NDC is dispensed in Medicaid SDUD; blank = none yet. Approval and NDC listing aren't used because generics are often approved and listed years before patents let them launch | all |

"Seed 8" are the prototype brands: Otezla, Cosentyx, Taltz, Siliq, Tremfya, Skyrizi, Sotyktu, Ibrance. Label-read values live in `data/reference/analog_evidence.csv` with a quote and link. They are copied into `analogs.csv` even before approval, and `checks.md` lists every analog with unapproved values.

**Supporting files** (`data/processed/`, rebuilt every run):
- `sdud_quarterly.csv`: analog × quarter, long format; metrics `trx` (mid estimate), `trx_low`, `trx_high`, `trx_reported`, `suppressed_rows`, `imputed_share`, `units`, `reimbursed_usd`
- `ndc_map.csv`: analog × NDC, with `listing` (current / excluded / sdud only) and `match_method`
- `launch_curves.csv`, `analog_features.csv`, `bass_fits.csv`, `indication_history.csv`, `medicaid_enrollment.csv`: built tables, specs below
- `candidate_pool.csv`: intermediate, spec below
- `generic_ndcs.csv`: brand × possible generic / biosimilar NDC. Why it matters: it finds when generic competition started, so curves it distorts can be excluded
- `checks.md`: validation report. Why it matters: it lists the data problems, shows how many analogs survive each rule, and lists every NME brand left out of the pool with the reason

## Rules (agree before building)

| Rule | Definition |
|---|---|
| Analog pool | Novel NDA/BLA, first indication, pharmacy-dispensed route group, launched 2010 onward |
| Enough data | ≥ 12 complete (non-provisional) quarters of SDUD since launch, and ≤ 20% of the analog's Q3–Q20 TRx imputed (mid estimate; `MAX_IMPUTED_SHARE` in `pipeline/features.py`) |
| Low volume | Peak TRx (mid) < 300 a quarter (`LOW_VOLUME`). A flag, not a filter: counting noise alone weakens Bass fits at this size (EDA `volume_vs_shape`) |
| Brand → NDC | Application number in NDC Directory + excluded file, plus SDUD NDCs with same labeler + name; split by route group; audited in `ndc_map` |
| TRx | SDUD prescriptions, all NDCs in the route group, national, FFSU + MCOU, per quarter. Suppressed rows (< 11 Rx) imputed at 5 (low 1, high 10); a quarter with no SDUD row = 0. Both readings are model assumptions, not confirmed with CMS (decisions.md, 2026-11-01) |
| Launch date | Press release / SEC filing (approved evidence). Until approved, launch quarter = first SDUD quarter with any row (a suppressed row means 1–10 Rx), never before the approval quarter |
| Uptake curve | TRx ÷ peak TRx, by quarter since launch, Q0–Q20. Peak = max over Q0–Q20, excluding provisional quarters (the latest 2 SDUD quarters) |
| In window | Distortion flags (label expansion, generic entry, enrollment shock) look at Q0–Q12, the first 3 years |
| Agent features | Only attributes knowable for the target drug before launch |
| Payer | Analog curves are Medicaid; never mix with Medicare |
| Finder hard filters | Usable analogs from the `checks.md` funnel (enough data, no generic entry in window, no late launch) in the target's route group; a holdout analog is removed first. `label_expansion_in_window` and `multi_route` are warnings, not exclusions (D1, D2, decisions 2026-11-17) |
| Evidence in matching | Approved `analog_evidence` values only (D8) |
| Similarity | Σ wᵢsᵢ / Σ wᵢ over the features both target and analog have: text similarity on the profile text plus one 0–1 score per structured feature; weights from `analog_finder/config/scoring.yaml`, overridable per scenario (D6, D7) |
| Curve weights | Similarity ÷ sum of similarities over the confirmed analogs (sums to 1); forecaster override needs a reason (D5) |

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

Stage 1 (Label Research Agent, analog_finder/research):
  approved sources ─► analog_evidence rows (approved=false) ─► human review ─► approved values

Stage 2 (Analog Finder, query time, analog_finder/finder):
  target_drug + analog_features + approved analog_evidence
    ─► hard filters ─► embeddings (data/cache) + hybrid score ─► top 5, confirm / reject ─► analog_recommendations
    ─► (confirmed 3–5) + launch_curves + bass_fits ─► analog_weights ─► uptake_curve ─► illustrative curve
```
Critical path: FDA files → `candidate_pool` → `ndc_map` → `sdud_quarterly` → `analog_features`. Longest task: `analog_evidence` review.

## Build status

Update in the PR that changes a table. Status: not started / in progress / built (matches this spec).

| Table | Workstream | Journey step | Status |
|---|---|---|---|
| Download/cache module + manifest | 0 | — | built (`pipeline/common.py`) |
| **`analogs` (v1 analog table, 23 sheet columns)** | A–C | 2 | **built**; label-read columns for seed 8 only |
| `candidate_pool` | A | 2 | built (`pipeline/fda.py`); pool rule above, oral + sc (426 analogs); 16 injectables with no stated route are out until their labels are read |
| `indication_history` | A | 2 | built (`pipeline/fda.py`): approvals from Drugs@FDA; indication and line of therapy blank (need label reads) |
| `exclusivity` | A | 2 | replaced in v1 by the generic / exclusivity date column |
| `drug_master` | A | 2 | deferred (v1: `analogs` + `analog_features` play this role) |
| `ndc_map` | B | 2 | built (`pipeline/fda.py` + `pipeline/ndc.py`) |
| `sdud_quarterly` | B | 2, 4 | built for pool analogs (`pipeline/sdud.py`), suppressed rows imputed (low / mid / high); same-class competitors and `units_per_rx` not yet added |
| `medicaid_enrollment` | B | 2 | built (`pipeline/enrollment.py`); no data 2013-10 to 2017-05, used for shock flags only |
| `launch_curves` | B | 4 | built (`pipeline/curves.py`); no `trx_per_1k_enrollees` (no normalization in v1) |
| `analog_evidence` | C | 2 | in progress: 4 fields × seed 8 analogs, 27 of 31 approved; label-reads plan below. Label Research Agent (`analog_finder/research/`) and review screen: not started (plan steps 10–12) |
| `analog_features` | D | 2 | built (`pipeline/features.py`) for the columns code can fill; label-read match fields, `rems`, `limited_distribution` wait on approved evidence |
| `analog_recommendations` | D | 2 | built for the CLI (`analog_finder/finder/`: filters, TF-IDF embeddings, hybrid score, confirm loop; plan steps 3–6); summary cards and the app page not started (steps 13–14); demo output in `data/scenarios/torevia/` |
| Embedding cache (`data/cache/`) | D | 2 | built (`finder/embed.py`, step 4); used by fixed-model embedders only, so empty until RxBERT (step 9) |
| `target_drug` | E | 1 | built (`finder/target.py`, step 2); Torevia's profile in `analog_finder/scenarios/torevia.yaml` |
| `market_size` | E | 3 | not started |
| `epi_funnel` | E | 3 | not started (prototype for Ibrance 1L mBC in `6e92c63`) |
| `bass_fits` | E | 4 | built (`pipeline/bass.py`) for analogs with enough data |
| `analog_weights` | E | 4 | built (`finder/curve.py`, step 7) |
| `uptake_curve` | E | 4 | built (`finder/curve.py`, step 7); adds `n_upper_bound` |

---

## Data tables (built ahead of time)

### `candidate_pool`: one row per analog_id passing the hard filters ⚠️
**Why it matters:** the list of novel oral and SC drugs approved since 2010 that every other table is built from.

| Column | Source |
|---|---|
| analog_id, brand_key, route_group | Derived |
| brand_name, generic_name, first_indication, priority / breakthrough / accelerated / orphan | NME compilation |
| application_numbers, sponsor, approval_date, submission_class | Drugs@FDA |
| dosage_form, market_category | Drugs@FDA Products, NDC Directory |

### `analog_evidence`: one row per analog_id × field (agent-extracted, human-approved)
**Why it matters:** the facts that need a label read (line of therapy, dosing, competitors, launch date), each with a quote and a human approval, so the analog matching can be defended.

Fields: indication / target patients, line_of_therapy, dosing_frequency, days_supply, class_narrow, class_broad, competitors_at_launch, n_competitors_at_launch, efficacy_safety_vs_soc, launch_date, first_in_class, boxed_warning, rems.

**Written by the Label Research Agent** (Stage 1, `python -m analog_finder.research`; [plan](implementation_plan.md) steps 10–12). v1 extracts four fields: line_of_therapy and dosing_frequency (ORIG label), launch_date (press release / SEC filing, first commercial availability; "expected to be available" is a forecast, never a launch date) and n_competitors_at_launch (proposed by the model, each approval date checked against Drugs@FDA, marked `[derived, verify each date]`). It fetches only from the [approved-source list](data_sources.md#approved-source-list), appends rows with `approved=false`, and never overwrites an approved row. A person approves, edits or rejects each row in the app's review screen or the spreadsheet; one reviewer commits a given batch. The finder joins in approved values when it runs, so an approval shows up without a `pipeline.build`.

| Column | Source |
|---|---|
| analog_id, field, value | Agent extraction |
| quote, source_url, source_type | Original label, ClinicalTrials.gov, press release / SEC filing, Novel Drug Approvals, REMS list, Drugs@FDA |
| quote_check | verbatim / partial / not_checked: is the quote on the source page (`analog_finder/research/verify.py`) |
| extracted_by, extracted_at | agent / seed / human |
| approved, approved_by, approved_at | Human review. If two approved rows exist for the same analog and field, the latest `approved_at` is expected to win (to confirm in plan step 1) |

#### Label-reads plan
**Why it's next:** analog matching (journey step 2) compares the target drug with analogs on these fields. The EDA ([eda/](../eda/README.md)) found that ATC class and therapeutic area alone don't predict an analog's first 3 years, so line of therapy, competition and dosing have to carry the matching, and they only exist where labels have been read.

| Step | What | Unblocks | Status |
|---|---|---|---|
| 1 | Seed 8: 4 fields each, checked against source | the review process, end to end | 27 of 31 approved; 4 launch dates rest on pre-launch statements; Cosentyx launch date not found |
| 2 | Rebuild so approved values reach `analog_features` | anything that reads approved fields | done 2026-11-17 (merge of `main` into PR #6) |
| 3 | The example drug's therapeutic area: 4 fields for its usable analogs | testing whether matching on these fields beats class matching (`analog_similarity` EDA) | area chosen 2026-10-27: nervous system ([example_drug.md](example_drug.md)); Torevia's 5 analogs first, then the 41 usable nervous-system analogs; not started |
| 4 | The rest of the 261 usable analogs | `analog_recommendations` | not started |
| 5 | Self-injected vs clinic-given, from each sc label's dosage section | the self-administered flag | not started |
| 6 | Route of the 16 brands Drugs@FDA lists only as `INJECTABLE;INJECTION` | bringing the sc ones into the pool | not started |
| 7 | Approval letters for efficacy supplements: which added an indication | a precise `label_expansion_in_window` | not started |

**Where each field comes from:** line of therapy and dosing frequency from the ORIG label (indication; dosage and administration); launch date from a press release or SEC filing (first commercial availability, not approval); # competitors at launch derived from FDA approval history (definition in the v1 table above).

**Review:** rows go in with `approved=false`, a quote and a link. `python -m pipeline.labels --check` reports whether each label quote is verbatim in the label at its `source_url`; the reviewer then only judges whether the value fits the quote. Launch dates and competitor counts aren't label quotes: the reviewer checks the source itself. A forecast ("expected to be available in May") isn't a launch date.

### `ndc_map`: one row per analog_id × NDC ⚠️
**Why it matters:** it links each analog to all its product codes, since Medicaid reports by NDC rather than by brand.

| Column | Source |
|---|---|
| ndc9, labeler_name, strength, dosage_form, route | NDC Directory + excluded file, SDUD |
| start_marketing_date, end_marketing_date | NDC Directory + excluded file |
| match_method, in_fda_list | Derived |
| first_sdud_quarter, rx_total | SDUD |

### `sdud_quarterly`: analog_id × quarter, long format ⚠️
**Why it matters:** the raw Medicaid prescription counts per analog per quarter, which every curve is built from.

Includes **same-class competitors** (needed to check peak share against analog peaks).

| Metric | Source |
|---|---|
| trx_reported, units, reimbursed_usd, suppressed_rows | SDUD (sum of reported rows; `trx_reported` blank when every row is suppressed) |
| trx, trx_low, trx_high | Derived: `trx_reported` + 5 / 1 / 10 Rx per suppressed row. `trx` (mid) is the one every table uses |
| imputed_share | Derived: share of `trx` that is imputed (5 × suppressed rows ÷ trx) |
| units_per_rx | Derived (days-supply check) |

### `indication_history`: one row per analog_id × approval that set or may have changed its indications ⚠️
Every ORIG approval under the route group's applications (`kind` = original), plus EFFICACY supplements and new-indication applications (types 6, 9, 10). New-indication applications are taken from all the brand's applications, because they often have no NDCs of their own (Otezla's psoriasis approval is NDA206088). `kind`:
- `original`: anything approved on the first approval date (Rydapt got two indications the same day), plus later new dosage forms or formulations.
- `new indication application`: a later approval filed for an indication. These are expansions.
- `efficacy supplement`: only a **possible** expansion. Drugs@FDA doesn't say whether one adds an indication or only new clinical data (Skyrizi has 12); the approval letters do (planned label round).

**Why it matters:** it flags analogs that gained a new indication early on, because their curves reflect more than one launch and would mislead a first-indication forecast.

| Column | Source |
|---|---|
| application_number, submission_type, submission_no, submission_class, kind, approval_date | Drugs@FDA Submissions |
| q_since_launch | Derived (approval quarter − launch quarter) |
| indication, line_of_therapy | Label at that approval (agent + review); blank for now |

### `exclusivity`: one row per analog_id × record ⚠️
**Why it matters:** it would hold patent and exclusivity expiry dates; for now the generic-entry date in `analogs.csv` stands in for it.

| Column | Source |
|---|---|
| record_type, expiry_date, first_generic_date | Orange Book, Purple Book |

### `medicaid_enrollment`: one row per quarter from 2010Q1 ⚠️
**Why it matters:** it marks when Medicaid itself grew or shrank (2014 expansion, COVID, unwinding), so we don't mistake a change in enrollment for a drug's uptake.

| Column | Source |
|---|---|
| period, enrollees, months | Medicaid & CHIP enrollment: sum of states' final monthly totals, averaged over the months available in the quarter. Blank 2010Q1–2017Q1 except 2013Q3 (one baseline month, 49 states) |
| shock | Fixed windows: 2014 expansion (2014Q1–2015Q4), COVID continuous coverage (2020Q2–2023Q1), unwinding (2023Q2–2024Q4) |

### `drug_master`: one row per analog_id
**Why it matters:** it would combine pool facts with approved label reads in one table; for now `analogs.csv` and `analog_features` play that role.

| Column | Source |
|---|---|
| candidate_pool columns | candidate_pool |
| approved values from analog_evidence (one column per field) | analog_evidence (`approved = true`) |
| atc_narrow, atc_broad | RxClass ⚠️ (checks class_narrow / class_broad) |
| entry_order_in_class, entry_order_in_indication, entry_order_at_line | Derived (the three meanings of "first") |

### `launch_curves`: analog_id × quarter since launch
**Why it matters:** it turns each analog's Medicaid TRx into a share-of-peak curve over its first 20 quarters, which is the uptake shape the trajectory question needs.

| Column | Source |
|---|---|
| q_since_launch (0–20), period, trx, trx_low, trx_high, trx_reported, suppressed_rows, imputed_share | sdud_quarterly + launch quarter. `trx` is the mid estimate; `imputed_share` documents how much of each quarter is imputed |
| no_sdud_row | True when no NDC of the analog has an SDUD row that quarter; all TRx columns are then 0 |
| provisional | Latest 2 SDUD quarters (incomplete); kept, but left out of the peak |
| share_of_peak | trx ÷ the analog's **Q0–Q28 peak** (max trx over complete quarters Q0–Q28, read from every SDUD quarter, not only these rows; decision 2026-11-14). Without the full Q0–Q28 window (`peak_confirmed` false in analog_features) the peak is the highest quarter so far, so share_of_peak is an upper bound: show it as "≤ X, peak not confirmed" |
| label_expansion_flag | indication_history: on from the first possible label expansion |
| trx_per_1k_enrollees | Not built: v1 flags enrollment shocks instead of normalizing |

### `analog_features`: one row per analog_id. Input to the analog agent
**Why it matters:** one row per analog with the launch facts, data quality and distortion flags that the analog search uses to filter and score candidates.

| Column | Source |
|---|---|
| route_group, therapeutic_area (ATC 1), class_broad (ATC 3), class_narrow (ATC 4) | candidate_pool, RxClass |
| line_of_therapy, dosing_frequency, n_competitors_at_launch | analog_evidence, **approved values only**; blank until reviewed |
| launch_quarter, launch_source, quarters_approval_to_launch, quarters_of_data | sdud_quarterly, launch_curves |
| peak_trx, peak_q, peak_confirmed, peak_at_last_quarter | sdud_quarterly: the Q0–Q28 peak share_of_peak divides by (first quarter reaching it); `peak_confirmed` = the full Q0–Q28 window is in the data; `peak_at_last_quarter` = the peak is Q28, or the latest complete quarter if the window isn't full (still climbing) |
| **Data quality:** low_volume (highest TRx in the Q0–Q20 fit window < 300 a quarter), suppressed_quarters, hidden_quarters_after_q2 (every row suppressed), no_row_quarters_after_q2, imputed_share (Q3–Q20, mid; the enough-data rule) with imputed_share_low / imputed_share_high, provisional_quarters, ndc_match_issues, fields_not_approved | launch_curves, ndc_map, analog_evidence |
| **Distortion flags:** label_expansion_in_window (over-flags: counts every efficacy supplement), generic_entry_in_window, enrollment_shock_in_window (names the shocks), late_launch (> 4 quarters from approval: route added later or delayed launch), multi_route (counts out-of-scope routes such as IV), rems, limited_distribution (blank until label reads) | indication_history, analogs, medicaid_enrollment, candidate_pool, analog_evidence |
| enough_data | Derived (rule above) |

---

## Scenario and output tables (created per forecast)

**Why they matter:**
- `target_drug`: the forecaster's profile of the new drug, which the analogs are compared against.
- `analog_recommendations`: the log of the confirm / reject loop: every candidate shown, with its rank, similarity and the forecaster's decision and reason.
- `market_size`: the ceiling (peak patients, M), from eligible population × peak share via Zipf.
- `epi_funnel`: an optional, detailed sourcing of the eligible population behind M.
- `bass_fits`: it reduces each curve to the p and q our forecast borrows, with a flag showing which fits can't be trusted.
- `analog_weights`: how much each confirmed analog counts when their curves are combined into one trajectory.
- `uptake_curve`: the similarity-weighted trajectory with its band, the trajectory input to the forecast.

`analog_recommendations`, `analog_weights` and `uptake_curve` are written to `data/scenarios/<scenario>/<table>.csv` by `python -m analog_finder.finder --scenario <scenario>` or the app's finder page.

| Table | One row per | Columns | Created by |
|---|---|---|---|
| `target_drug` | scenario | name, indication, target_patient_definition, class_narrow (ATC 4), class_broad (ATC 3), therapeutic_area (ATC 1), route_group, dosage_form, line_of_therapy, entry_order, first_definition (class / indication / line), expected_n_entrants, n_competitors_at_launch (+ is_estimate), efficacy_safety_vs_soc, dosing_frequency, days_supply, dosing_vs_alternatives, launch_date, preferences (feature-weight overrides, D7). Route group derived the same way as for analogs. Required vs. optional fields set in plan step 2 | Forecaster (step 1), saved as `analog_finder/scenarios/<scenario>.yaml` |
| `analog_recommendations` | scenario × analog shown | scenario, analog_id, rank, similarity, decision (shown / confirmed / rejected), reason, decided_by, decided_at | Code filters + scores (deterministic); the model writes a summary card per candidate (not stored here); forecaster confirms or rejects one at a time, a rejection fetches the next-ranked candidate, stop at 3–5 confirmed (step 2; D3, D4) |
| `market_size` | scenario | entry_order, n_entrants_low/high, alpha_low/high, peak_share_low/base/high, differentiation_adj + reason, M_low/base/high | Forecaster inputs + Zipf code (step 3) |
| `epi_funnel` (optional) | indication × step | stage, low/base/high, source_url, source_file, source_type | Manual from SEER / CDC / literature (step 3) |
| `bass_fits` | analog | p, q, m, n_points, fit_quality (R²), weak_fit_flag, low_volume, dropped | Code from launch_curves (step 4). Built ahead for every analog with enough data: cumulative Bass m·F(t) fitted to share_of_peak (mid estimate) on Q0–Q20, so m is the share of the Q0–Q28 peak at saturation (bounds 0.1–5); weak = R² < 0.9 or p, q or m on an arbitrary bound; low_volume shown next to the fit, since a weak fit at low volume is mostly counting noise |
| `analog_weights` | scenario × confirmed analog | analog_id, similarity, weight (similarity normalized over the confirmed analogs; sums to 1), override_weight, override_reason | Code (step 4; D5); the forecaster may override a weight with a reason |
| `uptake_curve` | scenario × quarter since launch | quarter (0–20), weighted_share_of_peak, band_min, band_max (min–max of the confirmed analogs), n_analogs (analogs with data that quarter), n_upper_bound (of those, analogs whose peak isn't confirmed: the weighted value is then an upper bound) | Code from `launch_curves` + `analog_weights` (step 4); the Bass table for the confirmed analogs is shown alongside from `bass_fits` |

---

## Workstreams

| Workstream | Owns | Pulls | Waits on | Start |
|---|---|---|---|---|
| **0. Setup** | Download/cache module + manifest | — | — | Day 1 (half day) |
| **A. FDA & candidate pool** | `candidate_pool`, `indication_history`, `drug_master`, `exclusivity` | NME compilation, Drugs@FDA, NDC + excluded, RxClass, Orange/Purple Book | Setup | Day 1 |
| **B. Medicaid utilization** | `ndc_map`, `sdud_quarterly`, `launch_curves`, `medicaid_enrollment` | SDUD whole years, enrollment | candidate_pool (for ndc_map) | Day 1 (downloads) |
| **C. Evidence extraction & review** | `analog_evidence` (Label Research Agent `analog_finder/research/` + review page / sheet; plan steps 10–12, 15) | Approved sources: original labels, ClinicalTrials.gov, press releases / SEC, Novel Drug Approvals, REMS | candidate_pool | Day 1 (field definitions); extract once pool exists |
| **D. Analog Finder** | `analog_features`, `analog_recommendations` (`analog_finder/finder/`: filters, embeddings, hybrid score, confirm loop, summary cards; plan steps 3–6, 8–9, 13–14) | — | A, B, C | Day 1 (design scoring on draft data) |
| **E. Market size & uptake** | `target_drug` schema, `market_size`, `epi_funnel`, `bass_fits`, `analog_weights`, `uptake_curve` (plan steps 2, 7) | SEER / CDC / literature (optional) | launch_curves (for bass_fits) | Day 1 (Zipf + Bass code) |

The Analog Finder is built as one step = one PR in the order of [implementation_plan.md](implementation_plan.md#build-sequence); module handoffs are its [Shared contracts](implementation_plan.md#shared-contracts).

**Handoffs to agree on day 1**
| Handoff | From → To | Fix early |
|---|---|---|
| `analog_id` + `candidate_pool` | A → B, C, D | Route groups, filter rule (draft by day 2) |
| `analog_evidence` fields + allowed values | C → A, D | Line of therapy, dosing, class, "first" definitions |
| `target_drug` columns | E → D | Same fields and values as `analog_evidence` (so they can be compared) |
| Long format | B → D, E | Column names above |

**Milestones:** (1) Analog Finder: `target_drug` + `analog_features` → `analog_recommendations` (CLI end to end on Torevia at plan step 7); (2) uptake review: `launch_curves` → `bass_fits`, `analog_weights`, `uptake_curve`; (3) ceiling: `market_size`; (4) illustrative curve.

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
| cost per unit | — | Empty for now; if added later, add cost per Rx alongside it ([decisions](decisions.md)) |
| market size | `epi_funnel`, `market_size` | Dropped from the analog table; sizing is per forecast in `market_size` ([decisions](decisions.md)) |
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
| fills per patient | — | Dropped ([decisions](decisions.md)) |
| generic / exclusivity date | `exclusivity` | |
