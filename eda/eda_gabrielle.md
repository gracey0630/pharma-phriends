# EDA: pool, Medicaid gaps and late launches (Gabrielle)

**Author:** Gabrielle · **Date:** 2026-10-23 · **Branch:** `eda` · **Data:** `data/processed/` as committed on `main` at `2dec2a2` (built 2026-10-22; no rebuild needed)

Follows the write-up format in [README.md](README.md). Each EDA below uses the same sections so it can be merged with the team's other EDA write-ups: **Question → Data → Method → Findings → What it means for the tool → Open checks**. The notebook in each heading reproduces every number (`.venv/bin/jupyter lab eda/<notebook>`).

## Summary

| EDA | Notebook | Question | Headline | Feeds |
|---|---|---|---|---|
| Pool funnel by group | [pool_funnel_gabrielle.ipynb](pool_funnel_gabrielle.ipynb) | Where do analogs leave the pool, by route, area and era? | 250 of 426 analogs usable. Almost all losses are at the enough-data rule, and two-thirds of those are approvals too recent to have 12 quarters | Analog pool rule; scope question (which areas) |
| Medicaid gaps | [suppression_gabrielle.ipynb](suppression_gabrielle.ipynb) | Where are SDUD quarters blank, and why? | Size causes the gaps, route doesn't. Blank quarters come from two causes: suppression (< 11 Rx) in small drugs, and no row once a drug stops being dispensed | Enough-data rule |
| Late launches | [late_launch_gabrielle.ipynb](late_launch_gabrielle.ipynb) | Why do 19 analogs start in Medicaid > 4 quarters after approval? | 3 routes added later, 6 delayed commercial launches, 10 slow Medicaid uptake (mostly drugs Medicaid rarely pays for) | Exclusion list; `late_launch` flag |

## Decisions these suggest (for the team)

1. **Leave out sc forms added years after the brand** (Actemra sc, Benlysta sc, Entyvio sc). They're line extensions, not first launches.
2. **Leave out drugs whose Medicaid curve isn't uptake:** Kybella (cosmetic), Scenesse (clinic implant), Impavido, Sirturo, Aemcolo (tropical disease, TB, travellers' diarrhoea).
3. **Revisit the enough-data rule.** It treats "suppressed" (1–10 Rx) and "no row" (use stopped) the same. Treating suppressed quarters as 1–10 Rx, or ending a curve at withdrawal, would keep small and fast-fading drugs that are dropped today.
4. **Say in the app that the usable pool is in practice 2010–2021 approvals**, and leans towards drugs with Medicaid volume.

---

## 1. Pool funnel by group

**Notebook:** [pool_funnel_gabrielle.ipynb](pool_funnel_gabrielle.ipynb)

**Question.** Where do analogs leave the pool, and does that differ by route, therapeutic area or approval era?

**Data.** `analog_features.csv` (rules and flags), `analogs.csv` (approval date, lifetime Medicaid Rx). Therapeutic area = ATC level 1 from RxClass.

**Method.** The same rules, in the same order, as the funnel in `checks.md`: has Medicaid data → not `late_launch` → no generic in Q0–Q12 → enough data (≥ 12 quarters, no blank quarter after Q2). Counted by group; each dropped analog labelled by where it left.

**Findings.**
- **426 → 250 usable** (oral 202 of 332, 61%; sc 48 of 94, 51%). The generic-entry rule removes none.
- **The enough-data rule does almost all the work: it drops 137.** 94 have < 12 quarters (88 of them approved 2023 or later); 43 have a blank quarter after Q2.
- **By era:** 80% usable for 2010–13, 85% for 2014–17, 73% for 2018–21, **8% for 2022–25**.
- **By area** (ATC 1, with L split into oncology and immunology, as in `launch_eda`): respiratory 80% usable, nervous system 79%, cardiovascular 68%, alimentary & metabolism 67%, oncology 60% (62 of 104), blood 58%, immunology 55% (28 of 51), anti-infectives 51%, systemic hormones 46%, dermatology 43%, no ATC class 23%. Missing ATC classes are mostly recent approvals that would drop anyway.
- **Weakest groups: sc oncology (1 of 7 usable) and sc immunology (12 of 26).** sc oncology is recent clinic-administered bispecifics (Tecvayli, Talvey, Elrexfio, Epkinly) and Lunsumio. sc immunology loses late sc versions of older drugs (Actemra, Entyvio, Benlysta) and Granix, six recent launches (e.g. Bimzelx, Omvoh) and four with no Medicaid data (e.g. Spevigo, Saphnelo).
- **Dropped analogs are small:** among 2010–2021 approvals, median lifetime Medicaid Rx is 442 for dropped vs 37,556 for usable. Dropped for blank quarters: the HCV orals (Sovaldi, Incivek, Victrelis, Olysio, Daklinza, Viekira Pak) and niche oncology / rare-disease orals (e.g. Farydak, Tepmetko, Exkivity).

**What it means for the tool.** The pool leans towards older launches that lasted and had Medicaid volume. A target drug in rare-disease oncology, or a curative short course, will find its closest analogs missing.

