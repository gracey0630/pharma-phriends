# Project Log: Pharma Phriends Launch Forecast Tool

Running notes on data collection: what we tried, what worked, and what we decided. Newest entry on top. Put your name on each entry.

---

## 2026-10-13 (part 2): First scrapers built and run (Josh)

### What got built
| File | What it does | Output |
|---|---|---|
| `scrapers/common.py` | Cached + throttled GET (0.5 s between calls, retries on 429/5xx), per-source `manifest.csv` of every live call, NDC formatting | `data/raw/<source>/` (gitignored) |
| `scrapers/openfda.py` | Drugs@FDA + NDC directory + label for each seed brand | `data/reference/drug_master.csv` |
| `scrapers/sdud.py` | National Medicaid TRx by quarter, FFSU + MCOU summed | `data/processed/sdud_quarterly.csv`, `sdud_ndc_audit.csv` |
| `scrapers/partd.py` | Medicare Part D Spending by Drug, formulations summed to brand | `data/processed/partd_annual.csv` |
| `scrapers/plot_check.py` | Sanity plot of TRx vs. quarters since approval | `data/processed/sdud_launch_curves.png` |

Run order: `python -m scrapers.openfda` → `python -m scrapers.sdud` → `python -m scrapers.partd` → `python -m scrapers.plot_check`.

### Results
**Drug master (openFDA):** all 7 seed drugs are confirmed "Type 1 - New Molecular Entity".
| Brand | Application | Approval | Route |
|---|---|---|---|
| Otezla | NDA205437 | 2014-03-21 (PsA, its first indication) | oral |
| Cosentyx | BLA125504 | 2015-01-21 | SC |
| Taltz | BLA125521 | 2016-03-22 | SC |
| Siliq | BLA761032 | 2017-02-15 | SC |
| Tremfya | BLA761061 | 2017-07-13 | SC (IV added later) |
| Skyrizi | BLA761105 | 2019-04-23 | SC (IV added later) |
| Sotyktu | NDA214958 | 2022-09-09 | oral |

`first_indication`, `line_of_therapy` and `first_in_class` are still blank. They need manual or agent tagging from `indications_text`.

**SDUD (Medicaid national TRx):** 732 rows covering 7 brands × all quarters since approval. Latest-quarter TRx (2025Q4): Cosentyx 39.6k, Skyrizi 23.5k, Taltz 19.0k, Otezla 17.8k, Tremfya 11.3k, Sotyktu 1.1k, Siliq ~0 (suppressed).

**Part D fills per patient per year (2024):** Siliq 8.0, Otezla 6.9, Cosentyx 6.5, Taltz 5.9, Sotyktu 4.8, Tremfya 4.2, Skyrizi 3.3. These roughly follow dosing frequency: Skyrizi q12w has a max of ~4.3/yr and Tremfya q8w a max of ~6.5/yr. They sit below the max because of mid-year starts and drop-off.

### Findings and gotchas (new today)
1. **National (`XX`) SDUD rows *can* be suppressed.** Earlier I wrote that they never are, which was wrong (the plan is now corrected). Siliq 2025Q4 is fully suppressed, and launch quarters for Cosentyx 2015Q1, Taltz 2016Q2 and Siliq 2017Q3–Q4 are blank. The first run summed suppressed nulls to **0**; this is fixed with `sum(min_count=1)` plus a new `suppressed_rows` metric. The undercount is ≤ 10 Rx × suppressed rows per quarter.
2. **openFDA lists only current NDCs.** Otezla's Celgene-era NDCs (labeler 59572, about 160k Rx from 2014–2019) aren't in openFDA, because Amgen relabeled after buying the drug in 2019. A strict NDC join would have dropped Otezla's entire launch. We now match by 10-char name prefix and audit against the FDA list in `sdud_ndc_audit.csv`.
3. **The latest SDUD quarter is incomplete.** 2026Q1 dips for every brand. Treat the last 1–2 quarters as provisional.
4. **SDUD LIKE queries are slow,** about 10 s each on the server, so a full pull of 7 brands took ~12 min. Re-runs come from the cache in seconds.
5. **Part D API only has 2020–2024.** The catalog lists two API endpoints for the 2024 release with identical fields. Earlier years (needed for Otezla, Cosentyx, Taltz, Siliq and Tremfya launches) are only in archived releases, so downloading those is a separate task.
6. **Part D brands are split by formulation** ("Cosentyx Sensoready Pen", "Taltz Autoinjector (2 Pack)"…). We sum them to brand level, which slightly double-counts beneficiaries who used two forms in a year.
7. **The curves look right.** In the plot there are smooth S-shaped ramps and no holes from missing NDCs. Biologics are still climbing at 20 quarters, so the historical curves won't show a peak and M has to come from the epi funnel. Siliq barely launches (suicidality boxed warning, REMS), a good outlier test case for "drop an analog".
8. **Approval date ≠ launch date.** Siliq's first Rx appears about 2 quarters after approval. Consider aligning curves on the first quarter with TRx > 0 instead of the approval quarter.

