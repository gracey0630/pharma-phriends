# EDA: peak definition, fit window and analog matching (Grace)

**Author:** Grace · **Date:** 2026-10-23 · **Branch:** `eda` · **Data:** `data/processed/` as committed on `main` at `2dec2a2` (built 2026-10-22; no rebuild needed)

Follows the write-up format in [README.md](README.md): **Question → Data → Method → Findings → What it means for the tool → Open checks**. Each notebook reproduces every number.

**Shared definitions** (as in `launch_eda`). *Usable* = the end of the `checks.md` funnel, 250 of 426 analogs. *Area* = ATC level 1, with L split into **Oncology** (L01, L02) and **Immunology** (L03, L04). Provisional quarters (the latest 2) are left out of everything.

**ATC classes corrected for 11 analogs.** RxClass returns codes for every product with the ingredient, so 25 analogs have several ATC codes, and the EDAs use the first. For 11 usable analogs the first code comes from a combination pill or another route: the SGLT2 inhibitors (Farxiga, Jardiance, Invokana, Steglatro) and DPP-4 inhibitors (Tradjenta, Nesina) read as "combinations", the GLP-1s Victoza and Adlyxin as insulins, Jakafi and Daliresp as dermatology (so their *area* is Dermatology in every EDA), and Zytiga as a PARP inhibitor. Both notebooks set these 11 to their own class; the pipeline should do the same (see decision 6).

## Summary

| EDA | Notebook | Question | Headline | Feeds |
|---|---|---|---|---|
| Peak definition and fit window | [peak_window_grace.ipynb](peak_window_grace.ipynb) | Does the Q0–Q20 peak understate the real peak, and which peak and fit window best describe Q0–Q12? | Curves that peak at Q20 keep rising (median 1.44× later), and it isn't COVID. The peak definition moves the share of peak at Q12 from 0.66 to 0.46 but leaves Bass p and q unchanged; the fit window is what moves p and q | Open question on the Q0–Q20 peak (decisions.md); `launch_eda` decision 1; `share_of_peak`, `bass_fits` |
| Analog matching | [analog_similarity_grace.ipynb](analog_similarity_grace.ipynb) | Are same-class, area, route, volume or cohort curves more alike, and does a group median predict a held-out analog's Q0–Q12? | Same-ATC 4 pairs are a little more alike, but no group median predicts a held-out analog's first 3 years much better than the median of all analogs; class medians make it worse, even for clean classes like SGLT2. Medicaid volume band is the only clear gain (14%, or 8% on Q0–Q12-normalized curves) | Similarity score in `analog_recommendations`; analog card (show the spread); `volume_vs_shape` decision 2 |

## Decisions these suggest (for the team)

1. **Keep fitting Bass on Q0–Q20, but stop using the Q0–Q20 peak as the ceiling.** It caps nearly half the curves at an artificial peak. When uptake at Q12 is read as a share of peak, use the peak over a **fixed horizon** longer than the fit window (e.g. Q0–Q28, complete quarters), **not the all-time peak**: the all-time peak depends on how long each drug has been on the market, so it means a 12-year peak for a 2012 launch and a 6-year peak for a 2019 launch, and it's still rising for drugs at their highest today. Lower m's 0.5 floor if `bass_fits` is renormalized. This answers the open question in decisions.md differently from `launch_eda` decision 1, which tested only whether the Q20 climb is COVID.
2. **Don't fit on Q0–Q12 only, even though the forecast is 3 years.** Short-window fits match the first 3 years slightly better but are unstable: 41% sit on a bound and q moves by more than 50% for half the analogs.
3. **Don't give ATC class, area or route much weight in the similarity score as they stand.** As group medians they don't predict a held-out analog's first 3 years; ATC 4 makes it worse. Re-test once label-read features (line of therapy, competitors, dosing) are approved.
4. **Show the analogs' spread on the analog card and in step 4, not one borrowed curve.** First-3-year shapes differ by 0.22 of peak between two analogs on median.
5. **If volume becomes a similarity feature (`volume_vs_shape` decision 2), use a pre-launch proxy** such as the expected patient population, since a target drug's Medicaid volume isn't known before launch.
6. **Fix multi-code ATC classes in the pipeline** (`class_narrow`, `class_broad`): keep the analog's own class, not codes from combination products or other routes. Until then, every EDA's class and area columns are wrong for the 11 analogs above, including Jakafi and Daliresp counted as Dermatology.

