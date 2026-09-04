from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import borsapy as bp

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

HOLDOUT_START = "2024-01-01"
HOLDOUT_END = "2024-12-31"


def norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x.columns = [str(c).strip().lower().replace(" ", "_") for c in x.columns]
    if "adj_close" in x.columns and "close" not in x.columns:
        x = x.rename(columns={"adj_close": "close"})
    if not isinstance(x.index, pd.DatetimeIndex):
        x.index = pd.to_datetime(x.index)
    return x.sort_index()


def fetch_stock(symbol: str, start: str, end: str) -> pd.DataFrame:
    try:
        df = bp.Ticker(symbol).history(start=start, end=end)
        return pd.DataFrame() if df is None or len(df) == 0 else norm_cols(df)
    except Exception:
        return pd.DataFrame()


def fetch_index(start: str, end: str) -> pd.DataFrame:
    try:
        df = bp.Index("XU100").history(start=start, end=end)
        return pd.DataFrame() if df is None or len(df) == 0 else norm_cols(df)
    except Exception:
        return pd.DataFrame()


def pct(a, b):
    if a is None or b is None or a == 0 or not np.isfinite(a) or not np.isfinite(b):
        return np.nan
    return b / a - 1.0


def slice_dates(df, start, end):
    if df.empty:
        return pd.DataFrame()
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    idx = df.index
    if idx.tz is not None:
        s = s.tz_localize(idx.tz)
        e = e.tz_localize(idx.tz)
    return df.loc[(idx >= s) & (idx <= e)].copy()


def feat(hist: pd.DataFrame, bench: pd.DataFrame):
    need = {"open", "high", "low", "close", "volume"}
    if hist.empty or len(hist) < 25 or not need.issubset(hist.columns):
        return None
    h = hist.iloc[-25:]
    c, v = h.close.astype(float), h.volume.astype(float)
    r3 = pct(c.iloc[-4], c.iloc[-1])
    r5 = pct(c.iloc[-6], c.iloc[-1])
    r10 = pct(c.iloc[-11], c.iloc[-1])
    r20 = pct(c.iloc[-21], c.iloc[-1])
    high20 = float(h.high.iloc[-20:].astype(float).max())
    dist20 = c.iloc[-1] / high20 - 1 if high20 else np.nan
    vol_base = float(v.iloc[-21:-1].mean())
    vol1 = float(v.iloc[-1] / vol_base) if vol_base else np.nan
    vol5 = float(v.iloc[-5:].mean() / vol_base) if vol_base else np.nan
    b5 = np.nan
    if not bench.empty and len(bench) >= 6 and "close" in bench:
        bc = bench.close.astype(float)
        b5 = pct(bc.iloc[-6], bc.iloc[-1])
    rel5 = r5 - b5 if np.isfinite(r5) and np.isfinite(b5) else np.nan
    rng5 = (h.high.iloc[-5:].astype(float).max() - h.low.iloc[-5:].astype(float).min()) / c.iloc[-1]
    return dict(ret3=r3, ret5=r5, ret10=r10, ret20=r20, dist_high20=dist20, vol1_ratio=vol1, vol5_ratio=vol5, rel5=rel5, range5=rng5)


def week_ret(df):
    if df.empty or not {"open", "close"}.issubset(df.columns):
        return np.nan
    return pct(float(df.open.iloc[0]), float(df.close.iloc[-1]))


def percentile_rank(s: pd.Series, higher_better=True):
    return s.rank(pct=True, ascending=not higher_better, method="average")


