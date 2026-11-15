# EDA: peak definition, fit window and analog matching (Grace)

**Author:** Grace · **Date:** 2026-10-23, rerun 2026-11-15 · **Branch:** `eda` · **Data:** `data/processed/` as committed on `main` at `062a1d7` (Q0–Q28 peak, 2026-11-14)

Follows the write-up format in [README.md](README.md): **Question → Data → Method → Findings → What it means for the tool → Open checks**. Each notebook reproduces every number.

**Shared definitions** (as in `launch_eda`). *Usable* = the end of the `checks.md` funnel, 261 of 426 analogs. *Area* = ATC level 1, with L split into **Oncology** (L01, L02) and **Immunology** (L03, L04). Provisional quarters (the latest 2) are left out of everything. TRx = the mid estimate (suppressed rows at 5 Rx, no SDUD row = 0; decision 2026-10-30).

**ATC classes.** RxClass returned codes for every product with the ingredient, so some analogs carried a class from a combination pill or a topical form: the SGLT2 and DPP-4 inhibitors read as "combinations", Victoza and Adlyxin as insulins, Jakafi and Daliresp as dermatology, Zytiga as a PARP inhibitor. Found in this EDA and fixed in the pipeline on 2026-10-23 (`main`, decision log); the notebooks now read the corrected classes.

**Rerun on the suppression rebuild (2026-11-14).** 250 → 261 usable analogs. The peak findings hold with small shifts. The analog-matching headline softens: ATC 4 class medians are now about level with the overall median (−1%), not worse (−7%), and the SGLT2 example no longer shows the class hurting on average. `peak_window` §5 is new: it compares peak horizons and backs decision 1.

**Rerun on the Q0–Q28 peak (2026-11-15).** Decision 1 is now built (`062a1d7`), so `share_of_peak` divides by the Q0–Q28 peak and m's floor is 0.1. `peak_window` computes its own peaks, so its findings stand; with the lower floor, median p and q are identical under all three peak definitions, and Q0–Q12 fits no longer sit on a bound more often. In `analog_similarity` the headline holds: no class or area median beats the overall median, and volume band is still the only clear gain (now 20%). Two shifts: the SGLT2 class median is now worse than the overall median, and launch cohort gains 8%, most likely because recent launches' shares are upper bounds. Volume bands now use the Q0–Q20 TRx maximum explicitly, so they match `volume_vs_shape`.

## Summary

| EDA | Notebook | Question | Headline | Feeds |
|---|---|---|---|---|
| Peak definition and fit window | [peak_window_grace.ipynb](peak_window_grace.ipynb) | Does the Q0–Q20 peak understate the real peak, and which peak and fit window best describe Q0–Q12? | Curves that peak at Q20 keep rising (median 1.43× later), and it isn't COVID. The peak definition moves the share of peak at Q12 from 0.67 to 0.46 but leaves Bass p and q unchanged; the fit window is what moves p and q. Only a fixed horizon with a full window measures every launch year the same way; Q0–Q28 was chosen and is built | Decision 2026-11-14 (decisions.md); `launch_eda` decision 1; `share_of_peak`, `bass_fits` |
| Analog matching | [analog_similarity_grace.ipynb](analog_similarity_grace.ipynb) | Are same-class, area, route, volume or cohort curves more alike, and does a group median predict a held-out analog's Q0–Q12? | Same-ATC 4 pairs are a little more alike, but no group median predicts a held-out analog's first 3 years much better than the median of all analogs; class medians are level with it or worse, even for clean classes like SGLT2. Medicaid volume band is the only clear gain (20%, or 9% on Q0–Q12-normalized curves) | Similarity score in `analog_recommendations`; analog card (show the spread); `volume_vs_shape` decision 2 |

## Decisions these suggest (for the team)

