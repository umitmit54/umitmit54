from __future__ import annotations

from pathlib import Path

import borsapy as bp
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
CFG = ROOT / "config"
OUT = ROOT / "output_s5"
OUT.mkdir(exist_ok=True)


def norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x.columns = [str(c).strip().lower().replace(" ", "_") for c in x.columns]
    if "adj_close" in x.columns and "close" not in x.columns:
        x = x.rename(columns={"adj_close": "close"})
    if not isinstance(x.index, pd.DatetimeIndex):
        try:
            x.index = pd.to_datetime(x.index)
        except Exception:
            pass
    return x.sort_index()


def fetch_stock(symbol: str, start: str, end: str) -> pd.DataFrame:
    try:
        df = bp.Ticker(symbol).history(start=start, end=end)
        return pd.DataFrame() if df is None or len(df) == 0 else norm_cols(df)
    except Exception as exc:
        print(f"WARN {symbol}: {exc}")
        return pd.DataFrame()


def fetch_index(start: str, end: str) -> pd.DataFrame:
    try:
        df = bp.Index("XU100").history(start=start, end=end)
        return pd.DataFrame() if df is None or len(df) == 0 else norm_cols(df)
    except Exception as exc:
        print(f"WARN XU100: {exc}")
        return pd.DataFrame()


def current_universe() -> list[str]:
    return sorted({str(s).strip().upper() for s in bp.Index("XU100").component_symbols if s})


def pct(a: float, b: float) -> float:
    if a is None or b is None or not np.isfinite(a) or not np.isfinite(b) or a == 0:
        return np.nan
    return b / a - 1.0


def slice_dates(df: pd.DataFrame, start, end) -> pd.DataFrame:
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return pd.DataFrame()
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    if df.index.tz is not None:
        s, e = s.tz_localize(df.index.tz), e.tz_localize(df.index.tz)
    return df.loc[(df.index >= s) & (df.index <= e)].copy()


def features(hist: pd.DataFrame, bench: pd.DataFrame, catalyst_bonus: float) -> dict | None:
    need = {"open", "high", "low", "close", "volume"}
    if hist.empty or not need.issubset(hist.columns) or len(hist) < 21:
        return None
    h = hist.iloc[-21:].copy()
    c = h.close.astype(float)
    o = h.open.astype(float)
    hi = h.high.astype(float)
    lo = h.low.astype(float)
    v = h.volume.astype(float)
    dr = c.pct_change()

    r1 = pct(c.iloc[-2], c.iloc[-1])
    r3 = pct(c.iloc[-4], c.iloc[-1])
    r5 = pct(c.iloc[-6], c.iloc[-1])
    r10 = pct(c.iloc[-11], c.iloc[-1])
    r20 = pct(c.iloc[0], c.iloc[-1])
    maxret5 = float(dr.iloc[-5:].max())
    posdays5 = int((dr.iloc[-5:] > 0).sum())

    high20 = float(hi.max())
    dist_high20 = c.iloc[-1] / high20 - 1.0 if high20 else np.nan
    vol20 = float(v.iloc[:-1].mean())
    vol1 = float(v.iloc[-1] / vol20) if vol20 else np.nan
    vol3 = float(v.iloc[-3:].mean() / vol20) if vol20 else np.nan
    vol5 = float(v.iloc[-5:].mean() / vol20) if vol20 else np.nan

    tr = pd.concat([(hi-lo), (hi-c.shift()).abs(), (lo-c.shift()).abs()], axis=1).max(axis=1)
    atr20 = float(tr.iloc[-20:].mean())
    range1_atr = float((hi.iloc[-1]-lo.iloc[-1]) / atr20) if atr20 else np.nan
    close_pos = float((c.iloc[-1]-lo.iloc[-1])/(hi.iloc[-1]-lo.iloc[-1])) if hi.iloc[-1] > lo.iloc[-1] else 0.5
    gap1 = pct(c.iloc[-2], o.iloc[-1])

    br3 = br5 = np.nan
    if not bench.empty and "close" in bench.columns:
        bc = bench.close.astype(float)
        if len(bc) >= 6:
            br3 = pct(bc.iloc[-4], bc.iloc[-1])
            br5 = pct(bc.iloc[-6], bc.iloc[-1])
    rel3 = r3 - br3 if np.isfinite(r3) and np.isfinite(br3) else np.nan
    rel5 = r5 - br5 if np.isfinite(r5) and np.isfinite(br5) else np.nan

    accel = r3 - 0.3 * r10 if np.isfinite(r3) and np.isfinite(r10) else np.nan
    flush5 = -r5 if np.isfinite(r5) and r5 < 0 else 0.0
    reversal = (1.0 if np.isfinite(r1) and r1 > 0 else 0.0) + (1.0 if np.isfinite(vol1) and vol1 > 1.2 else 0.0)

    return dict(r1=r1,r3=r3,r5=r5,r10=r10,r20=r20,maxret5=maxret5,posdays5=posdays5,
                dist_high20=dist_high20,vol1=vol1,vol3=vol3,vol5=vol5,range1_atr=range1_atr,
                close_pos=close_pos,gap1=gap1,rel3=rel3,rel5=rel5,accel=accel,flush5=flush5,
                reversal=reversal,catalyst_bonus=float(catalyst_bonus or 0.0))


