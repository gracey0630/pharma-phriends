# Data Collection Plan: Launch Forecast Tool

Status: draft, 2026-10-13. Running notes are in [../LOG.md](../LOG.md).

## 1. What the data has to support

Each step of the forecaster journey (see *Launch Forecast Tool: User Journey*) needs specific data. Anything we scrape that doesn't feed one of these rows is out of scope for now.

| Journey step | What the model needs | Best public source | Priority |
|---|---|---|---|
| 1. Drug setup / 3. Analog search | For every candidate analog: approval date, NME flag, first indication, route, dosage form, mechanism class, sponsor, NDCs | openFDA `drugsfda` + `ndc` + `label`; FDA Novel Drug Approvals pages (first-in-class) | **P0** |
| 4. Historical adoption (Bass p, q) | Quarterly TRx per analog from launch through ≥ 12 quarters | **Medicaid SDUD**, national rows (`state = XX`) | **P0** |
| 9. Backtest | Same quarterly TRx series for held-out drugs | Medicaid SDUD (same pull) | **P0** |
| 6. Fills per patient | Claims ÷ patients by drug, plus days supply | Medicare **Part D Spending by Drug** (`Tot_Clms` / `Tot_Benes`, annual); Part D Prescribers (30-day fills) | **P1** |
| 6. Net price per TRx (reference only, the forecaster enters it) | Gross cost per Rx | SDUD `total_amount_reimbursed / number_of_prescriptions`; Part D `Avg_Spnd_Per_Clm`; NADAC | P2 |
| 5. Payer access | Formulary coverage, tier, PA/step therapy over time after launch | CMS Part D formulary PUF (monthly, large files) | P2 |
| 2. Epi funnel | Prevalence → diagnosed → treated → eligible, as ranges with a source tag | Hand-curated table: CDC (NHANES/BRFSS/WONDER), SEER for oncology, GBD, published literature; ClinicalTrials.gov for eligibility criteria | P1 (manual, not scraped) |

**Don't try to scrape the epi funnel.** It comes from scattered literature and is mostly judgment. Keep it as a curated CSV (`data/reference/epi_funnel.csv`) with `low`, `base`, `high`, `source_url` and `source_type` columns. It fits the "source tag" requirement in the user journey doc.

## 2. Sources (all verified live on 2026-10-13)