---

## 1. Peak definition and fit window

**Notebook:** [peak_window_grace.ipynb](peak_window_grace.ipynb)

**Question.** `share_of_peak` divides by the highest TRx in Q0–Q20. Does that understate where launches go? And since the forecast covers 3 years (Q0–Q12), which peak and which Bass fit window best describe that window?

**Data.** `sdud_quarterly.csv` (every quarter through 2026Q1, not only Q0–Q20), `analog_features.csv` (launch quarter, usable funnel), `indication_history.csv` (possible label expansions), the pipeline's `pipeline.bass` fit.

**Method.**
- Followed each usable analog past Q20 using every complete quarter. Compared the all-time peak and the Q0–Q28 peak with the Q0–Q20 peak (203 analogs with quarters after Q20).
- Split the post-Q20 rise by whether Q21–Q28 ends before COVID continuous coverage (2020Q2), and by whether a possible label expansion came after Q20.
- On the 154 analogs with ≥ 28 complete quarters: Q0–Q20 curves divided by three peaks (Q0–Q20, Q0–Q28, all-time); Bass refitted on Q0–Q20 for each.
- Bass fitted on Q0–Q12, Q0–Q20 and Q0–Q28 (share of the Q0–Q28 peak); errors as RMSE in share-of-peak units on Q0–Q12 and Q13–Q20.

**Findings.**
- **87 of 203 analogs peak at Q20, and 95% of those go more than 5% higher later:** median 1.44× the Q0–Q20 peak (quartiles 1.18–2.07). Curves that peak before Q20 mostly stay there (median 1.00).
- **Not COVID:** the Q20→Q28 rise is 1.33× when Q21–Q28 ends before COVID coverage (n = 18) and 1.35× when it overlaps it (n = 50). It is larger with a possible label expansion after Q20 (1.39× vs 1.23×), but above 1 without one.
- **Share of peak at Q12** (median): 0.66 with the Q0–Q20 peak, 0.55 with the Q0–Q28 peak, 0.46 with the all-time peak. By area under the all-time peak it ranges from 0.33 (alimentary & metabolism) to 0.56 (blood).
- **The peak definition doesn't change the Bass shape.** q is unchanged for 78% of analogs; the rest move because m hits its 0.5 floor (5 fits under the Q0–Q20 peak, 29 under the all-time peak). m at the 5.0 cap stays at 19–20.
- **The fit window does change it.**

  | Fit window | median q | on a bound | RMSE Q0–Q12 | RMSE Q13–Q20 |
  |---|---|---|---|---|
  | Q0–Q12 | 0.26 | 41% | 0.029 | 0.146 |
  | Q0–Q20 | 0.19 | 25% | 0.042 | 0.043 |
  | Q0–Q28 | 0.18 | 24% | 0.049 | 0.053 |

  q moves by more than 50% between the Q0–Q12 and Q0–Q20 fits for 53% of analogs.

**What it means for the tool.** p and q describe the shape; the peak definition decides how that shape maps to the ceiling. Reading "share of peak at year 3" against the Q0–Q20 peak overstates progress towards the ceiling (two-thirds vs about half). The fit window should stay long enough to see the bend (Q0–Q20); the 3-year horizon is where the forecast is read, not where Bass is fitted.

**Open checks.**
- The all-time peak includes later indications and late-life growth, and its horizon differs by launch year, so it's an upper reference, not a usable denominator. A rule like "peak before the first confirmed expansion" needs the approval-letter read.
- 154 of 250 usable analogs have ≥ 28 quarters; the comparison leans towards older launches.

---