### Next steps
- [ ] Group sign-off on the plan; assign workstreams
- [ ] Tag first indication / line of therapy / first-in-class in `drug_master.csv`
- [ ] Get archived Part D releases (2012–2019) for older launches
- [ ] Decide on launch alignment (approval quarter vs. first-Rx quarter)
- [ ] Get an openFDA API key and add it to `.env` as `OPENFDA_API_KEY`
- [ ] Expand the analog list beyond immunology

---

## 2026-10-13: Data collection kickoff (Josh)

### Goal for today
Plan how to collect data for the launch forecast tool, starting with Medicare/Medicaid. The full plan is in [docs/data_collection_plan.md](docs/data_collection_plan.md).

### Context reviewed
- Read *Pharma Phriends User Journey.pdf*. Needs that drive data collection:
  - **Analog TRx trajectories** (quarterly), to fit Bass p, q (step 4) and to backtest (step 9). The doc names SDUD, quarterly, as the backtest source.
  - **Analog attributes** for the agent's ranking: route, line of therapy, competition, first-in-class (step 3).
  - **Fills per patient**, filtered by dosing / days supply / route (step 6).
  - **Epi funnel** ranges with source tags (step 2).
  - Fixed assumptions: US, NME, first indication, retail pharmacy. Analog data are Medicaid-based.
- GitHub repo `gracey0630/pharma-phriends` is **empty** (checked with `gh`). There's no existing structure to follow, so the plan proposes one.

### Source checks (all live-tested today)

#### Medicaid SDUD (data.medicaid.gov)
- The catalog search `api/1/search?fulltext=state drug utilization data` returns 36 datasets, one per year from 1991 to 2026.
- Query pattern that works:
  `https://data.medicaid.gov/api/1/datastore/query/{id}/0?limit=N&conditions[0][property]=state&conditions[0][value]=XX&conditions[0][operator]==`
- `operator=like` with `%` wildcards also works (e.g. `product_name LIKE SKYRIZI%`).
- 2023 dataset has **5,326,586 rows**, too big to pull whole. Filter server-side.
- **Gotchas found:**
  - `product_name` is cut to 10 chars and padded with spaces: `"SKYRIZI   "`, `"SKYRIZI ON"`, `"SKYRIZI 15"`. An exact match on `"SKYRIZI"` returned 0 rows. **Join on NDC, not name.**
  - State-level rows with small counts are suppressed (`suppression_used: true`, all metrics null). Example: Skyrizi in AK, 2023Q4.
  - **`state = 'XX'` rows are national totals and are not suppressed.** *(Correction, part 2: they can be. See finding 1 above.)* Skyrizi 2023Q4 national rows: 47. Example: NDC 00074105001, FFSU 832 Rx, MCOU 701 Rx.
  - `utilization_type` has two values, `FFSU` (fee-for-service) and `MCOU` (managed care). Both have to be summed.
- Example row fields: `utilization_type, state, ndc, labeler_code, product_code, package_size, year, quarter, suppression_used, product_name, units_reimbursed, number_of_prescriptions, total_amount_reimbursed, medicaid_amount_reimbursed, non_medicaid_amount_reimbursed`.

##### SDUD dataset IDs
| Year | Dataset ID |
|---|---|
| 2010 | 1db0f12c-e4d6-5a70-8c1b-5af9635999be |
| 2011 | 138872f1-b1ba-5e05-be13-8be200306a58 |
| 2012 | 992936b2-2a72-5df6-a734-a56a8631b87a |
| 2013 | 6a91f80f-e2fd-5f43-8e38-afcebebb8387 |
| 2014 | a9cfe5e9-d7d8-5b87-a7db-b45a7daf84fc |
| 2015 | 2fed5758-5fd6-5dbb-8f92-34b3a0c3c8dd |
| 2016 | 53cf9f05-97e3-5bd6-a237-bc971e3642d9 |
| 2017 | 776a3880-a62d-5990-8b40-4406e6861dbb |
| 2018 | a1f3598e-fc71-51aa-8560-78e7e1a61b09 |
| 2019 | daba7980-e219-5996-9bec-90358fd156f1 |
| 2020 | cc318bfb-a9b2-55f3-a924-d47376b32ea3 |
| 2021 | eec7fbe6-c4c4-5915-b3d0-be5828ef4e9d |
| 2022 | 200c2cba-e58d-4a95-aa60-14b99736808d |
| 2023 | d890d3a9-6b00-43fd-8b31-fcba4c8e2909 |
| 2024 | 61729e5a-7aa8-448c-8903-ba3e0cd0ea3c |
| 2025 | 158a1baa-5506-400a-8ec3-97756f0b0536 |
| 2026 | 2957a7f9-9a15-453e-9afd-3bbdcbac8fd3 |

