# EDA

Exploratory analysis of the tables in `data/processed/`. Everyone's EDAs will be combined into one write-up later, so they follow one naming convention, one write-up format, and a registry that stops two people doing the same analysis.

**Before starting an EDA (people and Claude sessions alike):**
1. Work on the shared **`eda`** branch: `git switch eda && git pull`. Read the **registry** below as it is on `origin/eda` (and `origin/main` once EDA is merged). Someone may already be doing your topic, sometimes as one section of a bigger notebook.
2. If the topic is taken, extend that notebook (ask its owner) instead of starting a new one. If it overlaps, say how yours differs in the registry row.
3. Claim the topic: add or update your registry row (status `in progress`), commit and push it to `eda` before you start the analysis, so others see the claim.
4. Commit only your own files plus your registry rows; `git pull` before every push. Never force-push `eda`.

## Naming

| Thing | Pattern | Example |
|---|---|---|
| Branch | the shared `eda` branch (no `eda/...` branches: git can't have both) | `eda` |
| Notebook | `eda/<topic>_<name>.ipynb`, topic in snake_case, your first name in lowercase | `eda/late_launch_gabrielle.ipynb` |
| Write-up | `eda/eda_<name>.md`, one per person, covering all your notebooks | `eda/eda_gabrielle.md` |
| Topic | the registry's topic id; reuse it, don't rename | `late_launch` |

No other files in `eda/`. Charts stay inside the notebooks; scratch work stays out of the repo.

## Notebooks
- Read only from `data/processed/` (and `data/reference/`). Never write to `data/`. If an EDA needs a new table or column, that's a pipeline change in its own PR.
- Start with this cell so it runs from the repo root or from `eda/`:
  ```python
  from pathlib import Path
  ROOT = Path.cwd() if (Path.cwd() / "pipeline").exists() else Path.cwd().parent
  PROCESSED = ROOT / "data" / "processed"
  ```
- A markdown cell before each section says what it shows; the last cell is **Takeaways**.
- Run top to bottom and commit with outputs (`.venv/bin/jupyter nbconvert --to notebook --execute --inplace eda/<file>.ipynb`), so the numbers can be read on GitHub.
- Use only packages in `requirements.txt`. Adding one is its own PR.

## Write-up format (`eda_<name>.md`)

So the files can be stacked into one document, every write-up has:

1. **Header:** author, date, branch, data version (`main` commit the `data/processed/` tables came from).
2. **Summary table:** `| EDA | Notebook | Question | Headline | Feeds |`, one row per notebook. *Feeds* = the decision, rule or table it informs.
3. **Decisions these suggest:** numbered proposals for the team, kept apart from findings so they can move to [decisions.md](../docs/decisions.md).
4. **One section per notebook**, with exactly these headings: **Question · Data · Method · Findings · What it means for the tool · Open checks**.
5. **Reproduce:** the commands to re-run.

[eda_gabrielle.md](eda_gabrielle.md) is a worked example.

## Registry

One row per topic. A topic covered by a section of a bigger notebook names the section (e.g. `launch_eda` §3). Add yours before you start; update the status when the PR merges. Status: `in progress` / `done` / `open` (idea, nobody on it).

| Topic | Question | Owner | Notebook | Status |
|---|---|---|---|---|
| `launch_eda` | Broad first pass: pool, curve shape by area, Q20 peak, Bass fits, distortion flags, seed brands (one notebook, six sections) | Christina | [launch_eda_christina.ipynb](launch_eda_christina.ipynb) | in progress |
| `pool_funnel` | Where do analogs leave the pool, by route, area and era? Overlaps `launch_eda` §1; adds the area × route and era breakdowns | Gabrielle | [pool_funnel_gabrielle.ipynb](pool_funnel_gabrielle.ipynb) | in progress |
| `suppression` | Where are SDUD quarters blank (suppressed vs no row), and why? | Gabrielle | [suppression_gabrielle.ipynb](suppression_gabrielle.ipynb) | in progress |
| `late_launch` | Why do 19 analogs start in Medicaid > 4 quarters after approval? | Gabrielle | [late_launch_gabrielle.ipynb](late_launch_gabrielle.ipynb) | in progress |
| `q20_peak` | Is the Q20 peak real or COVID enrollment growth? (open question in decisions.md) | Christina | `launch_eda` §3 | in progress |
| `bass_fit_quality` | Which Bass fits can be trusted (low R², parameters on a bound)? | Christina | `launch_eda` §4 | in progress |
| `curves_by_area` | Do launch shapes (share of peak, time to 50/80% of peak) differ by area and route? | Christina | `launch_eda` §2 | in progress |
| `sc_clinic` | Which sc analogs are clinic-administered? (input to the self-administered flag) | | | open |
| `label_expansion` | Does a flagged efficacy supplement change the curve? How noisy is the flag? | Christina | `launch_eda` §5 | in progress |
| `launch_cohorts` | Did launch shapes change across 2010–13, 2014–17, 2018–21? | | | open |
| `seed_brands` | Do the 8 seed brands' curves and fits look as expected? | Christina | `launch_eda` §6 | in progress |
| `volume_vs_shape` | Does Medicaid volume affect curve shape and fit quality? | | | open |

## Combining

When the team combines EDAs, the summary tables and "Decisions these suggest" lists merge first; overlapping findings are reconciled against the registry's topic ids.
