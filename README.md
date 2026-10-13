# Pharma Phriends: Launch Forecast Tool

Forecasts first-3-year TRx for a new US drug launch using analog launches (Bass diffusion), an epidemiology funnel, and payer-access scenarios.

- Data collection plan: [docs/data_collection_plan.md](docs/data_collection_plan.md)
- Running notes and decisions: [LOG.md](LOG.md). Add a dated entry when you work on something.

## Collecting data

```bash
pip install -r requirements.txt
python -m scrapers.fda_files       # -> data/reference/drug_master.csv   (Drugs@FDA + NDC Directory bulk files, NME compilation, DailyMed, RxClass)
python -m scrapers.openfda         #    alternative drug master via the openFDA API (was returning 500s on 2026-10-13)
python -m scrapers.sdud            # -> data/processed/sdud_quarterly.csv (Medicaid TRx by quarter, ~2 min per brand first run)
python -m scrapers.cms_spending    # -> data/processed/partd_annual.csv, medicaid_spending_annual.csv (claims, patients, spend, manufacturers)
python -m scrapers.clinicaltrials  # -> data/processed/ctgov_trials.csv  (phase 3 + pre-approval phase 2 trials, eligibility, line-of-therapy hint)
python -m scrapers.plot_check      # -> data/processed/sdud_launch_curves.png
```

To add a drug, put it in `data/reference/seed_drugs.csv` (hand tags like `line_of_therapy` and `first_in_class` go there too, so re-runs don't wipe them), then run each scraper with `--brands <brand_key>`. That only replaces that brand's rows in the output files, so you don't re-pull every other brand:

```bash
python -m scrapers.fda_files --brands ibrance && python -m scrapers.sdud --brands ibrance && python -m scrapers.cms_spending --brands ibrance && python -m scrapers.clinicaltrials --brands ibrance
```

The epi funnel is hand-curated in `data/reference/epi_funnel.csv` (low/base/high with a source tag per step). API responses are cached in `data/raw/` (not committed), so re-runs are fast.

All processed utilization files use one long format: `brand_key, source, payer, period, metric, value, pulled_at`. `ctgov_trials.csv` is one row per trial.