## 2. Analog matching

**Notebook:** [analog_similarity_grace.ipynb](analog_similarity_grace.ipynb)

**Question.** The tool picks analogs by similarity on structured features, then borrows their shape. Are curves in the same ATC 4 or ATC 3 class, area, route, Medicaid volume band or launch cohort more alike than random pairs? Does a group's median curve predict a held-out analog's first 3 years?

**Data.** `launch_curves.csv` (share of peak, Q0–Q12, non-provisional), `analog_features.csv` (classes, area, route, `peak_trx`), `analogs.csv` (approval year). 250 usable analogs. Volume bands as in `volume_vs_shape` (small ≤ 766 peak TRx a quarter, mid ≤ 14,748, large).

**Method.**
- Distance between two analogs = mean absolute gap in share of peak over the quarters both have (Q0–Q12).
- For each grouping: mean same-group distance ÷ all-pairs distance, with a 1,000-shuffle permutation test.
- Holdout: leave one analog out, predict its Q0–Q12 with the median curve of the rest of its group (≥ 3 members), and compare with the median of all other analogs on the same analogs.
- Repeated with curves normalized to each analog's own Q0–Q12 peak, so the result doesn't depend on §1's peak question.

**Findings.**
- Two analogs' first-3-year curves sit **0.22 of peak apart** on median (quartiles 0.13–0.34).
- **Pairs more alike than random:**
  - Same ATC 4 class: 0.90 of the average distance (p = 0.009).
  - Same volume band: 0.95 (p = 0.001).
  - Same ATC 3 class, area, route or launch cohort: 0.98–1.01, not significant.
- **Holdout** (median error reduction vs the overall median curve, whose error is 0.15 of peak):

  | Grouping | Analogs | Share of Q0–Q20 peak | Share of own Q0–Q12 peak |
  |---|---|---|---|
  | Volume band | 250 | **+14%** (60% of analogs better) | +8% (55%) |
  | ATC 3 × volume | 143 | +8% | +6% |
  | Route | 250 | +2% | +4% |
  | Launch cohort | 250 | +2% | −1% |
  | Area × volume | 227 | +2% | −3% |
  | Area | 243 | −4% | −1% |
  | ATC 3 class | 187 | −7% | −5% |
  | ATC 4 class | 95 | **−7%** | −6% |

- **Why ATC 4 fails despite closer pairs:** most ATC 4 groups have 3–5 usable members, so their median is noisy, while the overall median is smoothed over 249 curves. Only 95 analogs have ≥ 3 classmates.
- **Even a clean class doesn't help:** the four SGLT2 inhibitors are predicted worse by their class median than by the overall median (error 0.125 vs 0.097). Same mechanism, different launches, plausibly because of order of entry.
- **Volume helps within most areas:** oncology 22%, immunology 21%, alimentary & metabolism 25%, nervous system 5%. Part of its effect is §1's peak artifact (small drugs plateau before Q20), part is the faster start found in `volume_vs_shape`.

**What it means for the tool.** First-3-year shapes are mostly drug-specific: class, area and route don't pick analogs that predict a held-out drug's early curve, at least as group medians. The analog step should show the spread of the chosen analogs, and the matching that matters has to come from the agent's re-rank on line of therapy, competition and dosing, which can't be tested until label reads are approved. Volume is the strongest structured signal but isn't known for a target drug before launch.

**Open checks.**
- Nearest-neighbour matching on several features at once, instead of one group's median.
- The same tests on Bass p and q instead of shares.
- Re-run with label-read features once approved, and once clinic-administered sc drugs are flagged.

---

## Reproduce

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/jupyter nbconvert --to notebook --execute --inplace eda/peak_window_grace.ipynb
.venv/bin/jupyter nbconvert --to notebook --execute --inplace eda/analog_similarity_grace.ipynb
```

The notebooks only read `data/processed/` (and import `pipeline.common` and `pipeline.bass`). The permutation test uses a fixed seed (2026). If the data is rebuilt, re-run them and update the numbers here.
