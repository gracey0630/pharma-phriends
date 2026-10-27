# EDA: launch curves, Q20 peak, Bass fits and flags (Christina)

**Author:** Christina · **Date:** 2026-10-23 · **Branch:** `eda` · **Data:** `data/processed/` as committed on `main` at `1bc6134` (built 2026-10-23, after the ATC class fix; no rebuild needed)

Follows the write-up format in [README.md](README.md): **Question → Data → Method → Findings → What it means for the tool → Open checks**. All six EDAs are sections of one notebook, [launch_eda_christina.ipynb](launch_eda_christina.ipynb), so each section below is one registry topic (`launch_eda` §1–§6) and names its notebook section.

**Shared definitions.** *Usable* = the end of the `checks.md` funnel: has a launch quarter, not `late_launch`, no generic in Q0–Q12, and `enough_data` (≥ 12 complete quarters, no blank quarter after Q2). 250 of 426 analogs. *Area* = ATC level 1, except that L (antineoplastic and immunomodulating) is split into **Oncology** (L01, L02) and **Immunology** (L03, L04), because the open scope question compares them. Provisional quarters (the latest 2) are left out of everything.

## Summary

| EDA | Notebook | Question | Headline | Feeds |
|---|---|---|---|---|
| Pool and survivorship | [launch_eda_christina.ipynb](launch_eda_christina.ipynb) §1 | What's in the usable pool, and who does it leave out? | 250 of 426 usable. Analogs dropped for blank quarters are tiny (median 442 lifetime Rx vs 34,367 usable). Oncology is the largest usable area (62) | Analog pool rule; scope question |
| Curves by area | §2 | Do launch shapes differ by area and route? | Every large area reaches 50% of peak at a median Q5–Q8. Oncology starts faster and flattens; immunology and sc start slower, then catch up | Scope question (one area or two); analog weighting |
| Q20 peak | §3 | Is the Q20 peak real, or COVID enrollment growth? | No COVID signal overall (43% peak at Q20 whether Q16–Q20 overlaps COVID or not). Immunology may be the exception (5 of 6), too few to tell | Open question: Q0–Q20 peak |
| Bass fit quality | §4 | Which Bass fits can be trusted? | 100 of 250 usable fits are weak. Oncology is worst (41 of 62 weak): cumulative Bass can't follow rise-plateau-decline | `bass_fits`; step-4 review |
| Label expansion and flags | §5 | How common are the distortion flags, and does an expansion change the curve? | Enrollment-shock flag on for 91%, expansion flag for 55%. Curves without an expansion are front-loaded (0.47 of peak at Q5 vs 0.35 with one) | Distortion flags as filters |
| Seed brands | §6 | Do the 8 seed brands' curves and fits look as expected? | Otezla, Cosentyx, Taltz, Tremfya peak at Q20. Taltz and Tremfya have m at the cap (p, q not identified). Siliq peaks at Q11 on tiny volume | Seed-brand evidence review |

## Decisions these suggest (for the team)

1. **Keep the Q0–Q20 peak for now.** Across the pool, curves whose last quarters fall in the COVID enrollment growth don't climb more at the end than others. Revisit only if the immunology check (§3) holds up.
2. **Don't use oncology Bass p and q as they are.** Two-thirds of oncology fits are weak. Either fit a curve that can decline (or Bass on new adopters), or leave weak fits out of the p, q spread shown in step 4.
3. **Don't make `enrollment_shock_in_window` a filter.** At 91% it would empty the pool. Keep it as a note on the analog card.
4. **Keep `label_expansion_in_window` as a flag until the approval-letter read.** Efficacy-supplement curves look like confirmed-expansion curves, so many supplements may be real expansions, but the flag can't tell which.
5. **If the demo covers two areas, compare them on the late curve, not on time to 50%.** Oncology and immunology reach half their peak at a similar pace; they differ in whether they're still climbing at Q20.
6. **Add partial suppression to the data limits.** In 94% of usable analogs at least one quarter has some rows suppressed, so its TRx is a small undercount.

---

