# Example drug: Torevia (velapiprazole)

> **Status: agreed by the team** · 2026-10-27 · Christina · logged in [decisions.md](decisions.md)
> The example drug for the demo: a fictional drug to run the tool end to end (user journey steps 1–5). The name and molecule are invented; check that neither matches a real product before using them in slides.

**Data:** `data/processed/` on `main` at `1bc6134` (ATC class fix). EDA references are the write-ups on the `eda` branch (`eda/eda_*.md`).

## Summary

A once-daily oral antipsychotic for adults with schizophrenia, launching in January 2027 as the 7th branded novel antipsychotic. Chosen because it has the cleanest analog set in our data:

- **5 usable analogs in the same market:** Latuda, Rexulti, Vraylar, Caplyta, Lybalvi (all oral, schizophrenia).
- **High Medicaid volume** (peak 34k–206k TRx a quarter), so the Bass fits are trustworthy: all five have R² ≈ 0.99 and none is weak. Low volume is the main cause of weak fits (`volume_vs_shape`).
- **Medicaid is the most representative payer here.** Medicaid is widely reported as the largest payer for schizophrenia care (cite a source before presenting), which answers the "can Medicaid curves stand in for the market?" question better than any other area.
- **In scope:** novel oral drug, pharmacy-dispensed, self-administered, first indication only, no generic entry in its first 3 years.

## Why schizophrenia (nervous system), not psoriasis (immunology)