1. **Keep fitting Bass on Q0–Q20, but read share of peak against the Q0–Q28 peak, for analogs with a full Q0–Q28 window** (agreed by the team and built 2026-11-14, `062a1d7`; decisions.md). The Q0–Q20 peak caps nearly half the curves at an artificial peak. A fixed horizon with a full window is the only option that measures every launch year the same way; the all-time peak ties the horizon to launch year (12 years for a 2012 launch, 5 for a 2020 one) and keeps moving with each data refresh. Analogs without 7 years of data (2019+ launches) keep their shape (p, q) and get their share against the peak so far, shown as an upper bound: "≤ X, peak not confirmed". m's floor dropped from 0.5 to 0.1 with it.
2. **Don't fit on Q0–Q12 only, even though the forecast is 3 years.** Short-window fits match the first 3 years slightly better but are unstable: q moves by more than 50% for more than half the analogs, and the curve misses Q13–Q20 badly.
3. **Don't give ATC class, area or route much weight in the similarity score as they stand.** As group medians they predict a held-out analog's first 3 years no better than the median of all analogs. Re-test once label-read features (line of therapy, competitors, dosing) are approved.
4. **Show the analogs' spread on the analog card and in step 4, not one borrowed curve.** First-3-year shapes differ by 0.24 of peak between two analogs on median.
5. **If volume becomes a similarity feature (`volume_vs_shape` decision 2), use a pre-launch proxy** such as the expected patient population, since a target drug's Medicaid volume isn't known before launch.

---

## 1. Peak definition and fit window

**Notebook:** [peak_window_grace.ipynb](peak_window_grace.ipynb)

**Question.** `share_of_peak` divides by the highest TRx in Q0–Q20. Does that understate where launches go? Since the forecast covers 3 years (Q0–Q12), which peak and which Bass fit window best describe that window? And which peak horizon should replace Q0–Q20?

**Data.** `sdud_quarterly.csv` (every quarter through 2026Q1, not only Q0–Q20), `analog_features.csv` (launch quarter, usable funnel), `indication_history.csv` (possible label expansions), the pipeline's `pipeline.bass` fit.

**Method.**
- Followed each usable analog past Q20 using every complete quarter. Compared the all-time peak and the Q0–Q28 peak with the Q0–Q20 peak (208 analogs with quarters after Q20).
- Split the post-Q20 rise by whether Q21–Q28 ends before COVID continuous coverage (2020Q2), and by whether a possible label expansion came after Q20.
- On the 154 analogs with ≥ 28 complete quarters: Q0–Q20 curves divided by three peaks (Q0–Q20, Q0–Q28, all-time); Bass refitted on Q0–Q20 for each.
- Bass fitted on Q0–Q12, Q0–Q20 and Q0–Q28 (share of the Q0–Q28 peak); errors as RMSE in share-of-peak units on Q0–Q12 and Q13–Q20.
- Peak horizons (§5): fixed horizons with a full window (Q0–Q20, Q0–Q24, Q0–Q28), Q0–Q28 capped at the data each analog has, and all available data with a minimum of 13, 21 or 29 quarters. For each, the analogs covered, the share still peaking in the window's last quarter, the median share of peak at Q12, and its Spearman correlation with quarters of data (near 0 = the same measure for every launch year).

**Findings.**
- **89 of 208 analogs peak at Q20, and 96% of those go more than 5% higher later:** median 1.43× the Q0–Q20 peak (quartiles 1.18–2.04). Curves that peak before Q20 mostly stay there (median 1.00).
- **Not COVID:** the Q20→Q28 rise is 1.30× when Q21–Q28 ends before COVID coverage (n = 17) and 1.35× when it overlaps it (n = 50). It is larger with a possible label expansion after Q20 (1.39× vs 1.23×), but above 1 without one.
- **Share of peak at Q12** (median): 0.67 with the Q0–Q20 peak, 0.56 with the Q0–Q28 peak, 0.46 with the all-time peak. By area under the all-time peak it ranges from 0.35 (alimentary & metabolism, cardiovascular) to 0.56 (blood).
- **The peak definition doesn't change the Bass shape.** With m's floor at 0.1, q is unchanged for 90% of analogs and median p, q and R² are identical under all three peaks. At the old 0.5 floor, q moved for more analogs because m was capped (5 fits under the Q0–Q20 peak, 29 under the all-time peak). m at the 5.0 cap stays at 18–19.
- **The fit window does change it.**

  | Fit window | median q | on a bound | RMSE Q0–Q12 | RMSE Q13–Q20 |
  |---|---|---|---|---|
  | Q0–Q12 | 0.30 | 20% | 0.027 | 0.158 |
  | Q0–Q20 | 0.19 | 22% | 0.042 | 0.043 |
  | Q0–Q28 | 0.18 | 23% | 0.048 | 0.055 |

  q moves by more than 50% between the Q0–Q12 and Q0–Q20 fits for 54% of analogs. At the old 0.5 floor, 40% of Q0–Q12 fits sat on a bound (vs 25%); with the 0.1 floor that difference is gone.