def week_return(df: pd.DataFrame) -> float:
    if df.empty or not {"open", "close"}.issubset(df.columns):
        return np.nan
    return pct(float(df.open.iloc[0]), float(df.close.iloc[-1]))


def percentile_score(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    cols = ["r1","r3","r5","r10","r20","maxret5","dist_high20","vol1","vol3","vol5",
            "range1_atr","close_pos","gap1","rel3","rel5","accel","flush5","catalyst_bonus"]
    for col in cols:
        x[col+"_p"] = x[col].rank(pct=True, method="average")

    # Lane A: breakout / continuation pressure
    x["lane_breakout"] = (
        2.5*x.r3_p + 2.0*x.rel3_p + 2.0*x.vol1_p + 1.5*x.vol3_p +
        1.5*x.dist_high20_p + 1.0*x.close_pos_p + 1.0*x.maxret5_p + 2.0*x.catalyst_bonus_p
    )
    # Lane B: fresh acceleration; rewards a fast move even if 20d trend is not yet strong
    x["lane_accel"] = (
        3.0*x.accel_p + 2.5*x.r1_p + 2.0*x.rel3_p + 2.0*x.vol1_p +
        1.0*x.range1_atr_p + 1.0*x.close_pos_p + 2.0*x.catalyst_bonus_p
    )
    # Lane C: failed-breakdown / reversal. A negative 5d tape is allowed if the last day turns with volume.
    rev_gate = ((x.r5 < 0) & (x.r1 > 0)).astype(float)
    x["lane_reversal"] = (
        2.5*x.flush5_p + 2.5*x.r1_p + 2.0*x.vol1_p + 1.5*x.range1_atr_p +
        1.0*x.close_pos_p + 2.0*x.catalyst_bonus_p + 2.0*rev_gate
    )
    x["s5_score"] = x[["lane_breakout","lane_accel","lane_reversal"]].max(axis=1)
    x["s5_lane"] = x[["lane_breakout","lane_accel","lane_reversal"]].idxmax(axis=1).str.replace("lane_", "", regex=False)
    return x


def main() -> None:
    weeks = pd.read_csv(CFG / "weeks.csv", dtype=str)
    cats = pd.read_csv(CFG / "catalysts.csv", dtype={"week_start": str, "symbol": str, "bonus": float, "note": str})
    cats["symbol"] = cats.symbol.str.upper()
    universe = current_universe()

    global_start = (pd.Timestamp(weeks.week_start.min()) - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    global_end = (pd.Timestamp(weeks.week_end.max()) + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    print(f"S5 proxy universe={len(universe)}; download {global_start} -> {global_end}")

    cache = {}
    for i, symbol in enumerate(universe, 1):
        cache[symbol] = fetch_stock(symbol, global_start, global_end)
        if i % 10 == 0: print(f"Downloaded {i}/{len(universe)}")
    bench_all = fetch_index(global_start, global_end)

    all_rows, summaries = [], []
    for _, w in weeks.iterrows():
        ws, we = pd.Timestamp(w.week_start), pd.Timestamp(w.week_end)
        pre_start, pre_end = ws-pd.Timedelta(days=45), ws-pd.Timedelta(days=1)
        bench_pre = slice_dates(bench_all, pre_start, pre_end)
        bench_week = slice_dates(bench_all, ws, we)
        csub = cats[cats.week_start == w.week_start]
        bonus = dict(zip(csub.symbol, csub.bonus))

        rows=[]
        for symbol in universe:
            h = slice_dates(cache.get(symbol,pd.DataFrame()), pre_start, pre_end)
            f = features(h, bench_pre, bonus.get(symbol,0.0))
            if f is None: continue
            wk = slice_dates(cache[symbol], ws, we)
            rows.append({"test_id":w.test_id,"week_start":w.week_start,"week_end":w.week_end,"symbol":symbol,**f,"week_return":week_return(wk)})
        d = pd.DataFrame(rows)
        if d.empty: continue
        d = percentile_score(d)
        d = d.sort_values(["s5_score","r1","vol1"],ascending=[False,False,False],na_position="last").reset_index(drop=True)
        d["s5_rank"] = np.arange(1,len(d)+1)
        all_rows.append(d)

        top5=d.head(5)
        s5ret=float(top5.week_return.dropna().mean()) if top5.week_return.notna().any() else np.nan
        leader=d.loc[d.week_return.idxmax()] if d.week_return.notna().any() else None
        bret=week_return(bench_week)
        summaries.append({
            "test_id":w.test_id,"week_start":w.week_start,"week_end":w.week_end,
            "universe_mode":"CURRENT_XU100_PROXY","top5":";".join(top5.symbol),
            "s5_top5_return":s5ret,"bist100_return":bret,"alpha":s5ret-bret if np.isfinite(s5ret) and np.isfinite(bret) else np.nan,
            "actual_leader":str(leader.symbol) if leader is not None else "",
            "actual_leader_return":float(leader.week_return) if leader is not None else np.nan,
            "leader_s5_rank":int(leader.s5_rank) if leader is not None else None,
            "leader_captured_top5":bool(leader is not None and int(leader.s5_rank)<=5),
            "leader_lane":str(leader.s5_lane) if leader is not None else "",
        })
        print(w.test_id, top5.symbol.tolist(), s5ret, bret, summaries[-1]["actual_leader"], summaries[-1]["leader_s5_rank"])

    detail=pd.concat(all_rows,ignore_index=True) if all_rows else pd.DataFrame()
    summary=pd.DataFrame(summaries)
    detail.to_csv(OUT/"s5_rankings.csv",index=False)
    summary.to_csv(OUT/"s5_summary.csv",index=False)
    if not summary.empty:
        stats=pd.DataFrame([{
            "weeks":len(summary),
            "leader_top5_capture_rate":summary.leader_captured_top5.mean(),
            "leader_top10_capture_rate":(summary.leader_s5_rank<=10).mean(),
            "median_leader_rank":summary.leader_s5_rank.median(),
            "weeks_beating_bist100":int((summary.alpha>0).sum()),
            "avg_s5_return":summary.s5_top5_return.mean(),
            "avg_bist100_return":summary.bist100_return.mean(),
            "avg_alpha":summary.alpha.mean(),
            "method_note":"Exploratory S5 on same 12 proxy weeks already inspected during S4 development; not a pristine holdout. OHLCV is ex-ante, but universe remains CURRENT_XU100_PROXY and catalyst file is sparse."
        }])
        stats.to_csv(OUT/"s5_stats.csv",index=False)

if __name__ == "__main__":
    main()