Earlier years (1991–2009) also exist. Re-run the catalog search to get their IDs if needed. Several datasets were modified 2026-04 and 2026-07, so **IDs may change when CMS republishes.** Look them up from the catalog in code rather than hard-coding them.

#### NADAC (data.medicaid.gov)
- Yearly datasets exist. 2026: `fbb83258-11c7-47f5-8b18-5f8e79f7e704`, 2025: `f38d0706-1239-442c-a3cc-40ef1b686ac0`, 2024: `99315a95-37ac-4eee-946a-3c523b4c481e`.

#### Medicare (data.cms.gov)
- Catalog: `https://data.cms.gov/data.json`. Relevant datasets found:
  - Medicare Part D Spending by Drug (annual)
  - Medicare Quarterly Part D Spending by Drug (latest quarter 2026Q1)
  - Medicare Part B Spending by Drug (annual and quarterly, for physician-administered drugs, which are out of scope)
  - Medicare Part D Prescribers by Provider and Drug / by Geography and Drug / by Provider
  - Monthly Prescription Drug Plan Formulary and Pharmacy Network Information (monthly files from 2019 on), for the access workstream
- **Part D Spending by Drug** API: `https://data.cms.gov/data-api/v1/dataset/7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b/data`
  - Current release covers **2020–2024** in wide format: `Tot_Spndng_YYYY, Tot_Dsg_Unts_YYYY, Tot_Clms_YYYY, Tot_Benes_YYYY, Avg_Spnd_Per_Clm_YYYY, Avg_Spnd_Per_Bene_YYYY, Outlier_Flag_YYYY`.
  - Each brand has an `Mftr_Name = "Overall"` row plus one row per manufacturer. Use the "Overall" row.
  - `filter[Brnd_Name]=Skyrizi` returned `[]`, but `keyword=Skyrizi` worked. Brand names are split by formulation ("Skyrizi On-Body").
  - Sanity check: Skyrizi On-Body 2024 has 19,225 claims / 4,897 benes, about 3.9 fills per beneficiary per year.
  - **This is our fills-per-patient source.** SDUD has no patient counts.

#### openFDA
- `drug/drugsfda.json?search=openfda.brand_name:"SKYRIZI"` returns BLA761105, AbbVie, ORIG approval 2019-04-23, "Type 1 - New Molecular Entity", route SC + IV, class "Interleukin-23 Antagonist [EPC]", and 13 product NDCs (e.g. `0074-1050`).
- The product NDC `0074-1050` maps to SDUD `labeler_code=00074, product_code=1050`. **The join works.**
- Without an API key the limit is 1,000 requests/day. We need a free key.

#### RxNav (NLM)
- `REST/drugs.json?name=skyrizi` returns SBD concepts with RxCUIs. Works.

#### ClinicalTrials.gov API v2
- `api/v2/studies?query.intr=risankizumab&fields=NCTId,BriefTitle,Phase,EnrollmentInfo` works and returns phase and enrollment.

### Decisions / proposals (need group sign-off)
1. **Drug master table first**, keyed on `brand_key` and NDC. Every other dataset joins to it.
2. **SDUD: national (`XX`) rows only, FFSU + MCOU summed, joined on labeler + product code.**
3. **Part D Spending by Drug** gives `Tot_Clms / Tot_Benes` as fills per patient.
4. **Epi funnel is hand-curated** with source tags, not scraped.
5. **MVP analog set:** immunology/derm NMEs approved 2011–2022 with retail distribution. Candidates: Otezla, Cosentyx, Taltz, Siliq, Tremfya, Skyrizi, Sotyktu. Approval dates and first indications still need checking in openFDA.
6. Shared long-format schema: `brand_key, source, payer, period, metric, value, pulled_at`.

### Open questions
- Who owns which workstream (A–E in the plan)?
- Do we want one MVP therapeutic area or two before building the model?
- Do we normalize SDUD TRx by Medicaid enrollment to remove the 2014 expansion and COVID-era jumps?
- Is the Part D older-release archive (pre-2020) needed for launches like Otezla (2014) and Cosentyx (2015)? Probably yes.

### Next steps
- [ ] Share plan with group; assign workstreams
- [ ] Initialize local git repo, add skeleton + `.gitignore`, push to `gracey0630/pharma-phriends`
- [ ] Write `scrapers/openfda.py` and build `drug_master.csv` for the 7 seed drugs
- [ ] Write `scrapers/sdud.py` (national, NDC-filtered, cached) and plot raw TRx curves for seed drugs