- **Peak horizons (§5):**

  | Peak over | Analogs | Latest launch | Peak in window's last quarter | Median share at Q12 | ρ with quarters of data |
  |---|---|---|---|---|---|
  | Q0–Q20 (old rule) | 256 | 2022 | 47% | 0.68 | −0.11 |
  | Q0–Q20, full window only | 213 | 2020 | 42% | 0.67 | 0.03 |
  | Q0–Q24, full window only | 183 | 2019 | 40% | 0.59 | 0.06 |
  | **Q0–Q28, full window only** | **154** | **2018** | **33%** | **0.56** | **−0.02** |
  | Q0–Q28, or as far as the data goes | 256 | 2022 | 41% | 0.60 | −0.23 |
  | All data, ≥ 13 quarters | 256 | 2022 | 38% | 0.56 | −0.35 |
  | All data, ≥ 21 quarters | 213 | 2020 | 31% | 0.52 | −0.24 |
  | All data, ≥ 29 quarters | 154 | 2018 | 28% | 0.46 | −0.17 |

  - A full window removes the launch-year bias at any length (ρ ≈ 0); mixing horizons brings it back, most of all with all data.
  - The all-data peak keeps moving: two more years of data raised it by more than 5% for 27% of the analogs with a full Q0–Q28 window.
  - Q0–Q28 leaves the fewest curves still rising at the window's end among the fixed horizons, at the cost of 2019+ launches. On the analogs with a full Q0–Q28 window, the Q0–Q24 peak is 1.07× the Q0–Q20 peak and the Q0–Q28 peak 1.17× (medians).
- **Example drug analogs** (Torevia) under the rule as built: Latuda 0.37, Rexulti 0.59, Vraylar 0.19 share of peak at Q12 (confirmed, full Q0–Q28 window); Caplyta ≤ 0.54 and Lybalvi ≤ 0.80 (peak not confirmed).

**What it means for the tool.** p and q describe the shape; the peak definition decides how that shape maps to the ceiling. Reading "share of peak at year 3" against the Q0–Q20 peak overstates progress towards the ceiling (two-thirds vs a little over half against the Q0–Q28 peak). The fit window should stay long enough to see the bend (Q0–Q20); the 3-year horizon is where the forecast is read, not where Bass is fitted. A recent analog's share against its peak so far is an upper bound, so it stays in as "≤ X" rather than being dropped.

