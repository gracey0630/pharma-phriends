# Pharma Phriends: Launch Forecast Tool

Forecasts first-3-year TRx for a new US drug launch using analog launches (Bass diffusion), an epidemiology funnel, and payer-access scenarios.

- Data collection plan: [docs/data_collection_plan.md](docs/data_collection_plan.md)
- Running notes and decisions: [LOG.md](LOG.md). Add a dated entry when you work on something.

## Collecting data

```bash
pip install -r requirements.txt
python -m scrapers.openfda      # -> data/reference/drug_master.csv   (FDA drug attributes + NDCs)
python -m scrapers.sdud         # -> data/processed/sdud_quarterly.csv (Medicaid TRx by quarter, ~12 min first run)
python -m scrapers.partd        # -> data/processed/partd_annual.csv   (Medicare claims, patients, fills/patient)
python -m scrapers.plot_check   # -> data/processed/sdud_launch_curves.png
```

To add drugs, put them in `data/reference/seed_drugs.csv` and re-run. API responses are cached in `data/raw/` (not committed), so re-runs are fast.

All processed files use one long format: `brand_key, source, payer, period, metric, value, pulled_at`.
