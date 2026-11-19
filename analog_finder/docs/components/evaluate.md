# evaluate (step 8)
Purpose: test whether the finder predicts a launch better than a "typical drug" guess. Hold out one analog, let the finder pick its 5 analogs, and compare the weighted curve with what the held-out drug actually did in Q0–Q12 ([Evaluation](../../../docs/implementation_plan.md#evaluation)).

Input: `io.load_tables()` (loaded once) and `io.load_config()`. `use_evidence` stays off, so every analog is matched on the same features (decisions.md 2026-11-18).

Output: `python -m analog_finder.evaluate` prints one row per method and baseline. `--out <csv>` writes the per-analog errors (default `data/cache/evaluation/errors.csv`, gitignored); `--analogs <id> ...` runs a subset.

Depends on: steps 1–7. Reuses `filters.candidates(..., holdout=)`, `embed.embed`, `score.score`, `loop.CandidateQueue(...).auto_confirm()`, `curve.weights`, `curve.uptake_curve`; no finder code changes.

**How to read the result.** The error is how far a prediction misses, in share of peak, averaged over Q0–Q12 (0.18 = misses by 18 points of peak). Lower is better. The baselines are guesses that use no matching; the finder is worth using only if its error is below theirs.

Decisions made:
- **Held out:** the usable analogs with all of Q0–Q12: 258 of 261.
- **Each run:** build a target from the held-out analog → filters (its route group) → embed → score → auto-confirm the top 5 (no rejections) → weighted curve → error.
- **Target from an analog:** its indication text, ATC codes (first ATC 4 if it has several), route group and dosage form; no evidence. Gaps come from the data, not the method: 6 analogs have no ATC class (text only), 7 have several (as a candidate any can match), 15 have no dosage form. Built as a `Target` directly, since the scenario check requires an ATC 4 code.
- **Methods:**
  - **TF-IDF hybrid:** the `scoring.yaml` weights (text plus ATC 4, ATC 3, area).
  - **Structured only:** text weight 0, so ATC class alone. Within a class, candidates tie and `analog_id` breaks the tie, so its top 5 there is arbitrary.
- **Baselines**, both from the other usable analogs **in the same route group** (the pool the finder picks from; mixing routes would credit the finder for oral and sc drugs ramping differently):
  - **All-analog median:** every new drug launches like the typical drug.
  - **ATC 4 median:** like the typical drug in its class (at least 3 others in the class; otherwise the all-analog median, with the count reported).
- **Measuring-tool check:** the all-analog baseline should come out near the EDA's 0.18. If it doesn't, the code has a bug. It gives 0.169 same-route (0.174 mixing routes, as the EDA did). A unit test pins the error formula to the EDA's.
- **Summary across analogs:** the median error (the EDA's measure) and the mean.
- **Spread:** 95% bootstrap intervals (2,000 resamples, fixed seed) for each median error and for each method's gap to the all-analog baseline, plus the share of analogs where the method beats that baseline.
- **Unconfirmed peaks:** included, as in the EDA; a second set of rows covers only the ~164 analogs with a confirmed peak.
- **Weights don't change in step 8.** It's a first measurement. A later evaluation (steps 9, 15) changes the defaults only if the median error improves by ≥ 0.01 and the 95% interval of the difference excludes 0 (set now, before any results).
- **Speed:** one embedding per held-out analog, shared by both methods; a few minutes for all 258.

Open questions: none.

Caveats for the write-up: matching is on text and class only (no label reads yet), so this understates the hybrid score (step 15). Medicaid (SDUD) only.

Done when: `python -m analog_finder.evaluate` prints TF-IDF and structured-only errors next to both baselines; the all-analog baseline comes out near 0.18.