**Open checks.**
- Even with every quarter of data, 28–38% of analogs are still at their highest: some drugs haven't peaked yet, and no window fixes that, so the flag matters.
- An analog that has clearly turned down (peak several quarters back and falling) could be shown as "≈ X, peak likely reached" rather than "≤ X"; not tested.
- The all-time peak includes later indications and late-life growth (e.g. Vraylar's later indications), so it's an upper reference, not a usable denominator. A rule like "peak before the first confirmed expansion" needs the approval-letter read.
- 154 of 261 usable analogs have ≥ 28 quarters up to their last SDUD row. The pipeline counts quarters with no row as 0 TRx, which adds 10 discontinued drugs (e.g. the first-wave HCV orals), so 164 have `peak_confirmed`. The confirmed-peak set is 2010–2018 launches and grows forward by about one launch year a year.

---

## 2. Analog matching

**Notebook:** [analog_similarity_grace.ipynb](analog_similarity_grace.ipynb)

**Question.** The tool picks analogs by similarity on structured features, then borrows their shape. Are curves in the same ATC 4 or ATC 3 class, area, route, Medicaid volume band or launch cohort more alike than random pairs? Does a group's median curve predict a held-out analog's first 3 years?

**Data.** `launch_curves.csv` (share of peak, Q0–Q12, non-provisional), `analog_features.csv` (classes, area, route), `analogs.csv` (approval year). 261 usable analogs. Share of peak is against the Q0–Q28 peak, an upper bound for the 97 without the full window. Volume bands as in `volume_vs_shape`, on the highest TRx in Q0–Q20 (small ≤ 766 a quarter, mid ≤ 14,748, large).

**Method.**
- Distance between two analogs = mean absolute gap in share of peak over the quarters both have (Q0–Q12).
- For each grouping: mean same-group distance ÷ all-pairs distance, with a 1,000-shuffle permutation test.
- Holdout: leave one analog out, predict its Q0–Q12 with the median curve of the rest of its group (≥ 3 members), and compare with the median of all other analogs on the same analogs.
- Repeated with curves normalized to each analog's own Q0–Q12 peak, so the result doesn't depend on §1's peak question.

**Findings.**
- Two analogs' first-3-year curves sit **0.24 of peak apart** on median (quartiles 0.14–0.37).
- **Pairs more alike than random:**
  - Same ATC 4 class: 0.91 of the average distance (p = 0.012).
  - Same volume band: 0.95 (p = 0.001).
  - Same launch cohort: 0.97 (p = 0.001).
  - Same ATC 3 class, area or route: 0.99–1.02, not significant.
- **Holdout** (median error reduction vs the overall median curve, whose error is 0.18 of peak):

  | Grouping | Analogs | Share of Q0–Q28 peak | Share of own Q0–Q12 peak |
  |---|---|---|---|
  | Volume band | 261 | **+20%** (56% of analogs better) | +9% (58%) |
  | ATC 3 × volume | 152 | +13% | +7% |
  | Launch cohort | 261 | +8% | 0% |
  | Route | 261 | +2% | +5% |
  | Area × volume | 237 | +1% | 0% |
  | ATC 4 class | 105 | **0%** | +5% |
  | Area | 254 | −4% | −3% |
  | ATC 3 class | 195 | −5% | −1% |

- **Why ATC 4 doesn't help despite closer pairs:** most ATC 4 groups have 3–5 usable members, so their median is noisy, while the overall median is smoothed over 260 curves. Only 105 analogs have ≥ 3 classmates.
- **Launch cohort's gain is most likely the upper bound:** it disappears on own-Q12 shares (0%). Recent launches' shares are against the peak so far, so their cohort median runs higher; it isn't evidence that launch year predicts shape.
- **A clean class doesn't help on average:** the four SGLT2 inhibitors are predicted worse by their class median than by the overall median (mean error 0.219 vs 0.187). It helps Farxiga and Jardiance and hurts Invokana and Steglatro: same mechanism, different launches, plausibly because of order of entry.
- **Volume helps within most areas:** oncology 31%, immunology 23%, alimentary & metabolism 21%; not anti-infectives (−6%) or nervous system (−11%), the example drug's area. Part of its effect is §1's peak artifact (small drugs plateau earlier), part is the faster start found in `volume_vs_shape`. ATC 4 by area swings from −14% (nervous system) to +29% (anti-infectives, 15 analogs), too noisy to read.

**What it means for the tool.** First-3-year shapes are mostly drug-specific: class, area and route don't pick analogs that predict a held-out drug's early curve, at least as group medians. The analog step should show the spread of the chosen analogs, and the matching that matters has to come from the agent's re-rank on line of therapy, competition and dosing, which can't be tested until label reads are approved. Volume is the strongest structured signal but isn't known for a target drug before launch.

**Open checks.**
- Nearest-neighbour matching on several features at once, instead of one group's median.
- The same tests on Bass p and q instead of shares.
- Re-run with label-read features once approved, and once clinic-administered sc drugs are flagged.
- Re-run on confirmed-peak analogs only, to separate the cohort gain from the upper bounds.

---

## Reproduce

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/jupyter nbconvert --to notebook --execute --inplace eda/peak_window_grace.ipynb
.venv/bin/jupyter nbconvert --to notebook --execute --inplace eda/analog_similarity_grace.ipynb
```

The notebooks only read `data/processed/` (and import `pipeline.common` and `pipeline.bass`). The permutation test uses a fixed seed (2026). If the data is rebuilt, re-run them and update the numbers here.
