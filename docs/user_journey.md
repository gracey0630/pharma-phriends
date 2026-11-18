# Launch Analog and Input Tool: User Journey

> **Status: draft v2** · last updated 2026-11-17 · v1 transcribed from [user_journey_v1.pdf](user_journey_v1.pdf); v2 follows the agreed [implementation plan](implementation_plan.md) (decisions D1–D8). Earlier versions are in [archive/](archive/).
> This document is expected to change as we work through the components. Edit it in a PR and add a line to the change log at the bottom. Tables and sources for each step are in [data_model.md](data_model.md) and [data_sources.md](data_sources.md); decisions and open questions are in [decisions.md](decisions.md); how steps 2 and 4 are built is in [implementation_plan.md](implementation_plan.md).

**Motivating question:** How many TRx will a new brand sell in its first three years, how uncertain is that, and what drives the uncertainty?

**Purpose:** Help a pharma forecasting team choose and defend the two inputs a launch forecast depends on: how big the launch can get (the **ceiling**) and how fast it gets there (the **trajectory**). The tool recommends comparable launches, sizes the market, and shows an illustrative curve with its limitations stated.

## Users
- **Primary user: forecaster.** Enters the profile, reviews and approves analogs, sets the funnel assumptions, defends the inputs.
- **Audience for results: brand leadership and finance.** They see the analog set, the ceiling and trajectory assumptions, and the illustrative curve through the memo and final presentation, and use them to judge whether the inputs are defensible and what forecast to commission.

## Fixed assumptions (not user inputs)
- **US only.**
- **New molecular entity or new therapeutic biologic** (NDA or BLA brand), first indication, with no generic entry in its first three years.
- **Pharmacy-dispensed, self-administered products** (oral or self-injected). Clinic-administered drugs are out of scope because our data barely covers them.
- **Unit of analysis: dispensed prescriptions** (not shipments). One analog = one brand × route group.
- **Payer population:** analog curves come from Medicaid dispensing data (Medicare Part D is used for cross-checks), so they may differ from commercial behavior. Any curve we show states this.
- **Medicaid data reading (not confirmed with CMS):** a quarter with no SDUD row means 0 prescriptions, and a suppressed row holds fewer than 11.

## Two questions for leadership
- **How big can the launch be (ceiling)?** Epi funnel
  - Prevalent population → diagnosed → drug-treated → eligible → peak brand share → M
  - Line of therapy: first-line M is much larger than third-line M
  - Peak brand share: default from order of entry (Zipf)
- **How fast can we get to the ceiling (trajectory)?** Analogs
  - Borrow uptake shape (Bass p and q) from previous launches
  - Novelty: first in class, or entering a competitive market
  - Line of therapy and competition shape which launches are comparable

## Data limits to state up front
- Distribution channel (pharmacy-based vs. medical-based): our data covers pharmacy-dispensed drugs only.
- For novel competitive drugs, distribution data may not be available, because manufacturers may keep it private.

---

## Forecaster journey

### 1. Define the drug
The forecaster enters the brand profile:
- Indication and target patient definition (e.g., adults with moderate-to-severe plaque psoriasis who are candidates for systemic therapy and have not yet received a biologic)
- Class (narrow and broad, e.g., TYK2 inhibitor / JAK family)
- Route of administration / formulation (oral, self-injected)
- Line of therapy
- Order of entry (rank among entrants) and expected eventual number of entrants
  - Define what "first" means: first in class, first for the indication, or first at this line
  - Classes can compete with each other and can expand
- Competitors at launch
  - Number of competitors
  - How the drug compares on efficacy and safety to the standard of care
- Dosing frequency and days supply (one of the most important)
  - Important: how it compares to current alternatives
- Launch date

The profile is saved as a scenario file (`analog_finder/scenarios/<scenario>.yaml`, e.g. `torevia.yaml` for the [example drug](example_drug.md)). It can also set the forecaster's **feature preferences**: weights for how much each feature counts in the similarity score (step 2), overriding the defaults (D7).

