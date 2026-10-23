# Decisions & Open Questions

What the team has decided and what's still open. When a question is settled, remove it from the list, add a row to the decision log, and update the doc it affects ([user_journey.md](user_journey.md), [data_sources.md](data_sources.md) or [data_model.md](data_model.md)) in the same PR.

## Decision log

Newest first.

| Date | Decision | Why | Who |
|---|---|---|---|
| 2026-10-23 | ATC class = the brand's own class: for single-ingredient brands, only classes RxClass finds on the ingredient itself; topical / eye classes (ATC D, S) dropped when another remains. Combination brands keep their combination classes; any analog still with several classes is listed in `checks.md` | RxClass returns classes for every product with the ingredient, so 16 analogs carried a combination-product or topical class (SGLT2 and DPP-4 drugs as "combinations", Victoza and Adlyxin as insulins, Jakafi and Daliresp as dermatology, Zytiga as a PARP inhibitor), which put Jakafi and Daliresp in the wrong area. Found in the EDA (`analog_similarity`) | Grace |
| 2026-10-22 | Route fallback: when no NDC under an application has a route, use Drugs@FDA Products. Adds 34 analogs (28 oral, 6 sc; 11 with enough data), e.g. Trikafta, Symdeko, Ocaliva, the first-wave HCV orals. The 16 brands Drugs@FDA lists only as `INJECTABLE;INJECTION` stay out for now (listed in `checks.md`) | Kits (Trikafta) list a blank route and fully delisted applications have none, so these brands were dropped silently. Resolving the injectables needs a label read per brand, deferred | Grace |
| 2026-10-22 | Launch quarter = approved `launch_date` evidence; until then, the first SDUD quarter with any row (a suppressed row still means 1–10 Rx), never before the approval quarter. `launch_source` records which | Label reads cover 8 analogs and none are approved; SDUD exists for 373. Ibrance has a stray SDUD row before approval | Grace |
| 2026-10-22 | Peak for `share_of_peak` = max TRx over Q0–Q20, excluding provisional quarters | Matches the curve window, so later label expansions or generics don't move it. Curves still climbing at Q20 end at 1.0 (`peak_at_last_quarter`) | Grace |
| 2026-10-22 | The latest 2 SDUD quarters are provisional: kept in curves, left out of the peak, the fits and `quarters_of_data` | CMS publishes the latest quarters incomplete | Grace |
| 2026-10-22 | No enrollment normalization in v1: `medicaid_enrollment` is built, but curves are only flagged for fixed shock windows (2014 expansion 2014Q1–2015Q4, COVID continuous coverage 2020Q2–2023Q1, unwinding 2023Q2–2024Q4) | The enrollment dataset has one month before 2017-06 (2013-09), so there's no baseline for the 2014 expansion | Grace |
| 2026-10-22 | Bass is fitted as cumulative m·F(t) to `share_of_peak` (TRx ÷ peak read as share of eventual adopters), for every analog with enough data | Simple and stable; strictly, Bass models new adopters and TRx counts everyone on therapy, so this is stated wherever fits are shown | Grace |
| 2026-10-22 | "In window" for distortion flags = Q0–Q12 | Same 3 years as the "no generic entry in the first 3 years" scope | Grace |
| 2026-10-22 | Fills per patient is dropped: not filled in v1 and not planned | SDUD has no patient counts; Part D is Medicare (never mixed with Medicaid curves) and the current API covers 2020–2024 only, missing most launch years. Fills conversion is out of scope | Grace |
| 2026-10-22 | Market size per analog is dropped: not filled in v1 and not planned. Market sizing stays per forecast (`market_size`, `epi_funnel`) | Trial enrollment on ClinicalTrials.gov is a sample size, not a market; a per-analog size would need epi work for each analog's first indication | Grace |
| 2026-10-22 | Cost per unit stays empty for now. If cost is added later, add cost per Rx (`reimbursed_usd ÷ trx`) and cost per unit (`reimbursed_usd ÷ units`) together, with `units_per_rx` alongside | Each misleads alone: cost per Rx depends on days per fill (a 90-day fill looks 3× a 30-day fill), and cost per unit depends on what a unit is (tablet, mL, pen), so it only compares within one product form. Cost per Rx = cost per unit × units per Rx shows which one drives a difference. Both are gross SDUD reimbursement (before rebates), not prices | Grace |
| 2026-10-21 | v1 analog table uses only the 23 columns of the analog schema sheet, with the sheet's names and order (`data/processed/analogs.csv`, key `analog_id`) | Keep v1 simple enough for the whole team to follow; larger tables in data_model.md are deferred | Jmazher12 |
| 2026-10-21 | Commit `data/processed/`; `data/raw/` stays gitignored and is rebuilt with `python -m pipeline.build` | Teammates can pick up the data without a ~1 hour SDUD download | Jmazher12 |
| 2026-10-21 | Cost per unit, fills per patient and market size are kept as empty columns for now | They're in the sheet but pricing, fills conversion and epi are out of scope or owned elsewhere (see open questions) | Jmazher12 |
| 2026-10-21 | Class (narrow) = RxClass ATC level 4 (e.g. `L04AC Interleukin inhibitors`), not DailyMed MoA | DailyMed is the current label, not the original; ATC is structured and consistent across the pool | Jmazher12 |
| 2026-10-21 | In-scope route groups are `oral` and `sc` (NDC `ROUTENAME` = ORAL / SUBCUTANEOUS). Delisted NDCs (excluded file, no route) take the route of the earliest listed NDC under the same application | Matches the self-administered scope; launch-era NDCs are often delisted | Jmazher12 |
| 2026-10-21 | SDUD is pulled as national rows (`state = XX`) for whole years via the data.medicaid.gov API, not the full state-level CSVs | ~300k rows/year instead of ~8 GB; national rows are all the analog curves use | Jmazher12 |
| 2026-10-21 | Generic / exclusivity date = first SDUD quarter a generic (ANDA) or biosimilar (351(k)) NDC is dispensed | ANDA approvals and NDC listings often precede launch by years (e.g. apremilast, apixaban) | Jmazher12 |
| 2026-10-21 | Launch date = first commercial availability from a press release or trade press; `YYYY-MM` allowed when only the month is stated | Releases often say "available in early May" rather than a day | Jmazher12 |
| 2026-10-21 | # competitors at launch = branded advanced systemic therapies (biologic or novel oral) approved for the same first indication before launch; excludes biosimilars and withdrawn drugs | One countable definition for the label reads | Jmazher12 |

