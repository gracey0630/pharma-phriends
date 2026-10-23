# EDA: Medicaid volume, curve shape and fit quality (Joshua)

**Author:** Joshua · **Date:** 2026-10-23 · **Branch:** `eda` · **Data:** `data/processed/` as committed on `main` at `2dec2a2` (built 2026-10-22; no rebuild needed)

Follows the write-up format in [README.md](README.md): **Question · Data · Method · Findings · What it means for the tool · Open checks**. The notebook reproduces every number.

## Summary

| EDA | Notebook | Question | Headline | Feeds |
|---|---|---|---|---|
| Volume vs shape | [volume_vs_shape_joshua.ipynb](volume_vs_shape_joshua.ipynb) | Does Medicaid volume affect curve shape and fit quality? | Volume drives fit quality (ρ = 0.62), and counting noise alone reproduces it. Oncology's weak fits are mostly oncology being small in Medicaid. Small drugs also really do start faster and peak sooner, which noise doesn't explain | Weak-fit rule; analog similarity score; `launch_eda` §4 (oncology fits) |

## Decisions these suggest (for the team)

1. **Add a low-volume flag to `analog_features`** (e.g. peak Medicaid TRx < 300 a quarter) and show it next to the fit. Below that, a low R² is what counting noise produces on its own, so it says little about the analog's shape.
2. **Use Medicaid volume as a similarity feature** in `analog_recommendations`. Small and large analogs have different shapes (small: higher p, lower q, earlier peak), so a small-population target should be matched to small analogs and the reverse.
3. **Don't treat oncology as a shape Bass can't fit.** Mid-volume oncology fits as well as any other area (6% with R² < 0.9). Re-word the oncology finding in `launch_eda` §4 when the EDAs are combined. Another curve form is still worth trying for the rise-and-fall curves.

---

## 1. Volume vs shape

**Notebook:** [volume_vs_shape_joshua.ipynb](volume_vs_shape_joshua.ipynb)

**Question.** Does Medicaid volume change the shape of launch curves, or how well Bass fits them? Is the oncology weak-fit problem in `launch_eda` §4 really about volume?

**Data.** `analog_features.csv` (`peak_trx`, area, flags), `launch_curves.csv` (share of peak Q0–Q20, non-provisional), `bass_fits.csv` (p, q, m, R²), `analogs.csv` (approval year). The 250 usable analogs (`checks.md` funnel). Area as in `launch_eda` (ATC 1, with L split into oncology and immunology). **Volume** = `peak_trx`, the highest Medicaid TRx in a quarter over Q0–Q20. It measures Medicaid use, not national size.

**Method.**
- Volume fifths (50 analogs each) and three bands: small ≤ 766 peak TRx a quarter (bottom two fifths), mid ≤ 14,748, large (top fifth).
- Fit quality and shape (quarters to 50% / 80% of peak, share at Q5, peak quarter, rise-and-fall = last quarter < 0.7 of peak) by fifth, by band, and by band within area. Spearman ρ for the trends.
- **Shrink-and-refit test** (noise vs real shape): each large analog's real curve scaled to a peak of 100, 300 and 1,000 TRx; counting noise added (patients ~ Poisson(TRx / 3), 3 fills each); quarters < 11 suppressed; curves with a blank after Q2 dropped, as the enough-data rule would; refitted with the pipeline's `fit()`. 5 draws per analog per volume.

**Findings.**
- **Oncology is the smallest area in Medicaid:** median peak 386 TRx, 70% small, no large analogs. Nervous system is the largest (median 13,317).
- **Fit quality rises with volume** (ρ = 0.62). R² < 0.9 in 74% of the smallest fifth (peak ≤ 322) vs 10% of the largest.
- **The trend holds inside every area**, most strongly in oncology (ρ = 0.80). Mid-volume oncology: R² < 0.9 in 1 of 18 fits (6%), vs 32 of 43 (74%) small oncology.
- **Noise alone reproduces it.** Large curves shrunk to a peak of 100 / 300 / 1,000 have R² < 0.9 in 94% / 33% / 12% of fits; real analogs at about those volumes: 74% / 32% / 20%.
- **Weak fits with a parameter on a bound** (mostly m at the cap, curves still climbing) are not a volume effect: 4–16% in every fifth.
- **Small drugs start faster and peak sooner, and noise doesn't explain it.** Median quarter to 50% of peak: Q5 small, Q8 mid, Q9 large. Share of peak at Q5: 0.51 small vs 0.27 large; the shrunk large curves stay at 0.29–0.36. 27% of small drugs rise and fall vs 8% of large. It holds within oncology (ρ = −0.56), immunology (−0.61) and other areas (−0.35).
- **Volume shifts the Bass parameters**, even among good fits: small p 0.058 / q 0.09, mid 0.025 / 0.21, large 0.019 / 0.19.

**What it means for the tool.** Two things happen at low volume. Fits get noisy, which a volume flag should explain to the forecaster (decision 1). Separately, small drugs follow a faster-start, earlier-peak shape, so analog size should be part of matching (decision 2). A likely reason, not tested here, is that small Medicaid drugs treat small, already-identified populations (rare disease, biomarker-selected cancers) who start treatment quickly.

**Open checks.**
- **Medicaid-small vs market-small:** oncology is Medicare-heavy, so a small Medicaid cancer drug may be large nationally. A Part D cross-check would show which "small" means. Part D stays a cross-check, never mixed into the curves.
- **Noise model is a lower bound.** Real quarter-to-quarter swings are lumpier than Poisson patients, so the R² noise threshold may be above 300 TRx.
- **Partial suppression** undercounts peak TRx (94% of usable analogs have a suppressed row somewhere, `launch_eda` §1). That affects small drugs most and may shift the band edges slightly.
- Interacts with open topic `sc_clinic`: clinic-administered sc drugs are still in the pool. If they are mostly small in SDUD (not checked), they add to the small band; re-run once they're flagged.

---

## Reproduce

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/jupyter nbconvert --to notebook --execute --inplace eda/volume_vs_shape_joshua.ipynb
```

The notebook only reads `data/processed/` (and imports `pipeline.bass` for the fit). The shrink-and-refit test uses a fixed seed (2026). If the data is rebuilt, re-run it and update the numbers here.
