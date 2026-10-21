# Launch Analog and Input Tool: User Journey

> **Status: draft v1** · last updated 2026-10-21 · transcribed from *Pharma Phriends User Journey.pdf*
> This document is expected to change as we work through the components. Edit it in a PR and add a line to the change log at the bottom. Tables and sources for each step are in [data_model.md](data_model.md) and [data_sources.md](data_sources.md); decisions and open questions are in [decisions.md](decisions.md).

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

**Output:** a saved brand profile that drives the analog search and the epi funnel.
**Tables:** [`target_drug`](data_model.md#scenario-and-output-tables-created-per-forecast)

### 2. Find comparable launches (agent-assisted)
**Analog data (built ahead of time, not at query time):**
- Build the analog pool from the data schema for analogs ([data_model.md](data_model.md); one analog = brand × route group, launches from roughly 2010 onward, since SDUD managed-care records start in 2010)
- Structured sources (NDC directory, Drugs@FDA, SDUD) fill the tabular fields
- The agent reads approved sources (original approval labels, ClinicalTrials.gov, press releases / SEC filings for launch dates) to fill fields that aren't tabular: indication, dosing, class, line of therapy, competitors at launch, launch date
  - Each field is saved with a quote, a link, and a human-approved flag
  - A person reviews the extracted fields once

**Analog agent (at query time):**
- Code applies hard filters: novel NDA/BLA, matching route group, launch window, enough usable SDUD data, and exclusion flags (multi-route brand, generic entry or major indication expansion in the first three years)
- Code scores similarity on the structured features (class, order of entry, dosing frequency, with a small bonus for therapeutic area) and passes the top 20–30 to the agent
- The agent re-ranks that shortlist using line of therapy, competition, and other launch characteristics. It can only reorder or drop drugs, not add new ones.
- The agent proposes about 10 analogs, ranked, each with written reasoning that cites the evidence. The forecaster reviews and approves the final set of 3–5 analog drugs.
- For evaluation, the held-out drug is removed from the pool before any filtering.

**Output:** an approved set of analogs, each with a summary card (match table, rationale with evidence, distortion flags, data quality).
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
For each approved analog, the user sees its launch trajectory: TRx over time, then normalized uptake, then a fitted Bass curve.

**Uptake curve:** the share of a drug's eventual peak TRx reached in each quarter after launch.
- Normalized curves are overlaid, with the spread shown as a band.
- A small table lists each analog's fitted (p, q) and fit quality, flagging weak fits.
- This is a review step. If an analog looks like an outlier or fits poorly, the user can drop it and the (p, q) spread updates.

**Output:** the range of uptake speeds and shapes implied by history.

**The agent writes a summary of the analogs:**
- Similarities and differences between analogs and the new drug
- Which analogs to weight more, and which components to take
- A recommended weighting for the uptake curve, with the reasoning (the weights and curves themselves are computed by code)

**Tables:** `launch_curves`, `bass_fits`, `analog_weights`

### 5. Illustrative sample curve (demo only)
- Combine the similarity-weighted uptake curve band with a placeholder M, using simple hard-coded assumptions
- No access scenarios, fills conversion, or Monte Carlo
- Labeled on screen as "illustrative," with the limitations listed next to it: placeholder M, Medicaid-derived shapes, few analogs, no access or persistence modeling, no validation of the forecast itself

**Output:** a sample curve with a band to show how the analog work feeds a forecast.

---

## Open questions (journey)
Project-wide questions (data, scope, process) are in [decisions.md](decisions.md#open-questions).
- **Which "first" drives matching?** Step 1 asks the forecaster to define first in class / for the indication / at this line; `drug_master` computes all three. Which one feeds the similarity score and the Zipf default?
- **How do agent weights become numbers?** Step 4 says the agent recommends a weighting and code computes it. What's the rule (e.g., similarity score × agent tier, or forecaster-set weights)?
- **When is peak share revisited?** Step 3 says after analogs are approved. Is that a separate screen, or does step 4 feed back into `market_size` automatically?
- **Evaluation:** step 2 holds out one drug. Which drugs make up the test set, and what counts as a good recommendation?

## Change log
| Date | Version | Change |
|---|---|---|
| 2026-10-21 | v1 | Transcribed from the PDF; added table links and open questions |
