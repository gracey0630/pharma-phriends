"""Launch curves: Medicaid TRx by quarter since launch (Q0-Q20) and share of peak.

Rules (docs/data_model.md; decisions 2026-10-22):
  - launch quarter = approved launch_date in analog_evidence.csv; otherwise the first SDUD quarter with any
    row (a suppressed row still means 1-10 Rx were dispensed), never before the approval quarter
  - the latest PROVISIONAL quarters of SDUD are incomplete: kept in the curve, flagged, left out of the peak
  - peak = max TRx over Q0-Q20 (non-provisional); share_of_peak = trx / peak
  - suppressed quarters stay blank; a quarter with no SDUD row at all has trx and suppressed_rows blank
  - label_expansion_flag: on from the first possible label expansion (indication_history) onward

Output: data/processed/launch_curves.csv, one row per analog x quarter since launch:
        analog_id, q_since_launch, period, trx, suppressed_rows, provisional, share_of_peak, label_expansion_flag

Usage: python -m pipeline.build (needs sdud_quarterly, analog_evidence and indication_history)
"""
import pandas as pd

from pipeline.common import date_qnum, qnum, qstr

WINDOW = 20  # Q0-Q20
PROVISIONAL = 2  # latest SDUD quarters treated as incomplete


def provisional_periods(quarterly):
    latest = max(qnum(p) for p in quarterly.period.unique())
    return {qstr(n) for n in range(latest - PROVISIONAL + 1, latest + 1)}


def launch_quarters(pool, quarterly, evidence):
    """analog_id -> launch_quarter, launch_source ('evidence' or 'first sdud quarter'). Analogs with neither are left out."""
    ev = evidence[(evidence.field == "launch_date") & (evidence.approved.str.lower() == "true")]
    ev = ev.drop_duplicates("analog_id", keep="last").set_index("analog_id").value
    first_row = (quarterly[quarterly.metric == "trx"]
                 .merge(pool[["analog_id", "approval_date"]], on="analog_id"))
    first_row = first_row[first_row.period.map(qnum) >= first_row.approval_date.map(date_qnum)]
    first_row = first_row.groupby("analog_id").period.min()
    rows = []
    for a in pool.analog_id:
        if a in ev.index:
            rows.append((a, qstr(date_qnum(ev[a])), "evidence"))
        elif a in first_row.index:
            rows.append((a, first_row[a], "first sdud quarter"))
    return pd.DataFrame(rows, columns=["analog_id", "launch_quarter", "launch_source"]).set_index("analog_id")


def build(quarterly, launch, history):
    wide = quarterly[quarterly.metric.isin(["trx", "suppressed_rows"])].pivot_table(
        index=["analog_id", "period"], columns="metric", values="value", aggfunc="first")
    wide = wide.apply(pd.to_numeric, errors="coerce")
    provisional = provisional_periods(quarterly)
    latest = max(qnum(p) for p in quarterly.period.unique())
    expansion = history[history.kind != "original"].groupby("analog_id").q_since_launch.min()

    frames = []
    for a, (lq, _) in launch.iterrows():
        start = qnum(lq)
        q = range(0, min(WINDOW, latest - start) + 1)
        periods = [qstr(start + i) for i in q]
        c = pd.DataFrame({"analog_id": a, "q_since_launch": list(q), "period": periods})
        rows = wide.loc[a] if a in wide.index.get_level_values(0) else pd.DataFrame(columns=["trx", "suppressed_rows"])
        c = c.join(rows, on="period")
        c["provisional"] = c.period.isin(provisional)
        peak = c.loc[~c.provisional, "trx"].max()
        c["share_of_peak"] = (c.trx / peak).round(4) if peak and peak > 0 else pd.NA
        first_exp = expansion.get(a, pd.NA)
        c["label_expansion_flag"] = (c.q_since_launch >= max(first_exp, 0)) if pd.notna(first_exp) else False
        frames.append(c)
    out = pd.concat(frames, ignore_index=True)
    out["trx"] = out.trx.astype("Int64")
    out["suppressed_rows"] = out.suppressed_rows.astype("Int64")
    cols = ["analog_id", "q_since_launch", "period", "trx", "suppressed_rows", "provisional", "share_of_peak",
            "label_expansion_flag"]
    return out[cols]