### 2.1 Medicaid State Drug Utilization Data (SDUD): backbone for adoption curves and backtests
- One dataset per year, 1991–2026, on data.medicaid.gov (DKAN API). Dataset IDs are in [LOG.md](../LOG.md#sdud-dataset-ids).
- Query: `GET https://data.medicaid.gov/api/1/datastore/query/{dataset_id}/0?limit=...&offset=...&conditions[0][property]=...`
- Fields: `utilization_type` (FFSU / MCOU), `state`, `ndc` (11-digit), `labeler_code`, `product_code`, `package_size`, `year`, `quarter`, `suppression_used`, `product_name`, `units_reimbursed`, `number_of_prescriptions`, `total_amount_reimbursed`, `medicaid_amount_reimbursed`, `non_medicaid_amount_reimbursed`.
- **Rules we must follow:**
  1. **Pull only `state = 'XX'`.** These are national totals and are suppressed far less often than state rows. A national row is still blanked when it is under 11 Rx (`suppression_used = true`). This happens with small NDCs and in launch quarters, so the undercount per quarter is at most 10 × the number of suppressed rows. The scraper records `suppressed_rows` per quarter and leaves a quarter blank (not 0) when all of its rows are suppressed.
  2. **Sum both `FFSU` and `MCOU`.** Managed care is now most of Medicaid volume. FFS-only curves will look wrong.
  3. **Find NDCs by name prefix, then audit them against openFDA.** Names are cut to 10 characters and padded with spaces (`"SKYRIZI 15"`, `"SKYRIZI ON"`), so match on the first 10 characters. openFDA lists only *current* NDCs: Otezla's 2014–2019 Celgene NDCs (labeler 59572) are missing there but are 160k+ Rx in SDUD. `sdud_ndc_audit.csv` shows which NDCs matched by name only.
  4. **The latest quarter is incomplete** (states report late). 2026Q1 dips for every brand. Treat the last 1–2 quarters as provisional.
  4. Each year is ~5.3M rows, so filter server-side (state + labeler code) rather than downloading whole years.
- TRx definition: `number_of_prescriptions` summed across all NDCs of a brand, by year-quarter.

### 2.2 Medicare Part D (data.cms.gov): fills per patient and a second payer view
- **Part D Spending by Drug** (annual, current release covers 2020–2024): `Brnd_Name`, `Gnrc_Name`, `Mftr_Name` (use the `"Overall"` row), and per-year `Tot_Clms_YYYY`, `Tot_Benes_YYYY`, `Tot_Spndng_YYYY`, `Avg_Spnd_Per_Clm_YYYY`. **Fills per patient per year = `Tot_Clms / Tot_Benes`.** SDUD has no patient counts, so this is the only public source for that ratio.
  - API: `https://data.cms.gov/data-api/v1/dataset/7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b/data?keyword=<brand>`. Use `keyword`, because exact `filter[Brnd_Name]` misses formulation variants like "Skyrizi On-Body".
  - Older launches need older yearly releases, which go back to about 2012 on the landing page.
- **Quarterly Part D Spending by Drug** gives a quarterly view. Coverage is limited to recent quarters, so it's useful as a Medicare cross-check against SDUD for recent launches.
- **Part D Prescribers, by Geography and Drug**: national `Tot_Clms`, `Tot_30day_Fills`, `Tot_Benes`. This gives a days-supply adjustment (30-day-equivalent fills vs. raw claims).
- Caveat: Medicare is 65+ / disabled. That's a different population from Medicaid, so keep `payer` as an explicit column.

### 2.3 FDA (openFDA): drug master and analog attributes
- `https://api.fda.gov/drug/drugsfda.json?search=openfda.brand_name:"X"`: application number, sponsor, ORIG submission date (= approval date), `submission_class_code_description` (e.g. "Type 1 - New Molecular Entity"), plus `openfda.route`, `openfda.pharm_class_epc` (mechanism class) and `openfda.product_ndc` (the SDUD join key).
- `drug/label.json` gives `indications_and_usage` text, which we use to derive first indication and line of therapy (e.g. "after failure of…"). That parsing is a manual or LLM-assisted tagging step, not a scrape.
- FDA "Novel Drug Approvals for YYYY" pages (CDER) are the HTML source for "first-in-class" and the NME list per year.
- Get a free openFDA API key. Without one the limit is 1,000 requests/day per IP.

### 2.4 Supporting sources
- **RxNav / RxNorm** (`rxnav.nlm.nih.gov/REST`): NDC ↔ RxCUI ↔ ingredient. Catches NDCs openFDA misses (old or discontinued packages).
- **ClinicalTrials.gov API v2** (`clinicaltrials.gov/api/v2/studies`): eligibility criteria, enrollment and phase. Supports the "eligible" stage of the funnel and the competitive landscape at launch.
- **NADAC** (data.medicaid.gov, yearly datasets): pharmacy acquisition cost per unit, as a price reference.

## 3. Analog universe: start narrow

The fixed assumptions (US, NME, first indication, retail pharmacy) plus the need for at least 12 quarters of post-launch data give these filters:

- Approved **2011–2022**. That leaves ≥ 3 full years of SDUD through 2025, and starts after Medicaid managed-care reporting became complete.
- NME / new BLA, **retail-dispensed** (oral or self-injected). Exclude physician-administered drugs (Part B / J-codes), which don't show up as retail TRx.
- **MVP therapeutic area:** immunology / dermatology, matching the doc's plaque psoriasis example. Candidate seed list, to be confirmed against openFDA (the first indication matters, e.g. Otezla's first indication was PsA): Otezla, Cosentyx, Taltz, Siliq, Tremfya, Skyrizi, Sotyktu. After the pipeline works end-to-end on these, add a second area (e.g. diabetes/GLP-1, HCV, or MS orals).

