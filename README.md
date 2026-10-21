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

## Working together
- Workstreams (0, A–E) and what each owns: [data_model.md](docs/data_model.md#workstreams).
- Branch per task, named `<workstream>/<topic>` (e.g. `b/sdud-ndc-map`); merge to `main` through a PR.
- If your change affects a rule, table or journey step, update the doc in the same PR.
- Settled an open question? Add it to the log in [decisions.md](docs/decisions.md) and remove it from the list.

## Layout
```
data/
├── raw/<source>/   downloads, unchanged, + manifest (gitignored)
├── reference/      approved / manual tables (analog_evidence, target_drug, epi_funnel)
└── processed/      tables built by code
docs/               user journey, sources, data model, decisions
```
