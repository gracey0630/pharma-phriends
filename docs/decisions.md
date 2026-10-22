# Decisions & Open Questions

What the team has decided and what's still open. When a question is settled, remove it from the list, add a row to the decision log, and update the doc it affects ([user_journey.md](user_journey.md), [data_sources.md](data_sources.md) or [data_model.md](data_model.md)) in the same PR.

## Decision log

Newest first.

| Date | Decision | Why | Who |
|---|---|---|---|
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
- Normalize SDUD TRx by Medicaid enrollment (`trx_per_1k_enrollees`), or only flag enrollment shocks (2014 expansion, COVID, 2023–24 unwinding)?
- Do we need archived Part D releases (pre-2020)? The current API covers 2020–2024 only, and Part D is a cross-check, but in oncology Medicare volume is ~7× Medicaid (Ibrance 2024).

**Scope**
- One therapeutic area or two for the demo? The prototype covered immunology (Otezla, Cosentyx, Taltz, Siliq, Tremfya, Skyrizi, Sotyktu) and one oncology analog (Ibrance). Oncology curves plateaued by ~Q12 while immunology biologics were still climbing at Q20, so fitting by area (or letting *p* differ) may matter.
