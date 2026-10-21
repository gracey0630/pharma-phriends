# Pharma Phriends: Launch Analog and Input Tool

Helps a forecasting team choose and defend the two inputs a launch forecast depends on: **how big the launch can get** (ceiling) and **how fast it gets there** (trajectory). It recommends comparable launches, sizes the market, and shows an illustrative curve with its limitations.

## Docs
- [docs/data_sources.md](docs/data_sources.md): what to pull, from where, and when to check it's current
- [docs/data_model.md](docs/data_model.md): tables, dependencies, workstreams

## Layout
```
data/
├── raw/<source>/   downloads, unchanged, + manifest (gitignored)
├── reference/      approved / manual tables (analog_evidence, target_drug, epi_funnel)
└── processed/      tables built by code
docs/
```
