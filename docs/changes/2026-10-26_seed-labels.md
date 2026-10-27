# 2026-10-26: Seed label approvals and rebuild

**Who:** Gabrielle (checking done with Claude Code) · **Branch:** `c/seed-review` · **PR:** [#6](https://github.com/gracey0630/pharma-phriends/pull/6) · **Base:** `main` at `1bc6134` (ATC class fix)

## Summary
- 27 of the 31 seed label values are approved and now reach `analog_features`.
- New `python -m pipeline.labels --check` verifies label quotes automatically.
- A label-reads plan is in [data_model.md](../data_model.md#label-reads-plan).
- `data/processed/` was rebuilt from sources downloaded on 2026-10-26. Apart from the approvals, the only data changes are one Juxtapid NDC listing and 3 new generic NDCs; no Medicaid counts and no pool numbers changed.

**The approvals are provisional.** They rest on the checks below, and values (especially # competitors) may be revisited once the team picks the example drug and its analogs.

## 1. Label values (`data/reference/analog_evidence.csv`)

### Approved (27, `approved_by = Gabrielle`)
| Field | Analogs | How it was checked |
|---|---|---|
| Line of therapy | all 8 | Quote is verbatim in the ORIG label (`pipeline.labels --check`); each label PDF says "Initial U.S. Approval" in its launch year |
| Dosing frequency | all 8 | Same |
| # competitors at launch | all 8 | Each listed competitor's approval date for the same first indication checked against Drugs@FDA / press. Ibrance = 0 is a judgment call: Afinitor (2012) was approved only after a nonsteroidal aromatase inhibitor, i.e. not first line |
| Launch date | Taltz, Siliq, Ibrance | Company statement of actual availability (see below) |

### Not approved (4)
- **Launch dates for Otezla (2014-03), Tremfya (2017-07), Skyrizi (2019-05), Sotyktu (2022-09).** The quotes are pre-launch statements ("expected to be available…"). Medicaid data agrees within a quarter, but an actual launch announcement is still needed.
- **Cosentyx:** no launch date row. Sources disagree (January vs March 2015) and no Novartis release was found.

### Source fixes
| Row | Before | After |
|---|---|---|
| Taltz launch date (2016-04) | Trade-press excerpt (PharmTech), marked `[excerpt, verify]` | Lilly Q1 2016 results, SEC 8-K, 2016-04-26 release: "we recently launched Taltz in the U.S., following its FDA approval last month" |
| Skyrizi, Sotyktu competitor quotes | Ilumya (2018-03-21) | Ilumya (2018-03-20), the approval date (Sun announced on the 21st) |
| Skyrizi, Sotyktu competitor quotes | Cimzia (2018) | Cimzia (2018-05-24), its psoriasis efficacy supplement in Drugs@FDA (BLA125160 SUPPL-283) |

Counts didn't change with the date fixes.

## 2. Code and docs
- **`pipeline/labels.py`:** `--check` downloads each label-sourced row's PDF (`source_url`) and reports `verbatim` or how far the quote matched. Launch dates and competitor counts show `not checked` (not label quotes).
- **`docs/data_model.md`:** new "Label-reads plan" (7 steps, what each unblocks, field sources, review process); `analog_evidence` build status updated.
- **`docs/data_sources.md`:** labels row mentions `--check`.
- **`CLAUDE.md`:** current state, known issues, pick-up list and log follow the plan.
- **`eda/seed_labels_gabrielle.ipynb`:** rebuild check (38 checks) plus a first look at label fields vs uptake for the seed 8.

## 3. Rebuild (`python -m pipeline.build`)
Run from a clean `data/raw/` (all sources downloaded 2026-10-26; previous build used 2026-10-22/23 downloads). Not `--refresh`, but the effect is the same since nothing was cached.

### Expected changes (from the approvals)
| File | Change |
|---|---|
| `analog_features.csv` | Seed 8: `line_of_therapy`, `dosing_frequency`, `n_competitors_at_launch` filled; `fields_not_approved` 4→1 (Otezla, Tremfya, Skyrizi, Sotyktu) and →0 (Cosentyx, Taltz, Siliq, Ibrance); `launch_source` = `evidence` for Taltz, Siliq, Ibrance, launch quarter unchanged |
| `checks.md` | "27 approved, 4 waiting for review"; unapproved list down to Otezla, Skyrizi, Sotyktu, Tremfya; launch quarter source 403 first SDUD quarter + 3 evidence |

### Drift from newer downloads
| File | Change | Effect |
|---|---|---|
| `sdud_quarterly.csv` | `pulled_at` 2026-10-23 → 2026-10-26 on every row | None: no row added or removed, no value changed (SDUD last modified July 2026) |
| `ndc_map.csv` | Juxtapid NDC 76431-120 moved from the current NDC listing to the excluded file (route now inferred) | Juxtapid `ndc_match_issues` 7→8 in `analog_features`; curve unchanged |
| `generic_ndcs.csv` | +3: two Aubagio generics (Civica, ANDA209598), one Eylea biosimilar (Sandoz, BLA761382) | None: no generic / exclusivity date in `analogs.csv` changed |
| `indication_history.csv` | Two Bimzelx efficacy supplements approved the same day swapped order | None: same rows |
| `checks.md` | Source freshness dates → 2026-10-26 | — |

### Unchanged
`analogs.csv`, `candidate_pool.csv`, `launch_curves.csv`, `bass_fits.csv`, `medicaid_enrollment.csv`. Pool: 426 analogs, 378 with Medicaid Rx, 250 usable, 256 Bass fits.

### Verification
`eda/seed_labels_gabrielle.ipynb` → **REBUILT: all 38 checks pass** (every approved value in `analog_features`, unapproved ones blank, launch source and quarter correct).

## 4. Still open
- The 4 launch dates and Cosentyx's.
- Label reads beyond the seed 8, starting with the example drug's therapeutic area (team decision pending).
- Other label reads in the plan: self-injected vs clinic-given, the 16 `INJECTABLE;INJECTION` routes, approval letters for efficacy supplements.
- Merge: CLAUDE.md also changed on `eda`, so the second branch to merge resolves a small conflict.