| | Schizophrenia (nervous system) | Psoriasis (immunology) |
|---|---|---|
| Close usable analogs | 5 oral antipsychotics | 7 psoriasis drugs (the 6 seed brands + Ilumya), plus Otezla (psoriatic arthritis first) |
| Medicaid volume | Large: peak 34k–206k TRx a quarter | Mixed: Siliq 358, Ilumya 604, up to Cosentyx 15k |
| Bass fits | All 5 good (R² 0.99) | 2 of 7 psoriasis drugs weak (Taltz, Tremfya: m at the cap) |
| Medicaid representative? | Yes: Medicaid is the largest payer for schizophrenia | Weaker: psoriasis biologics are mostly commercial |
| Clinic-administered products | None (all oral) | Yes (Ilumya); no self-administered flag yet |
| Label reads done | None yet (~20 values to read) | 27 seed values approved (PR #6) |

The one advantage of psoriasis is the label reads already done. The antipsychotic set is small enough to read quickly.

## Drug profile

Fields follow the `target_drug` table ([data_model.md](data_model.md#scenario-and-output-tables-created-per-forecast)).

| Field | Value |
|---|---|
| `indication` | Treatment of schizophrenia in adults. Schizophrenia only at launch, to match the first-indication scope |
| `target_patient_definition` | Adults with schizophrenia on antipsychotic therapy who switch because of inadequate response or intolerance (weight gain, metabolic effects, movement disorders) on a generic antipsychotic |
| `class_narrow` | ATC N05AX Other antipsychotics (a D2 / 5-HT1A partial agonist, like aripiprazole and brexpiprazole) |
| `class_broad` | ATC N05A Antipsychotics |
| `route_group` | oral |
| `dosage_form` | Tablet, 15 mg |
| `line_of_therapy` | Second line in practice: after at least one generic antipsychotic. Medicaid preferred-drug lists usually require a generic first, and that step is already in the analogs' Medicaid curves |
| `entry_order` | 7th branded novel antipsychotic, after Latuda (2010), Rexulti (2015), Vraylar (2015), Caplyta (2019), Lybalvi (2021), Cobenfy (2024) |
| `first_definition` | Not first in class, for the indication or at this line |
| `expected_n_entrants` | 8–10 |
| `n_competitors_at_launch` | 6 branded novel antipsychotics; generics are the standard of care |
| `efficacy_safety_vs_soc` | Similar efficacy; less weight gain and fewer metabolic effects; low risk of movement disorders (EPS) |
| `dosing_frequency` | Once daily, no titration |
| `days_supply` | 30 |
| `dosing_vs_alternatives` | Same as most branded alternatives; simpler than Cobenfy (twice daily, titrated) |
| `launch_date` | 2027-01 |

**Why a late entrant, not a new mechanism:** four of the five analogs were also late entrants into a market where generics are the standard of care, so the analog set matches the target. A novel mechanism would have only Cobenfy as a close analog, and it has 4 quarters of data (not usable).

## Expected analogs

From `launch_curves.csv` and `analog_features.csv`. Share of peak is against the Q0–Q20 peak.

| Analog | Approved | Launch quarter | Share of peak Q4 / Q8 / Q12 | Peak quarter | Peak TRx a quarter | Possible expansion in Q0–Q12 |
|---|---|---|---|---|---|---|
| Latuda | 2010-10 | 2011Q1 | 0.15 / 0.24 / 0.44 | Q20 | 206,071 | Q5, Q9 |
| Rexulti | 2015-07 | 2015Q3 | 0.34 / 0.57 / 0.74 | Q20 | 63,588 | Q4 |
| Vraylar | 2015-09 | 2016Q1 | 0.13 / 0.23 / 0.39 | Q20 | 126,982 | Q7 |
| Caplyta | 2019-12 | 2020Q2 | 0.10 / 0.28 / 0.59 | Q20 | 60,938 | Q6 |
| Lybalvi | 2021-05 | 2021Q4 | 0.36 / 0.61 / 0.80 | Q15 | 33,885 | none |

- **Wide spread at year 3: 0.39 to 0.80 of peak.** That fits the EDA's recommendation to show the analogs' range, not one borrowed curve (`analog_similarity`).
- **Part of the spread is probably indications.** Rexulti launched with MDD (adjunct) as well as schizophrenia, and Lybalvi with bipolar I. Latuda (bipolar depression) and Caplyta (bipolar depression) added indications within 3 years. These are leads until the approval letters are read.
- **Wider pool for comparison:** the 41 usable nervous-system analogs (7 of 41 weak fits, median R² 0.98), and the large Medicaid-volume band (`volume_vs_shape`).

## Ceiling inputs (illustrative; need sourcing)

M = eligible patients × peak brand share (user journey step 3).

| Input | Value | Source / status |
|---|---|---|
| Prevalence | 0.25–0.64% of US adults, about 0.65–1.7 million | NIMH; confirm the current page and the adult population used |
| Diagnosed, treated, switch candidates | To source | Literature / CDC; needs ranges |
| Order of entry / eventual entrants | 7th of 8–10 | Profile above |
| Peak brand share (Zipf) | ~5% at α = 1 (3% at α = 1.5, 8% at α = 0.5), for 7th of 9 entrants | Computed; α range to agree |

Decide whether the Zipf share applies to all treated patients or only the branded segment, since generics hold most of the volume.

## Caveats to state with the forecast

1. **The Q0–Q20 peak understates the ceiling.** 4 of the 5 analogs are still climbing at Q20, and curves like these keep rising (median 1.44× later, `peak_window`). Year-3 progress depends on the peak-definition decision.
2. **Label expansions:** 4 of the 5 analogs carry `label_expansion_in_window`. Read the approval letters to separate new indications from new clinical data.
3. **Launch indications differ:** Rexulti and Vraylar launched with a second indication, which breaks the first-indication assumption. Drop them or show them separately.
4. **Medicaid shapes:** the most representative payer for this disease, but still Medicaid, not the whole market.
5. **Launch quarters** are the first SDUD quarter until launch dates are read (Caplyta's is a quarter after approval).

## Next steps

1. ~~**Team:** agree on this example~~ Done 2026-10-27. This settles the "pick the example drug's therapeutic area" step in the label-reads plan (PR #6).
2. **Label reads** for the 5 analogs, 4 fields each (line of therapy, dosing, # competitors, launch date), with quotes and links, `approved=false` until reviewed.
3. **Approval letters** for the analogs' efficacy supplements in Q0–Q12.
4. **Source the epi funnel** and fill `target_drug` and `market_size`.

## Fallback: migraine prevention

Kept in case the schizophrenia example runs into a blocker. An oral CGRP-class migraine preventive. 6 usable CGRP analogs (Aimovig, Ajovy, Emgality, Ubrelvy, Nurtec, Qulipta), all high volume with good fits, and a clear order of entry. Weaker on Medicaid representativeness (migraine patients are more often commercially insured), and 5 of the 7 migraine analogs carry the label-expansion flag.