## 4. Shared conventions (agree on these before everyone writes scrapers)

This is the part that keeps the group's work from becoming four incompatible datasets.

**Keys**
- `ndc11`: 11-digit, zero-padded string, no dashes (SDUD format).
- `ndc9` = labeler + product (first 9 digits). This is the brand-level join key.
- `brand_key`: lowercase brand name, one row per brand in `data/reference/drug_master.csv`. This is the table every other dataset joins to.
- `period`: `YYYYQn` for quarterly data, `YYYY` for annual.

**Long-format output schema** for any utilization source:
`brand_key, source, payer, period, metric, value, pulled_at`
(e.g. `skyrizi, sdud, medicaid, 2023Q4, trx, 1533, 2026-10-13`)

**Repo layout**
```
pharma-phriends/
├── LOG.md                    # running notes (everyone appends, dated)
├── docs/data_collection_plan.md
├── scrapers/                 # one module per source: sdud.py, partd.py, openfda.py, ...
├── data/
│   ├── raw/<source>/         # cached API responses, gitignored
│   ├── processed/            # tidy long-format CSV/parquet, small, committed
│   └── reference/            # hand-curated: drug_master.csv, epi_funnel.csv
├── requirements.txt
└── .gitignore                # data/raw/, .env (API keys)
```

**Scraper rules**
- Use APIs before HTML scraping. Every source above except FDA Novel Approvals pages has a JSON API.
- Cache raw responses to `data/raw/` and make re-runs idempotent, so a re-run shouldn't hit the API again.
- Log every pull (dataset ID, query, row count, date) in a `manifest.csv` per source. Stakeholder view needs "source" tags, and this is where they come from.
- Throttle (~1–2 req/s) and send a descriptive `User-Agent`.
- Python + `requests` + `pandas`. Keep API keys in `.env` and never commit them.

## 5. Suggested split of work

Owners are TBD, so assign these at the next group sync. Each workstream outputs files in the shared schema above.

| Workstream | Deliverable | Depends on |
|---|---|---|
| **A. Drug master** (openFDA + RxNav + FDA Novel Approvals) | `drug_master.csv`: brand, generic, approval date, NME flag, route, class, first indication, first-in-class, NDC list | none (**do this first**, since everyone joins to it) |
| **B. Medicaid SDUD** | `sdud_quarterly.csv`: brand × quarter TRx, FFS + MCO, national | A (NDC list) |
| **C. Medicare Part D** | `partd_annual.csv`: claims, benes, 30-day fills, spend per claim; `fills_per_patient.csv` | A (brand names) |
| **D. Epi + trials** | `epi_funnel.csv` for MVP indication(s), with ranges and sources; trial eligibility notes | none (manual) |
| E. Access/price (stretch) | Part D formulary coverage over time; NADAC reference | A |

## 6. Sequence

1. **Day 1:** agree on keys and schema (§4), push the repo skeleton, build `drug_master.csv` for the 7 seed drugs.
2. **Day 2–3:** SDUD pull for seed drugs, 2011–2025. Sanity-check by plotting raw TRx by quarter since launch. You should see a clear S-curve, with no gaps where a quarter's NDCs went missing.
3. **Day 3–4:** Part D fills-per-patient for the same drugs. Compare fills/patient against the dosing label (e.g. a q12-week injectable should give about 4–5 fills/year).
4. **Day 5:** epi funnel for plaque psoriasis. Then expand the analog list.

## 7. Known data risks to note in the app

- **Medicaid ≠ commercial.** Already in the doc's assumptions, and should stay visible in the UI.
- **Medicaid enrollment shocks** distort trajectories: ACA expansion (2014), continuous enrollment during COVID (2020–2023), unwinding (2023–2024). Consider normalizing TRx per 1,000 enrollees.
- **Specialty pharmacy / limited distribution** brands can be under-represented in retail-type data.
- **Annual-only Part D** gives fills per patient as a yearly average, not a quarterly ramp.
- **NDC churn.** New package NDCs appear after launch. Re-query openFDA/RxNav and keep inactive NDCs.
