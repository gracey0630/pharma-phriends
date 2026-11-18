# curve (step 7)
Purpose: turn the confirmed analogs into one similarity-weighted uptake curve with a band (D5), shown with the analogs' Bass fits and the standard caveats.

Input: the confirmed analogs (step 6) and their scores (step 5), `launch_curves`, `bass_fits`, the candidate table (for `peak_not_confirmed`), optional `weight_overrides` in the scenario YAML.

Output ([Shared contracts](../../../docs/implementation_plan.md#shared-contracts); written to `data/scenarios/<scenario>/`):
- `curve.weights(...)` → `analog_weights.csv`: `analog_id`, `similarity`, `weight` (sums to 1), `override_weight`, `override_reason`
- `curve.uptake_curve(...)` → `uptake_curve.csv`: `quarter` (0–20), `weighted_share_of_peak`, `band_min`, `band_max`, `n_analogs`, `n_upper_bound` (added: analogs that quarter whose peak isn't confirmed)
- `curve.bass_table(...)` → printed next to the curve: weight, p, q, m, R², weak-fit and low-volume flags
- CLI: the full run (`python -m analog_finder.finder --scenario torevia`) writes all three outputs and prints weights, the curve at Q0/2/4/8/12/16/20, the Bass table and `curve.CAVEATS`.

Depends on: steps 1–6.

Decisions made:
- **Weights** = similarity of each confirmed analog ÷ the sum over the confirmed analogs.
- **Overrides:** `weight_overrides: {analog_id: {weight: 0–1, reason: text}}` in the scenario YAML. A reason is required. The other analogs share what's left (1 − overrides) in proportion to their similarity, so the total stays 1. Overrides may total at most 1, and exactly 1 if every analog is overridden. An override for an analog that isn't confirmed is ignored with a warning, since the confirmed set changes between runs (e.g. a holdout).
- **Short curves:** each quarter averages only the analogs with a non-provisional value that quarter, their weights renormalized among them; `n_analogs` records how many. A recent launch (Lybalvi: 18 quarters, the last 2 provisional) simply stops contributing.
- **Band** = plain min–max of the analogs with data that quarter, as agreed, even when one analog has a small weight: the band shows the spread of history, not a confidence interval.
- **Upper bounds:** `n_upper_bound` counts the analogs whose share of peak is "≤ X" (peak not confirmed). The CLI prints the weighted value as "≤" whenever it's > 0.
- **Bass:** shown per analog, not combined. Averaging p and q is a separate question (and Bass is fitted to TRx share of peak, not adopters); the weighted curve is the trajectory input.
- **Demo outputs** in `data/scenarios/torevia/` come from a forecaster-style session (`--decided-by demo`): confirm Rexulti and Vraylar, reject Nuplazid (Parkinson's disease psychosis, not schizophrenia), confirm Caplyta, Latuda and Lybalvi (offered as #6). Weights: Rexulti 0.245, Vraylar 0.229, Caplyta 0.211, Latuda 0.167, Lybalvi 0.148. Year 3 (Q12): ≤ 0.48 of peak, band 0.19–0.80, 2 of 5 analogs with the peak not confirmed.

Open questions:
- Should the curve also be drawn from the weighted Bass parameters, and how (average p and q, or fit to the weighted curve)? Decides: team (step 14 shows the curve).

Done when: the full CLI writes all three outputs to `data/scenarios/torevia/`; weights sum to 1; tests cover overrides and short curves. ✅ (`tests/test_curve.py`; final checks 2 and 3 pass)
