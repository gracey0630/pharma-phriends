# Pharma Phriends: Launch Analog and Input Tool

Helps a forecasting team choose and defend the two inputs a launch forecast depends on: **how big the launch can get** (ceiling) and **how fast it gets there** (trajectory). It recommends comparable launches, sizes the market, and shows an illustrative curve with its limitations.

## Docs
| Doc | What's in it |
|---|---|
| [docs/user_journey.md](docs/user_journey.md) | What the tool does, step by step (draft, still changing) |
| [docs/data_sources.md](docs/data_sources.md) | What to pull, from where, and when to check it's current |
| [docs/data_model.md](docs/data_model.md) | Tables, dependencies, workstreams, build status |
| [docs/decisions.md](docs/decisions.md) | Decision log and open questions |
| [docs/implementation_plan.md](docs/implementation_plan.md) | How the Analog Finder is built: steps, agreed decisions, module contracts, final checks |
| [docs/example_drug.md](docs/example_drug.md) | Torevia, the fictional example drug the demo runs on |
| [docs/archive/](docs/archive/) | Earlier versions of the docs above |
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

## Analog Finder (in progress)
Lives in `analog_finder/`, reads `data/processed/`, and runs in two stages: a Label Research Agent that reads approved sources and writes unapproved evidence rows for review, and the finder that ranks analogs for a target drug, has the forecaster confirm 3–5, and builds a similarity-weighted uptake curve. Plan and build order: [implementation_plan.md](docs/implementation_plan.md); one spec per component in `analog_finder/docs/components/`.
```bash
pip install -r analog_finder/requirements.txt          # includes the pipeline's requirements
pytest analog_finder/tests                             # offline; no API key needed
python -m analog_finder.io --scenario torevia          # merged config + what loads (step 1)
```
Without `GEMINI_API_KEY` in `.env` the finder uses a fake model and still runs. With a key, also set `GEMINI_MODEL`.
On Apple silicon, build the venv from a native Python: `.venv/bin/python -c "import platform; print(platform.machine())"` should print `arm64`. An Intel Anaconda install prints `x86_64`, and then some packages (e.g. `cryptography`, needed by google-genai) try to build from source and fail.

Run the finder (steps 2–9; offline, no API key):
```bash
python -m analog_finder.finder --scenario torevia                 # interactive: confirm / reject the top 5
python -m analog_finder.finder --scenario torevia --auto-confirm  # take the top 5 as ranked
python -m analog_finder.finder --scenario torevia --summaries auto   # candidate cards from Gemini if a key is set (step 13)
python -m analog_finder.finder --scenario torevia --holdout latuda_oral --auto-confirm   # evaluation-style run
python -m analog_finder.evaluate                                  # leave-one-out evaluation (step 8), ~20 s
python -m analog_finder.evaluate --embedders tfidf rxbert         # compare embedders (step 9; downloads RxBERT once)
python -m analog_finder.research.queue --scenario torevia         # label reads still needed, in order (step 10)
python -m analog_finder.research --analogs latuda_oral            # label research agent (step 11); writes only with a Gemini key
```
Outputs: `data/scenarios/torevia/` (`analog_recommendations.csv`, `analog_weights.csv`, `uptake_curve.csv`); `--until filters|embed|score|loop` stops early; `--resume` continues a saved session.

Planned commands, as the steps land:
```bash
streamlit run analog_finder/app/Home.py                # review page + finder page
```

## Working together
- Workstreams (0, A–E) and what each owns: [data_model.md](docs/data_model.md#workstreams).
- Small tasks (doc edits, a few evidence rows, small fixes) go straight to `main`: pull first, commit small, push. Bigger work (multi-day, new `pipeline/` modules, rule changes, rebuilding `data/processed/`) gets a branch named `<workstream>/<topic>` and a PR. Analog Finder steps are one PR each, branch `<initials>/step-<NN>-<name>`. Details in [CLAUDE.md](CLAUDE.md#workflow).
- If your change affects a rule, table or journey step, update the doc in the same commit or PR.
- Settled an open question? Add it to the log in [decisions.md](docs/decisions.md) and remove it from the list.

## Layout
```
data/
├── raw/<source>/   downloads, unchanged, + manifest (gitignored)
├── reference/      approved / manual tables (analog_evidence, epi_funnel)
├── processed/      tables built by code (committed): analogs.csv, sdud_quarterly.csv, ndc_map.csv,
│                   launch_curves.csv, analog_features.csv, bass_fits.csv, indication_history.csv,
│                   medicaid_enrollment.csv, checks.md
├── scenarios/<s>/  per-forecast outputs from the finder (committed for torevia only)
└── cache/          embedding cache (gitignored)
docs/               user journey, sources, data model, decisions, implementation plan, example drug; archive/
pipeline/           build code: fda, sdud, ndc, rxclass, enrollment, curves, features, bass, labels, build, checks
analog_finder/      (planned) config/, scenarios/ (target drug profiles), finder/, research/, app/, tests/
```
