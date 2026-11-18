"""Launch curves: Medicaid TRx by quarter since launch (Q0-Q20) and share of peak.

Rules (docs/data_model.md; decisions 2026-10-22, 2026-10-30):
  - launch quarter = approved launch_date in analog_evidence.csv; otherwise the first SDUD quarter with any
    row (a suppressed row still means 1-10 Rx were dispensed), never before the approval quarter
  - the latest PROVISIONAL quarters of SDUD are incomplete: kept in the curve, flagged, left out of the peak
  - trx = the mid estimate (suppressed rows imputed, pipeline.sdud); trx_low / trx_high bound it, trx_reported is
    the visible sum, imputed_share = the share of trx that is imputed
  - a quarter with no SDUD row for any of the analog's NDCs is 0 TRx (no_sdud_row = True): SDUD has rows only for
    paid or dispensed prescriptions, and reports no explicit zeros
  - peak = max trx over Q0-Q28 (PEAK_WINDOW, non-provisional; decision 2026-11-14), read from every SDUD quarter,
    not only the Q0-Q20 rows kept here; share_of_peak = trx / peak. peak_confirmed = the analog has the full
    Q0-Q28 window. Without it the peak is the highest quarter so far, so share_of_peak is an upper bound
    (exact if the peak has passed, too high if it's still ahead)
  - label_expansion_flag: on from the first possible label expansion (indication_history) onward

Output: data/processed/launch_curves.csv, one row per analog x quarter since launch:
        analog_id, q_since_launch, period, trx, trx_low, trx_high, trx_reported, suppressed_rows, imputed_share,
        no_sdud_row, provisional, share_of_peak, label_expansion_flag

peaks() gives one row per analog (peak_trx, peak_q, peak_window_end, peak_confirmed) for analog_features.

Usage: python -m pipeline.build (needs sdud_quarterly, analog_evidence and indication_history)
"""
import pandas as pd

from pipeline.common import date_qnum, qnum, qstr

WINDOW = 20  # Q0-Q20: the curve rows and the Bass fit window
PEAK_WINDOW = 28  # Q0-Q28: the peak share_of_peak divides by (7 years; EDA peak_window)
PROVISIONAL = 2  # latest SDUD quarters treated as incomplete
TRX_COLS = ["trx", "trx_low", "trx_high", "trx_reported", "suppressed_rows", "imputed_share"]


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


def peaks(quarterly, launch):
    """analog_id -> peak_trx (max trx over Q0-Q28, complete quarters; a quarter with no SDUD row is 0), peak_q (first
    quarter reaching it), peak_window_end (Q28, or the last complete quarter if earlier) and peak_confirmed (full
    Q0-Q28 window)."""
    trx = quarterly[quarterly.metric == "trx"]
    trx = pd.Series(pd.to_numeric(trx.value, errors="coerce").to_numpy(),
                    index=pd.MultiIndex.from_arrays([trx.analog_id, trx.period.map(qnum)]))
    last_final = max(qnum(p) for p in quarterly.period.unique()) - PROVISIONAL
    rows = []
    for a, (lq, _) in launch.iterrows():
        start = qnum(lq)
        end = min(PEAK_WINDOW, last_final - start)
        if end < 0:
            continue
        s = trx.loc[a] if a in trx.index.get_level_values(0) else pd.Series(dtype=float)
        s = s.reindex(range(start, start + end + 1)).fillna(0)
        rows.append((a, s.max(), int(s.to_numpy().argmax()), end, end == PEAK_WINDOW))
    out = pd.DataFrame(rows, columns=["analog_id", "peak_trx", "peak_q", "peak_window_end", "peak_confirmed"])
    return out.set_index("analog_id")


def build(quarterly, launch, history, peak):
    # pivot, not pivot_table: keeps the blank trx_reported of fully suppressed quarters
    wide = quarterly[quarterly.metric.isin(TRX_COLS)].pivot(
        index=["analog_id", "period"], columns="metric", values="value")
    wide = wide.apply(pd.to_numeric, errors="coerce").reindex(columns=TRX_COLS)
    provisional = provisional_periods(quarterly)
    latest = max(qnum(p) for p in quarterly.period.unique())
    expansion = history[history.kind != "original"].groupby("analog_id").q_since_launch.min()

    frames = []
    for a, (lq, _) in launch.iterrows():
        start = qnum(lq)
        q = range(0, min(WINDOW, latest - start) + 1)
        periods = [qstr(start + i) for i in q]
        c = pd.DataFrame({"analog_id": a, "q_since_launch": list(q), "period": periods})
        rows = wide.loc[a] if a in wide.index.get_level_values(0) else pd.DataFrame(columns=TRX_COLS)
        c = c.join(rows, on="period")
        # no SDUD row for any NDC: no prescriptions paid or dispensed that quarter
        c["no_sdud_row"] = c.suppressed_rows.isna()
        c.loc[c.no_sdud_row, ["trx", "trx_low", "trx_high", "suppressed_rows", "imputed_share"]] = 0
        c.loc[c.no_sdud_row, "trx_reported"] = 0
        c["provisional"] = c.period.isin(provisional)
        pk = peak.peak_trx.get(a, pd.NA)
        c["share_of_peak"] = (c.trx / pk).round(4) if pd.notna(pk) and pk > 0 else pd.NA
        first_exp = expansion.get(a, pd.NA)
        c["label_expansion_flag"] = (c.q_since_launch >= max(first_exp, 0)) if pd.notna(first_exp) else False
        frames.append(c)
    out = pd.concat(frames, ignore_index=True)
    for col in ["trx", "trx_low", "trx_high", "trx_reported", "suppressed_rows"]:
        out[col] = out[col].astype("Int64")
    cols = ["analog_id", "q_since_launch", "period", *TRX_COLS, "no_sdud_row", "provisional", "share_of_peak",
            "label_expansion_flag"]
    return out[cols]