**Open checks.** None in the data; the bias is a design question (see decision 3).

---

## 2. Medicaid gaps (suppression)

**Notebook:** [suppression_gabrielle.ipynb](suppression_gabrielle.ipynb)

**Question.** Which launch-curve quarters are blank, and do the gaps cluster in small drugs, sc products, early quarters or particular areas?

**Data.** `launch_curves.csv` (Q0–Q20 per analog), `analog_features.csv` (route, area, peak TRx). 406 analogs, 6,966 analog-quarters.

**Method.** Each quarter labelled **has Rx** (6,077), **suppressed** (SDUD row, count hidden because < 11 Rx; 685) or **no row** (no SDUD row for any NDC; 204). Curves stop at the latest SDUD quarter, so a short curve isn't a gap. Gaps measured in the rule window (Q3–Q20) by quarter, size (peak-TRx fifths), route and area; heatmap of every analog × quarter.

**Findings.**
- **Q0 is 54% suppressed**: the launch quarter is often a partial quarter. It falls to 18% at Q1 and 10% at Q2, then stays at 5–8% from Q3 on. Ignoring Q0–Q2 is right.
- **"No row" grows over time**, from about 1% at Q3 to 6.5% at Q20: drugs that stop being dispensed (Bevyxxa, Ukoniq, Zurampic; the HCV orals once their market was cured).
- **Size is the driver.** Smallest fifth (peak 11–124 TRx a quarter): 35% have a blank quarter after Q2. Every other fifth: 8% or less. 21 analogs never have an unsuppressed, non-provisional quarter.
- **Route isn't:** oral 16% vs sc 12% with a blank, and sc is no worse than oral within each size fifth.
- **Areas differ mostly through size and short courses:** antiparasitics (80% with a blank, 5 analogs) and anti-infectives (35%) are worst; nervous system (4%) is best.

**What it means for the tool.** One rule covers two causes. In a small drug the value is 1–10, not missing; in a faded drug use really stopped. See decision 3.

**Open checks.**
- Whether some "no row" quarters are NDCs missing from `ndc_map` rather than drugs that stopped (spot-check the top no-row analogs).

---

## 3. Late launches

**Notebook:** [late_launch_gabrielle.ipynb](late_launch_gabrielle.ipynb)

**Question.** Why do the 19 `late_launch` analogs start in Medicaid > 4 quarters after the brand's first approval?

**Data.** `candidate_pool.csv` (approval date, earliest NDC start marketing date), `indication_history.csv` (ORIG approval of the route group's own application), `analog_features.csv` (launch quarter = first SDUD quarter), `ndc_map.csv` (NDCs by listing source).

**Method.** All dates in quarters after the brand's first approval. Classified in order:
1. **Route added later**: the route group's own application was approved > 4 quarters after the brand.
2. **Commercial launch delayed**: otherwise, start marketing > 4 quarters after approval.
3. **Medicaid uptake slow**: marketed on time, first Medicaid fill > 4 quarters later.

**Findings.**
| Reason | Analogs | Notes |
|---|---|---|
| Route added later (3) | Actemra sc, Benlysta sc, Entyvio sc | sc applications 4–9 years after the IV brand |
| Commercial launch delayed (6) | Granix, Stendra, Voquezna Triple Pak, Accrufer, Sogroya, Egrifta | Curve already starts at the real launch (launch quarter = first SDUD quarter) |
| Medicaid uptake slow (10) | Fycompa, Xolremdi, Sirturo, Bevyxxa, Exxua, Ibsrela, Impavido, Aemcolo, Scenesse, Kybella | Mostly drugs Medicaid rarely pays for or that are supplied outside retail pharmacy |

- **Six more analogs have a late start marketing date but aren't flagged**, because they have no Medicaid data yet: Ozempic oral, Moxidectin, Saphnelo sc, Spevigo sc, Lunsumio sc, Zegfrovy.
- **Across the pool,** 351 of 405 analogs have their first Medicaid fill in the start-marketing quarter or the next one. The 4-quarter threshold catches only the real tail.

**What it means for the tool.** "Late" isn't one thing. Routes added later and drugs Medicaid rarely pays for should leave the pool (decisions 1–2). Delayed commercial launches can stay, because the curve starts at the real launch.

**Open checks.**
- **Actemra sc:** first Medicaid quarter (2013Q1) is before its sc application was approved (2013-10). Find which NDC has that row.
- **Egrifta:** earliest NDC in `ndc_map` is a 2014 listing for a 2010 approval. Launch-era NDCs may be missing, so the curve may start mid-life.
- **Fycompa:** listed as marketed on approval day, but as a controlled substance it likely waited for DEA scheduling. Verify the launch date.
- **Spevigo sc, Lunsumio sc:** sc forms added under the brand's original BLA. The classification reads the application's ORIG date, so it can't see them and calls them "commercial launch delayed". A route-level approval date (from supplements) would fix this.

---

## Reproduce

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/jupyter lab eda/
```

The notebooks only read `data/processed/`. If the data is rebuilt, re-run them and update the numbers here.
