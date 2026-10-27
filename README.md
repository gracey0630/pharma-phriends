# Pharma Phriends: Launch Analog and Input Tool

Helps a forecasting team choose and defend the two inputs a launch forecast depends on: **how big the launch can get** (ceiling) and **how fast it gets there** (trajectory). It recommends comparable launches, sizes the market, and shows an illustrative curve with its limitations.

## Docs
| Doc | What's in it |
|---|---|
| [docs/user_journey.md](docs/user_journey.md) | What the tool does, step by step (draft, still changing) |
| [docs/data_sources.md](docs/data_sources.md) | What to pull, from where, and when to check it's current |
| [docs/data_model.md](docs/data_model.md) | Tables, dependencies, workstreams, build status |
| [docs/decisions.md](docs/decisions.md) | Decision log and open questions |
| [CLAUDE.md](CLAUDE.md) | Short project briefing (loaded automatically by Claude Code; useful for anyone) |

## Setup
Requires Python 3.12+.
```bash
git clone https://github.com/gracey0630/pharma-phriends && cd pharma-phriends
python3 -m venv .venv && source .venv/bin/activate   # or: conda create -n pharma python=3.12 && conda activate pharma
pip install -r requirements.txt
cp .env.example .env                                  # fill in API keys
```
If `python3 --version` is older than 3.12 (macOS ships 3.9), install a newer one first, e.g. `brew install python@3.13`, and create the venv with `python3.13 -m venv .venv`.

## Build the data
```bash
python -m pipeline.build            # everything: FDA files, SDUD, RxClass -> data/processed/analogs.csv
python -m pipeline.build --refresh  # re-download every source first (do this before a final build)
```
The first run downloads ~1 GB and takes about an hour, mostly SDUD at ~3.5 min per year. Later runs reuse `data/raw/` and take a few minutes. `data/processed/` is committed, so you only need to rebuild to refresh or change the data. Output tables and columns: [data_model.md](docs/data_model.md#v1-analog-table-current-spec). Current status and next steps: [CLAUDE.md](CLAUDE.md#status--handoff).

## Working together
- Workstreams (0, A–E) and what each owns: [data_model.md](docs/data_model.md#workstreams).
- Small tasks (doc edits, a few evidence rows, small fixes) go straight to `main`: pull first, commit small, push. Bigger work (multi-day, new `pipeline/` modules, rule changes, rebuilding `data/processed/`) gets a branch named `<workstream>/<topic>` and a PR. Details in [CLAUDE.md](CLAUDE.md#workflow).
- If your change affects a rule, table or journey step, update the doc in the same commit or PR.
- Settled an open question? Add it to the log in [decisions.md](docs/decisions.md) and remove it from the list.

## Layout
```
data/
├── raw/<source>/   downloads, unchanged, + manifest (gitignored)
├── reference/      approved / manual tables (analog_evidence, target_drug, epi_funnel)
└── processed/      tables built by code (committed): analogs.csv, sdud_quarterly.csv, ndc_map.csv,
                    launch_curves.csv, analog_features.csv, bass_fits.csv, indication_history.csv,
                    medicaid_enrollment.csv, checks.md
docs/               user journey, sources, data model, decisions
pipeline/           build code: fda, sdud, ndc, rxclass, enrollment, curves, features, bass, labels, build, checks
```
