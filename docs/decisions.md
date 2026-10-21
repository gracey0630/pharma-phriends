# Decisions & Open Questions

What the team has decided and what's still open. When a question is settled, remove it from the list, add a row to the decision log, and update the doc it affects ([user_journey.md](user_journey.md), [data_sources.md](data_sources.md) or [data_model.md](data_model.md)) in the same PR.

## Decision log

Newest first.

| Date | Decision | Why | Who |
|---|---|---|---|

## Open questions

**Owners and process**
- Who owns workstreams A–E ([data_model.md](data_model.md#workstreams))?
- Commit `data/processed/` (from merged PRs only), or keep it local and rebuild?

**Gaps between the original analog schema (Google Sheet) and the docs** (see the [crosswalk](data_model.md#crosswalk-original-analog-schema--tables))
- **Cost per unit:** the sheet lists it (Medicaid Spending by Drug, Part D), but pricing is out of scope. Drop it, or keep `reimbursed_usd ÷ units` from SDUD as a descriptive field?
- **Fills per patient:** the sheet lists it (Part D claims ÷ beneficiaries), but fills conversion is out of scope and no table has it. Keep it as an analog feature (dosing check) or drop it?
- **Market size from ClinicalTrials.gov:** the sheet lists trial reports as a market-size source; the docs use CT.gov only for line of therapy and competitors. Use trial enrollment or eligibility for the "eligible" funnel stage?
- **Class narrow:** the sheet derives it from the mechanism of action in DailyMed; the docs use RxClass ATC plus agent extraction from the ORIG label. Confirm the docs' approach.

**Data**
- Normalize SDUD TRx by Medicaid enrollment (`trx_per_1k_enrollees`), or only flag enrollment shocks (2014 expansion, COVID, 2023–24 unwinding)?
- Do we need archived Part D releases (pre-2020)? The current API covers 2020–2024 only, and Part D is a cross-check, but in oncology Medicare volume is ~7× Medicaid (Ibrance 2024).

**Scope**
- One therapeutic area or two for the demo? The prototype covered immunology (Otezla, Cosentyx, Taltz, Siliq, Tremfya, Skyrizi, Sotyktu) and one oncology analog (Ibrance). Oncology curves plateaued by ~Q12 while immunology biologics were still climbing at Q20, so fitting by area (or letting *p* differ) may matter.
