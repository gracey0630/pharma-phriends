# Data Sources

What to pull. Tables built from these are in [data_model.md](data_model.md).

**Scope:** US, novel drugs (NME / new BLA), first indication, pharmacy-dispensed only. Analog data is Medicaid/Medicare-based, not commercial. Launches from 2010 onward (SDUD managed-care data starts in 2010).

## Sources

| # | Source | Access | Used for | Priority | ⚠️ Freshness check before each build |
|---|---|---|---|---|---|
| 1 | [CDER NME & New Biologic Approvals compilation](https://www.fda.gov/drugs/drug-approvals-and-databases/compilation-cder-new-molecular-entity-nme-drug-and-new-biologic-approvals) (+ data dictionary) | xlsx | Candidate pool, indication at approval, FDA designations | Core | Newer yearly edition? Spot-check `Approved Use(s)` vs. approval letters |
| 2 | [Drugs@FDA data files](https://www.fda.gov/drugs/drug-approvals-and-databases/drugsfda-data-files) | zip (tab-separated) | Sponsor, approval date, submission class, route/form, later indications, label links | Core | Weekly: re-download |
| 3 | [NDC Directory](https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory) + NDC excluded file | zip (tab-separated) | NDC ↔ brand × route group, market category | Core | Daily: re-download |
| 4 | Medicaid SDUD (data.medicaid.gov, one dataset per year) | CSV per year | Quarterly TRx (analogs + competitors), units per Rx | Core | CMS republishes years; record last-modified; latest 1–2 quarters incomplete |
| 5 | RxClass API (`rxnav.nlm.nih.gov/REST/rxclass`) | API | Class narrow (ATC 4) and broad (ATC 3) | Core | ATC revised yearly: record version |
| 6 | Original approval labels (URLs in Drugs@FDA `ApplicationDocs`) | PDF | **Agent extraction:** indication, dosing, days supply, line of therapy, boxed warning at launch | Core | Fixed; confirm it's the ORIG label |
| 7 | ClinicalTrials.gov API v2 | API | **Agent extraction:** line of therapy, comparators, competitors | Core | Changes daily: date-stamp pulls |
| 8 | Press releases (company sites) + [SEC EDGAR](https://www.sec.gov/edgar/search/) filings | web / API | **Agent extraction:** launch date, competitors at launch | Core | Fixed once found; save a copy |
| 9 | [Novel Drug Approvals reports](https://www.fda.gov/drugs/development-approval-process-drugs/novel-drug-approvals-fda) | web / PDF | First-in-class | Core | Yearly |
| 10 | [FDA REMS list](https://www.accessdata.fda.gov/scripts/cder/rems/) | web | REMS at launch (distortion flag) | Flags | As updated |
| 11 | [Orange Book](https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files) + [Purple Book](https://purplebooksearch.fda.gov/) | tab-separated / CSV | Generic/biosimilar entry (distortion flag) | Flags | Monthly: re-download |
| 12 | Medicaid & CHIP enrollment (data.medicaid.gov) | CSV | Enrollment-shock flag; optional curve normalization | Flags | Monthly |
| 13 | [Medicare Part D Spending by Drug](https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug/medicare-part-d-spending-by-drug) | CSV per release | Days-supply cross-check (units per claim) | Optional | New release yearly |
| 14 | SEER, CDC (NHANES, BRFSS, WONDER), GBD, literature | web / tables / papers | Full epi funnel (optional ceiling path) | Optional | SEER updates each April; save a copy |
| 15 | Treatment guidelines (e.g. NCCN) | read manually | Line-of-therapy definitions | Reference | Check version cited |

**Out of scope for now:** Medicaid Spending by Drug, Part D formulary files, NADAC (fills conversion, access scenarios and pricing aren't in the demo).

## Source rules

| Source | Rule |
|---|---|
| NME compilation | `Approved Use(s)` = indication at original approval. Normalize double-spaced headers. |
| Drugs@FDA | Original approval = earliest `ORIG` + `AP`. Later indications = `EFFICACY` supplements. Match on application number. |
| NDC Directory | Current listings only: add the excluded file + NDCs seen in SDUD. `0069-0187` → `000690187`. Keep NDA/BLA. Route group from `ROUTENAME` (oral, subcutaneous, IV…). |
| SDUD | National rows (`state = XX`); sum FFSU + MCOU; join on 9-digit NDC, not `product_name` (truncated); suppressed rows (< 11 Rx) stay blank, not 0. Pull whole years. |
| RxClass | Narrow = ATC level 4 (e.g. CDK inhibitors); broad = ATC level 3 or a manual family (e.g. JAK family). FDA's pharmacologic class can be too broad. |
| Labels | ORIG label only. DailyMed is the *current* label. |
| ClinicalTrials.gov | Phase 3 + Phase 2 started before approval. "Adjuvant" in metastatic trials usually means *prior* therapy. |
| Press releases / SEC | Launch date = first commercial availability. Cross-check with first SDUD quarter. |
| Agent-read sources | Every extracted value saved with quote + link; a person approves it once. |
| Part D | `Overall` manufacturer row; sum formulations to brand. |
| Epi | Save each page/table to `data/raw/epi/` with URL + access date. |
| Guidelines | Licensed: cite, don't scrape. |

## Pull conventions
- Bulk files > APIs > HTML scraping.
- Raw files go to `data/raw/<source>/` (gitignored), unchanged.
- **Manifest per source:** URL, download date, version / last-modified, file hash, row count. This is how stale files are caught.
- Re-download FDA and CMS files right before any final build.
- Throttle APIs (~1–2 req/s), descriptive `User-Agent`, keys in `.env`.

## Data limits to state in the app
- Pharmacy-dispensed drugs only; no medical-benefit (clinic-administered) data.
- Analog curves are Medicaid (low income), not commercial.
- Distribution data for recent competitors may be unavailable (kept private by manufacturers).
- Enrollment shocks (2014 expansion, COVID, 2023–24 unwinding), label expansions and suppressed quarters distort curves; flagged per analog.