**Output:** a saved brand profile that drives the analog search and the epi funnel.
**Tables:** [`target_drug`](data_model.md#scenario-and-output-tables-created-per-forecast)

### 2. Find comparable launches
**Analog data (built ahead of time, not at query time):**
- Build the analog pool from the data schema for analogs ([data_model.md](data_model.md); one analog = brand × route group, launches from roughly 2010 onward, since SDUD managed-care records start in 2010)
- Structured sources (NME compilation, NDC directory, Drugs@FDA, RxClass, SDUD) fill the tabular fields, including indication at approval and class (ATC)
- **Label Research Agent (Stage 1):** reads approved sources only (original approval labels, press releases / SEC filings, Drugs@FDA; the list is in [data_sources.md](data_sources.md#approved-source-list)) to fill the four fields that aren't tabular: line of therapy, dosing frequency, launch date, # competitors at launch
  - Each value is saved with a verbatim quote, a link and a quote check, as an unapproved row; it never overwrites an approved row
  - A person approves, edits or rejects each value once, in the app's review screen or the spreadsheet. Only approved values are used in matching (D8)

**Analog Finder (Stage 2, at query time):**
- **Hard filters** run first (D1, D2): only the usable analogs from the `checks.md` funnel (which already excludes generic entry in the first three years and late launches) in the target's route group. Possible label expansion and multi-route brands are **warnings** shown on the card, not exclusions.
- **Similarity score** (D6): a hybrid of text similarity between profile texts (indication, class, route and form, plus approved label reads; RxBERT or TF-IDF) and one score per structured feature (ATC 4, ATC 3, therapeutic area, line of therapy, dosing frequency, # competitors, order of entry), combined with the forecaster's feature weights (D7). A feature the analog or target lacks is left out, not counted as a mismatch. Ranking is deterministic.
- **Top 5, confirmed one at a time** (D3): each candidate is shown with a summary card. The forecaster confirms or rejects it; a rejection brings in the next-ranked candidate with a new card. The forecaster can stop at 3–5 confirmed. Every decision and reason is logged.
- **Summary cards** (D4): the language model writes the card from the facts it's given (similarities, differences, score breakdown, flags, sources); it doesn't re-rank or add drugs. Without an API key, a template card is used.
- For evaluation, the held-out drug is removed from the pool before any filtering.

**Output:** a confirmed set of 3–5 analogs, each with a summary card (headline, similarities and differences, per-feature score breakdown, warning flags, sources with quotes).
**Tables:** built ahead: `candidate_pool`, `analog_evidence`, `ndc_map`, `sdud_quarterly`, `indication_history`, `exclusivity`, `drug_master`, `analog_features`; per forecast: `analog_recommendations` (all in [data_model.md](data_model.md))

### 3. Understand the potential market
Ideally, the user would perform an epidemiology funnel study to define the distribution of each stage: prevalent population → diagnosed → drug-treated → eligible → peak brand share → M (peak patients on therapy).

**Simplified version:** M = eligible patient population × peak brand share, with peak brand share defaulted from Zipf's law (order of entry vs. share of the market).
- Inputs: eligible patient population (one sourced range), order of entry (from step 1), number of eventual entrants (a range), alpha, i.e., how steeply share falls with rank (a range)
- Optional differentiation adjustment, with a written reason
- Revisit peak brand share after the analogs are approved
- Optional: compare the default share with analog peak shares

**Output:** a range for peak patients on therapy (M).
**Tables:** `market_size`, `epi_funnel` (optional)

### 4. Review historical uptake
For each confirmed analog, the user sees its launch trajectory: TRx over time, then normalized uptake, then a fitted Bass curve.

**Uptake curve:** the share of a drug's eventual peak TRx reached in each quarter after launch.
- Normalized curves are overlaid, with the spread shown as a band (min–max of the confirmed analogs).
- **Weighted uptake curve** (D5): each confirmed analog's weight is its similarity score, normalized so the weights sum to 1. The curve covers Q0–Q20; where an analog has no data for a quarter, the average uses the analogs available and the number is shown.
- The forecaster can override any weight with a written reason (setting it to 0 drops the analog), and the curve and (p, q) spread update.
- A small table lists each analog's fitted (p, q) and fit quality, flagging weak fits.
- This is a review step. Similarities and differences with the new drug are on each analog's summary card from step 2.

**Output:** the range of uptake speeds and shapes implied by history, and one similarity-weighted curve with its band.

**Tables:** `launch_curves`, `bass_fits`, `analog_weights`, `uptake_curve`

### 5. Illustrative sample curve (demo only)
- Combine the similarity-weighted uptake curve band with a placeholder M, using simple hard-coded assumptions
- No access scenarios, fills conversion, or Monte Carlo
- Labeled on screen as "illustrative," with the limitations listed next to it: placeholder M, Medicaid-derived shapes, few analogs, no access or persistence modeling, no validation of the forecast itself

**Output:** a sample curve with a band to show how the analog work feeds a forecast.

---

## Open questions (journey)
Project-wide questions (data, scope, process) are in [decisions.md](decisions.md#open-questions).
- **Which "first" drives matching?** Step 1 asks the forecaster to define first in class / for the indication / at this line; `drug_master` computes all three. Which one feeds the similarity score and the Zipf default?
- **When is peak share revisited?** Step 3 says after analogs are approved. Is that a separate screen, or does step 4 feed back into `market_size` automatically?

Settled in v2: how weights become numbers (D5) and evaluation (leave-one-out holdout against the all-analog median; [decisions.md](decisions.md), 2026-11-17).

## Change log
| Date | Version | Change |
|---|---|---|
| 2026-11-17 | v2 | Follows the agreed [implementation plan](implementation_plan.md): step 1 saved as a scenario file with feature preferences; step 2 split into the Label Research Agent (approved sources, four fields) and the Analog Finder (hard filters, hybrid similarity, top 5 confirmed one at a time, model writes summary cards only, no re-rank); step 4 similarity weights with overrides and the `uptake_curve` table. Removed the settled open questions on weights and evaluation. v1 in [archive/](archive/user_journey_2026-11-17.md) |
| 2026-10-21 | v1 | Transcribed from the PDF; added table links and open questions |
