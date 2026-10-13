"""Sanity-check plot: Medicaid TRx by quarter since launch for each seed brand.

Usage: python -m scrapers.plot_check  -> data/processed/sdud_launch_curves.png
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from scrapers.common import PROCESSED, REFERENCE


def main():
    trx = pd.read_csv(PROCESSED / "sdud_quarterly.csv").query("metric == 'trx'")
    master = pd.read_csv(REFERENCE / "drug_master.csv", dtype=str).set_index("brand_key")
    trx["q_index"] = trx.period.str[:4].astype(int) * 4 + trx.period.str[-1].astype(int) - 1

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    for brand, g in trx.groupby("brand_key"):
        launch = pd.Timestamp(master.loc[brand, "approval_date"])
        launch_q = launch.year * 4 + (launch.month - 1) // 3
        g = g.assign(q_since=g.q_index - launch_q).sort_values("q_since")
        g = g[g.q_since <= 20]
        ax1.plot(g.q_since, g.value, marker=".", label=brand)
        ax2.plot(g.q_since, g.value / g.value.max(), marker=".", label=brand)
    ax1.set(title="Medicaid TRx per quarter (national)", xlabel="Quarters since FDA approval", ylabel="TRx")
    ax2.set(title="Normalized to each brand's max (first 5 yrs)", xlabel="Quarters since FDA approval", ylabel="share of max")
    ax1.legend()
    fig.tight_layout()
    fig.savefig(PROCESSED / "sdud_launch_curves.png", dpi=110)
    print("wrote data/processed/sdud_launch_curves.png")


if __name__ == "__main__":
    main()
