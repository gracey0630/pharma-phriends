# evaluate (steps 8 and 9)
Purpose: test whether the finder predicts a launch better than a "typical drug" guess. Hold out one analog, let the finder pick its 5 analogs, and compare the weighted curve with what the held-out drug actually did in Q0–Q12 ([Evaluation](../../../docs/implementation_plan.md#evaluation)).

Input: `io.load_tables()` (loaded once) and `io.load_config()`. `use_evidence` stays off, so every analog is matched on the same features (decisions.md 2026-11-18).

Output: `python -m analog_finder.evaluate [--embedders tfidf rxbert]` prints one row per method and baseline, and with two embedders the paired comparison of the second against the config default. `--out <csv>` writes the per-analog errors (default `data/cache/evaluation/errors.csv`, gitignored); `--analogs <id> ...` runs a subset.

Depends on: steps 1–7. Reuses `filters.candidates(..., holdout=)`, `embed.embed`, `score.score`, `loop.CandidateQueue(...).auto_confirm()`, `curve.weights`, `curve.uptake_curve`; no finder code changes.

**How to read the result.** The error is how far a prediction misses, in share of peak, averaged over Q0–Q12 (0.18 = misses by 18 points of peak). Lower is better. The baselines are guesses that use no matching; the finder is worth using only if its error is below theirs.

Decisions made:
- **Held out:** the usable analogs with all of Q0–Q12: 258 of 261.
- **Each run:** build a target from the held-out analog → filters (its route group) → embed → score → auto-confirm the top 5 (no rejections) → weighted curve → error.
- **Target from an analog:** its indication text, ATC codes (first ATC 4 if it has several), route group and dosage form; no evidence. Gaps come from the data, not the method: 6 analogs have no ATC class (text only), 7 have several (as a candidate any can match), 15 have no dosage form. Built as a `Target` directly, since the scenario check requires an ATC 4 code.
- **Methods:**
  - **TF-IDF hybrid:** the `scoring.yaml` weights (text plus ATC 4, ATC 3, area).
  - **RxBERT hybrid (step 9):** the same weights with RxBERT (centered) as the text embedder. `--embedders tfidf rxbert` runs both on the same held-out analogs; RxBERT vectors come from the embedding cache, so each text is encoded once.
  - **Structured only:** text weight 0, so ATC class alone. Within a class, candidates tie and `analog_id` breaks the tie, so its top 5 there is arbitrary. A held-out analog with no ATC class (6) has nothing to rank on, so it gets the all-analog median, counted as a fallback.
- **Baselines**, both from the other usable analogs **in the same route group** (the pool the finder picks from; mixing routes would credit the finder for oral and sc drugs ramping differently):
  - **All-analog median:** every new drug launches like the typical drug.
  - **ATC 4 median:** like the typical drug in its class (at least 3 others in the class; otherwise the all-analog median, with the count reported).
- **Measuring-tool check:** the all-analog baseline should come out near the EDA's 0.18. If it doesn't, the code has a bug. It gives 0.169 same-route (0.174 mixing routes, as the EDA did). A unit test pins the error formula to the EDA's.
- **Summary across analogs:** the median error (the EDA's measure) and the mean.
- **Spread:** 95% bootstrap intervals (2,000 resamples, fixed seed) for each median error and for each method's gap to the all-analog baseline, plus the share of analogs where the method beats that baseline.
- **Unconfirmed peaks:** included, as in the EDA; a second set of rows covers only the ~164 analogs with a confirmed peak.
- **Weights don't change in step 8.** It's a first measurement. A later evaluation (steps 9, 15) changes the defaults only if the median error improves by ≥ 0.01 and the 95% interval of the difference excludes 0 (set now, before any results).
- **Default embedder (step 9):** RxBERT replaces TF-IDF as `scoring.yaml`'s `embedder` only if the paired comparison (RxBERT hybrid − TF-IDF hybrid, per analog) meets that margin. The CLI prints the comparison and whether it does. Otherwise TF-IDF stays: no download or torch needed for the demo.
- **Speed:** one embedding per held-out analog, shared by both methods; about 20 seconds for all 258.

Result (2026-11-18, TF-IDF, `use_evidence` off, provisional weights), median error over 258 analogs:

| method | error (95% interval) | vs all-analog median (95% interval) | beats it on |
|---|---|---|---|
| TF-IDF hybrid | 0.173 (0.155–0.195) | +0.004 (−0.010 to +0.020) | 48% |
| RxBERT hybrid (step 9) | 0.177 (0.157–0.187) | −0.007 (−0.016 to +0.009) | 52% |
| Structured only | 0.181 (0.166–0.196) | +0.004 (−0.002 to +0.013) | 47% (6 fallbacks) |
| ATC 4 median | 0.174 (0.157–0.189) | 0.000 | 172 fallbacks |
| All-analog median | 0.169 (0.153–0.189) | — | — |

The measuring-tool check passes (0.169). Nothing beats the typical-drug guess: the finder picks sensible analogs (Latuda → the other antipsychotics, Skyrizi → the other IL-17/23 psoriasis biologics), but text and class don't separate fast launches from slow ones. Same conclusion on the 164 analogs with a confirmed peak (TF-IDF hybrid 0.192, RxBERT hybrid 0.183, all-analog 0.190). Weights unchanged, as agreed.

Step 9, RxBERT vs TF-IDF (paired, per analog): median difference −0.002 (95% interval −0.007 to +0.001), RxBERT better on 54%. It doesn't meet the margin, so **TF-IDF stays the default embedder**. A better text model barely moves the error, as expected if text and class can't explain launch speed. Line of therapy, competition and dosing (step 15) are what's left to test.

Open questions: none.

Caveats for the write-up: matching is on text and class only (no label reads yet), so this understates the hybrid score (step 15). Medicaid (SDUD) only.

Done when: `python -m analog_finder.evaluate` prints TF-IDF and structured-only errors next to both baselines; the all-analog baseline comes out near 0.18. ✅ (`tests/test_evaluate.py`; baseline 0.169). Step 9: the table includes RxBERT ✅ (`--embedders tfidf rxbert`, ~40 s with a warm cache).