## Open questions

**Owners and process**
- Who owns workstreams A–E ([data_model.md](data_model.md#workstreams))?

**Empty columns in the v1 analog table** (see [v1 analog table](data_model.md#v1-analog-table-current-spec))
- **Dropped columns:** fills per patient and market size are dropped (decision log, 2026-10-22). Remove them from `analogs.csv` and the schema sheet, or keep them as empty columns so the table still matches the sheet's 23 columns?

**Data**
- **Peak inside Q0–Q20:** 89 of the 201 analogs with a full window peak at Q20. Some may be enrollment-driven: Taltz and Tremfya speed up late, and their Q20 falls in the COVID enrollment growth (Medicaid +33%, 2020–23). Keep the Q0–Q20 peak, use the all-time peak, or adjust for enrollment from 2017 on? (EDA first)
- Do we need archived Part D releases (pre-2020)? The current API covers 2020–2024 only, and Part D is a cross-check, but in oncology Medicare volume is ~7× Medicaid (Ibrance 2024).

**Scope**
- One therapeutic area or two for the demo? The prototype covered immunology (Otezla, Cosentyx, Taltz, Siliq, Tremfya, Skyrizi, Sotyktu) and one oncology analog (Ibrance). Oncology curves plateaued by ~Q12 while immunology biologics were still climbing at Q20, so fitting by area (or letting *p* differ) may matter.