def main():
    universe = sorted({str(s).upper() for s in bp.Index("XU100").component_symbols})
    global_start = "2023-10-01"
    global_end = "2025-01-10"
    cache = {s: fetch_stock(s, global_start, global_end) for s in universe}
    bench_all = fetch_index(global_start, global_end)

    mondays = pd.date_range(HOLDOUT_START, HOLDOUT_END, freq="W-MON")
    summaries, rankings = [], []

    for ws in mondays:
        we = ws + pd.Timedelta(days=4)
        if we > pd.Timestamp(HOLDOUT_END):
            break
        pre_start = ws - pd.Timedelta(days=45)
        pre_end = ws - pd.Timedelta(days=1)
        bpre = slice_dates(bench_all, pre_start, pre_end)
        rows = []
        for sym in universe:
            h = slice_dates(cache.get(sym, pd.DataFrame()), pre_start, pre_end)
            f = feat(h, bpre)
            if not f:
                continue
            wk = slice_dates(cache[sym], ws, we)
            rows.append({"symbol": sym, **f, "week_return": week_ret(wk)})
        df = pd.DataFrame(rows)
        if len(df) < 50:
            continue

        # percentile features, 1.0 = strongest/more extreme in desired direction
        for col in ["ret3", "ret5", "ret10", "ret20", "vol1_ratio", "vol5_ratio", "rel5"]:
            df[col+"_p"] = percentile_rank(df[col], True)
        df["near_high_p"] = percentile_rank(-df["dist_high20"].abs(), True)
        df["tight_p"] = percentile_rank(-df["range5"], True)
        df["reversal_p"] = percentile_rank(-df["ret5"], True)

        # DNA channels learned from 2025-2026 descriptive study.
        # L1 ignition: short momentum + volume + relative strength
        df["L1"] = 0.35*df.ret5_p + 0.20*df.ret3_p + 0.20*df.vol1_ratio_p + 0.15*df.rel5_p + 0.10*df.near_high_p
        # L2 coil: persistent trend + tight range + near high, quiet-ish volume accepted
        df["L2"] = 0.40*df.ret20_p + 0.20*df.ret10_p + 0.20*df.tight_p + 0.15*df.near_high_p + 0.05*(1-df.vol1_ratio_p)
        # L3 reversal proxy (no flow/event yet): punished short-term but not catastrophic long trend, volume awakening
        df["L3"] = 0.35*df.reversal_p + 0.20*df.vol1_ratio_p + 0.15*df.vol5_ratio_p + 0.15*(1-df.ret20_p) + 0.15*df.rel5_p

        # Candidate union: top 12 in each channel, then second-stage diversity score.
        idx = set(df.nlargest(12, "L1").index) | set(df.nlargest(12, "L2").index) | set(df.nlargest(12, "L3").index)
        cand = df.loc[sorted(idx)].copy()
        cand["best_channel"] = cand[["L1", "L2", "L3"]].idxmax(axis=1)
        cand["best_score"] = cand[["L1", "L2", "L3"]].max(axis=1)
        cand["second_score"] = cand[["L1", "L2", "L3"]].apply(lambda r: sorted(r, reverse=True)[1], axis=1)
        cand["final_score"] = cand.best_score + 0.25*cand.second_score
        cand = cand.sort_values("final_score", ascending=False)
        top5 = cand.head(5)

        leader = df.loc[df.week_return.idxmax()] if df.week_return.notna().any() else None
        leader_sym = leader.symbol if leader is not None else ""
        leader_ret = float(leader.week_return) if leader is not None else np.nan
        leader_in_union = bool(leader_sym in set(cand.symbol))
        leader_final_rank = None
        if leader_in_union:
            leader_final_rank = int(np.where(cand.symbol.values == leader_sym)[0][0] + 1)
        top5_capture = bool(leader_final_rank is not None and leader_final_rank <= 5)
        top10_capture = bool(leader_final_rank is not None and leader_final_rank <= 10)
        top20_capture = bool(leader_final_rank is not None and leader_final_rank <= 20)

        sret = float(top5.week_return.dropna().mean()) if top5.week_return.notna().any() else np.nan
        bw = slice_dates(bench_all, ws, we)
        bret = week_ret(bw)
        summaries.append({
            "week_start": ws.date().isoformat(), "week_end": we.date().isoformat(),
            "candidate_n": len(cand), "top5": ";".join(top5.symbol.tolist()),
            "model_return": sret, "bist100_return": bret, "alpha": sret-bret if np.isfinite(sret) and np.isfinite(bret) else np.nan,
            "leader": leader_sym, "leader_return": leader_ret, "leader_in_union": leader_in_union,
            "leader_final_rank": leader_final_rank, "top5_capture": top5_capture, "top10_capture": top10_capture, "top20_capture": top20_capture,
        })
        cand.insert(0, "week_start", ws.date().isoformat())
        rankings.append(cand)

    sm = pd.DataFrame(summaries)
    rk = pd.concat(rankings, ignore_index=True) if rankings else pd.DataFrame()
    sm.to_csv(OUT / "holdout_summary.csv", index=False)
    rk.to_csv(OUT / "holdout_rankings.csv", index=False)
    if not sm.empty:
        stats = pd.DataFrame([{
            "weeks": len(sm),
            "leader_union_recall": sm.leader_in_union.mean(),
            "leader_top5_capture": sm.top5_capture.mean(),
            "leader_top10_capture": sm.top10_capture.mean(),
            "leader_top20_capture": sm.top20_capture.mean(),
            "avg_model_return": sm.model_return.mean(),
            "avg_bist100_return": sm.bist100_return.mean(),
            "avg_alpha": sm.alpha.mean(),
            "weeks_beating_bist100": int((sm.alpha > 0).sum()),
            "note": "Holdout 2024. Current XU100 proxy universe; OHLCV only. L3 has no event/flow data yet."
        }])
        stats.to_csv(OUT / "holdout_stats.csv", index=False)

if __name__ == "__main__":
    main()