## 1. Pool and survivorship

**Notebook:** [launch_eda_christina.ipynb](launch_eda_christina.ipynb) §1 (registry `launch_eda`; overlaps Gabrielle's `pool_funnel`, which adds the area × route and era breakdowns)

**Question.** What's in the usable pool, which rule removes each dropped analog, and how do the dropped analogs differ from the usable ones?

**Data.** `analog_features.csv` (rules, flags, peak TRx, area), `analogs.csv` (approval date, lifetime Medicaid Rx).

**Method.** Each analog labelled with the first rule it fails, in the `checks.md` order: no Medicaid Rx → late launch → generic in Q0–Q12 → < 12 quarters → blank quarter after Q2. Stacked by approval year; usable vs blank-quarter analogs compared on lifetime Rx, peak TRx and share oncology; counts by area.

**Findings.**
- **426 → 250 usable.** Left out: 94 with < 12 quarters (almost all approved 2023+), 43 with a blank quarter after Q2, 20 with no Medicaid Rx, 19 late launches. The generic rule removes none.
- **Blank-quarter dropouts are tiny brands:** median 442 lifetime Medicaid Rx and peak 57 TRx a quarter, vs 34,367 and 1,264 for usable analogs. 37% of them are oncology, against 25% of the usable pool.
- **Usable by area:** oncology 62 of 104, nervous system 41 of 52, alimentary & metabolism 34 of 51, immunology 28 of 51 (about half sc), anti-infectives 18 of 35. Only 6 of the 26 analogs with no ATC class are usable.
- **Partial suppression is almost universal:** 94% of usable analogs have at least one quarter with a suppressed row. That quarter's TRx is the sum of the visible rows.

**What it means for the tool.** The usable pool is in practice 2010–2022 launches that got Medicaid volume. Small and niche oncology launches are under-represented.

**Open checks.**
- How large the partial-suppression undercount is: share of each quarter's rows suppressed, and the TRx those rows could hold (at most 10 each). Related to Gabrielle's `suppression` topic.

---

## 2. Curves by area and route

**Notebook:** [launch_eda_christina.ipynb](launch_eda_christina.ipynb) §2 (registry `curves_by_area`)

**Question.** Do uptake shapes differ by therapeutic area and route? In particular, oncology vs immunology.

**Data.** `launch_curves.csv` (share of peak, Q0–Q20) for the 250 usable analogs, with area and route from `analog_features.csv`.

**Method.** Small multiples for the 8 areas with ≥ 8 usable analogs: every curve in gray, the median and interquartile band in color. Median curves for oncology vs immunology and oral vs sc. Speed to peak = first quarter a curve reaches 50% and 80% of its peak.

**Findings.**
- **Time to 50% of peak is similar everywhere:** median Q5 (anti-infectives) to Q8 (blood, cardiovascular, immunology). Time to 80% is Q11 (respiratory) to Q16.
- **Oncology vs immunology:** oncology starts faster (median 0.25 of peak at Q2 vs 0.14) and is level with immunology by Q10 (0.66 vs 0.69). At Q20 oncology's median is 0.93, because many curves peak earlier and decline; immunology's is 1.0, still climbing.
- **Oral vs sc:** sc starts slower (0.30 of peak at Q5 vs 0.44) and catches up by Q16 (0.83 vs 0.82).
- **Anti-infectives are the most spread out:** short courses and cures give rise-and-fall curves (median about 0.76 at Q20, wide band).

**What it means for the tool.** Area matters less for early speed than the prototype suggested, and more for the late curve: whether it plateaus (oncology) or keeps climbing (immunology).

**Open checks.**
- sc includes clinic-administered products (no flag yet). Re-run once `sc_clinic` is done.
- Areas with < 8 usable analogs (dermatology, hormones, musculoskeletal) aren't shown.

---

## 3. Q20 peak

**Notebook:** [launch_eda_christina.ipynb](launch_eda_christina.ipynb) §3 (registry `q20_peak`)

**Question.** Many curves peak at Q20. Is that real uptake, or Medicaid enrollment growth during COVID continuous coverage (2020Q2–2023Q1)?

**Data.** `launch_curves.csv` for the 208 usable analogs with a complete Q20; `medicaid_enrollment.csv` (enrollment and shock windows).

**Method.** Each analog grouped by where its Q20 falls: **before COVID**, **Q16–Q20 overlapping COVID**, or **after COVID**. Compared the share peaking at Q20 and the median climb from Q16 to Q20 (share of peak at Q20 − at Q16), for the pool and within the four largest areas.

**Findings.**
- **89 of 208 (43%) peak at Q20.**
- **No difference overall:** 41% peak at Q20 when Q20 is before COVID, 43% when Q16–Q20 overlaps it, 46% after. Median Q16–Q20 climb is 0.12, 0.11 and 0.12.
- **Immunology may differ:** 5 of 6 analogs overlapping COVID peak at Q20 (median climb 0.37), vs 4 of 9 before COVID (0.12). This fits Taltz and Tremfya speeding up late, but n = 6.
- Enrollment rose from about 72M (2019) to 94M (early 2023), then fell to about 74M by 2026. There's no data from Oct 2013 to May 2017, so curves can't be adjusted for the 2014 expansion.

**What it means for the tool.** The COVID enrollment growth doesn't explain the Q20 peaks in general; many curves are still climbing at five years. Keep the Q0–Q20 peak (decision 1), and say in the app that the ceiling isn't observed for curves still climbing.

**Open checks.**
- The groups are confounded by launch year (the COVID group launched 2015–2018) and area mix.
- Test the immunology result with enrollment-adjusted curves from 2017Q2 on (TRx per enrollee).

---

## 4. Bass fit quality

**Notebook:** [launch_eda_christina.ipynb](launch_eda_christina.ipynb) §4 (registry `bass_fit_quality`)

**Question.** What range of p and q does history give, and which fits can be trusted?

**Data.** `bass_fits.csv` (p, q, m, R², `weak_fit_flag`) for the 250 usable analogs, with area from `analog_features.csv`.

**Method.** Medians of p, q, m and R² by area (≥ 8 analogs); p vs q scatter for good fits; weak fits split into R² < 0.9 vs a parameter on a bound (p or q at its cap, m at 0.5 or 5.0).

**Findings.**
- **100 of 250 weak:** 77 with R² < 0.9, 23 with a parameter on a bound. 27 have m at the 5.0 cap (still climbing, so m isn't identified).
- **Oncology is the problem:** 41 of 62 weak, median R² 0.89. Immunology 9 of 28 weak (median R² 0.97), nervous system 7 of 41 (0.98), anti-infectives 11 of 18 (0.83).
- **The worst fits are rise-and-fall curves,** with R² near or below 0: Zepatier, Harvoni (HCV cures), Xofluza (flu), Caprelsa, Cotellic, Zydelig (oncology).
- **Median q** ranges from 0.12 (respiratory, 8 analogs) to 0.27 (alimentary & metabolism); respiratory has the highest median p (0.078), then oncology (0.047).
- Good fits spread widely: p from about 0.002 to 0.2 and q from 0 to 1.2, with no clean separation between areas.

**What it means for the tool.** A cumulative Bass curve fits curves that keep climbing, but not those that decline. For oncology, p and q from these fits would understate the spread (decision 2). The step-4 review should show the weak-fit flag next to every analog.

**Open checks.**
- Refit oncology with Bass on new adopters (quarterly increments) or a curve that can decline, and compare R².
- Whether fitting only to the rising part (up to the peak quarter) fixes most weak fits.

---

## 5. Label expansion and flags

**Notebook:** [launch_eda_christina.ipynb](launch_eda_christina.ipynb) §5 (registry `label_expansion`)

**Question.** How common are the distortion flags in the usable pool, and does a possible label expansion in Q0–Q12 change the curve?

**Data.** `analog_features.csv` (flags), `indication_history.csv` (approval kind and quarter since launch), `launch_curves.csv`.

**Method.** Share of usable analogs with each flag. Usable analogs grouped by their strongest expansion in Q0–Q12: **none**, **efficacy supplement only** (possible expansion) or **new indication application** (real expansion). Median share-of-peak curves compared.

**Findings.**
- **Flag rates in the usable pool:** enrollment shock in Q0–Q12 91%, label expansion 55%, peak at last quarter 48%, multi-route 6%, any suppressed quarter 94%.
- **Curves with no expansion are front-loaded:** 0.47 of peak at Q5 and 0.68 at Q10 (113 analogs), vs 0.35 and 0.59 for efficacy-supplement-only (127) and 0.31 and 0.61 for new-indication applications (10). An expansion pushes the peak later, as expected.
- **Efficacy-supplement-only curves look like real-expansion curves,** which suggests many supplements did add an indication.

**What it means for the tool.** The enrollment-shock flag doesn't separate analogs (decision 3). The expansion flag does change the curve, but until the approval letters are read it can't say which analogs had a real expansion (decision 4).

**Open checks.**
- Only 10 analogs have a new-indication application in Q0–Q12, so that curve is noisy.
- Read approval letters for a sample of efficacy supplements to estimate how many added an indication.

---

## 6. Seed brands

**Notebook:** [launch_eda_christina.ipynb](launch_eda_christina.ipynb) §6 (registry `seed_brands`)

**Question.** Do the 8 prototype brands (Otezla, Cosentyx, Taltz, Siliq, Tremfya, Skyrizi, Sotyktu, Ibrance) have the curves and fits we'd expect?

**Data.** `launch_curves.csv` (raw TRx, first possible label expansion), `bass_fits.csv`, `analog_features.csv`.

**Method.** Raw Medicaid TRx by quarter since launch per brand, with the first possible label expansion marked; fitted p, q, m, R² and peak quarter side by side.

**Findings.**
| Brand | Launch quarter | p | q | m | R² | Peak quarter | Note |
|---|---|---|---|---|---|---|---|
| Otezla | 2014Q2 | 0.029 | 0.29 | 0.91 | 0.98 | Q20 | Psoriasis approval at Q1 (first indication was psoriatic arthritis) |
| Cosentyx | 2015Q1 | 0.008 | 0.15 | 1.88 | 0.995 | Q20 | Still climbing |
| Taltz | 2016Q2 | 0.002 | 0.13 | 5.0 | 0.97 | Q20 | **Weak:** m at cap, steep climb late |
| Siliq | 2017Q3 | 0.016 | 0.68 | 0.88 | 0.93 | Q11 | Peak about 360 TRx a quarter; first two quarters suppressed |
| Tremfya | 2017Q3 | 0.003 | 0.11 | 5.0 | 0.98 | Q20 | **Weak:** m at cap, steep climb late |
| Skyrizi | 2019Q2 | 0.007 | 0.24 | 1.23 | 0.99 | Q19 | |
| Sotyktu | 2022Q4 | 0.129 | 0.24 | 1.0 | 0.97 | Q11 | Only 12 quarters; still climbing |
| Ibrance | 2015Q1 | 0.049 | 0.30 | 0.99 | 0.997 | Q19 | Plateaus from about Q12 (oncology shape) |

- Launch quarters are the first SDUD quarter. They match the unapproved label-read launch dates within a quarter (e.g. Otezla 2014-03, Ibrance 2015-02).
- **Taltz and Tremfya's p and q aren't identified from Q0–Q20:** both climb steeply in their last quarters (2020–2022, the COVID enrollment growth; see §3).

**What it means for the tool.** The psoriasis brands mostly behave as expected and fit well. Two of six can't give a p and q, and Siliq (small, launched with a REMS) is a poor analog for a mainstream biologic.

**Open checks.**
- Compare each seed brand's first SDUD quarter with its launch date once the evidence is approved (Cosentyx's date is still missing).

---

## Reproduce

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/jupyter nbconvert --to notebook --execute --inplace eda/launch_eda_christina.ipynb
```

The notebook only reads `data/processed/`. If the data is rebuilt, re-run it and update the numbers here and in its last cell.
