from __future__ import annotations

import math
from pathlib import Path

import borsapy as bp
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
CFG = ROOT / "config"
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)


def norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x.columns = [str(c).strip().lower().replace(" ", "_") for c in x.columns]
    aliases = {
        "adj_close": "close",
        "datetime": "date",
    }
    x = x.rename(columns={k: v for k, v in aliases.items() if k in x.columns})
    return x


def safe_history(symbol: str, start: str, end: str) -> pd.DataFrame:
    try:
        df = bp.Ticker(symbol).history(start=start, end=end)
        if df is None or len(df) == 0:
            return pd.DataFrame()
        df = norm_cols(df)
        if not isinstance(df.index, pd.DatetimeIndex):
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                pass
        return df.sort_index()
    except Exception as exc:
        print(f"WARN {symbol}: {exc}")
        return pd.DataFrame()


def index_history(start: str, end: str) -> pd.DataFrame:
    df = bp.Index("XU100").history(start=start, end=end)
    return norm_cols(df).sort_index()


def get_current_universe() -> list[str]:
    idx = bp.Index("XU100")
    syms = list(idx.component_symbols)
    return sorted({str(s).strip().upper() for s in syms if s})


def pct(a: float, b: float) -> float:
    if a is None or b is None or not np.isfinite(a) or not np.isfinite(b) or a == 0:
        return np.nan
    return b / a - 1.0


def score_row(hist: pd.DataFrame, bench: pd.DataFrame, catalyst_bonus: float) -> dict | None:
    need = {"open", "high", "low", "close", "volume"}
    if hist.empty or not need.issubset(hist.columns) or len(hist) < 21:
        return None
    h = hist.iloc[-21:].copy()
    c = h["close"].astype(float)
    v = h["volume"].astype(float)

    ret20 = pct(c.iloc[0], c.iloc[-1])
    ret5 = pct(c.iloc[-6], c.iloc[-1]) if len(c) >= 6 else np.nan
    ret3 = pct(c.iloc[-4], c.iloc[-1]) if len(c) >= 4 else np.nan
    high20 = float(h["high"].astype(float).max())
    dist_high = c.iloc[-1] / high20 - 1.0 if high20 else np.nan
    vol20 = float(v.iloc[:-1].mean()) if len(v) > 1 else np.nan
    vol1_ratio = float(v.iloc[-1] / vol20) if vol20 and np.isfinite(vol20) else np.nan
    vol5_ratio = float(v.iloc[-5:].mean() / vol20) if vol20 and np.isfinite(vol20) else np.nan

    bench_ret5 = np.nan
    if not bench.empty and "close" in bench.columns and len(bench) >= 6:
        bc = bench["close"].astype(float)
        bench_ret5 = pct(bc.iloc[-6], bc.iloc[-1])
    rel5 = ret5 - bench_ret5 if np.isfinite(ret5) and np.isfinite(bench_ret5) else np.nan

    score = 0.0
    score += 2 if np.isfinite(ret20) and ret20 > 0 else 0
    score += 2 if np.isfinite(ret5) and ret5 > 0 else 0
    score += 1 if np.isfinite(ret3) and ret3 > 0 else 0
    score += 2 if np.isfinite(dist_high) and dist_high >= -0.05 else 0
    score += 2 if np.isfinite(vol1_ratio) and vol1_ratio >= 1.20 else 0
    score += 1 if np.isfinite(vol5_ratio) and vol5_ratio >= 1.20 else 0
    score += 1 if np.isfinite(rel5) and rel5 > 0 else 0
    score += 1 if np.isfinite(ret5) and 0.01 <= ret5 <= 0.15 else 0
    score += float(catalyst_bonus or 0)

    return {
        "score": score,
        "ret20": ret20,
        "ret5": ret5,
        "ret3": ret3,
        "dist_high20": dist_high,
        "vol1_ratio": vol1_ratio,
        "vol5_ratio": vol5_ratio,
        "rel5": rel5,
        "catalyst_bonus": catalyst_bonus,
    }


def week_return(df: pd.DataFrame) -> float:
    if df.empty or not {"open", "close"}.issubset(df.columns):
        return np.nan
    return pct(float(df["open"].iloc[0]), float(df["close"].iloc[-1]))


def main() -> None:
    weeks = pd.read_csv(CFG / "weeks.csv", dtype=str)
    cats = pd.read_csv(CFG / "catalysts.csv", dtype={"week_start": str, "symbol": str, "bonus": float, "note": str})
    cats["symbol"] = cats["symbol"].str.upper()

    universe = get_current_universe()
    print(f"Current XU100 proxy universe: {len(universe)} symbols")

    all_rankings: list[pd.DataFrame] = []
    summaries: list[dict] = []

    for _, w in weeks.iterrows():
        ws = pd.Timestamp(w.week_start)
        we = pd.Timestamp(w.week_end)
        pre_start = (ws - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
        pre_end = (ws - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        eval_end = (we + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        bench_pre = index_history(pre_start, pre_end)
        bench_week = index_history(ws.strftime("%Y-%m-%d"), eval_end)
        bench_ret = week_return(bench_week)

        csub = cats[cats.week_start == w.week_start]
        bonus_map = dict(zip(csub.symbol, csub.bonus))

        rows = []
        for symbol in universe:
            hist = safe_history(symbol, pre_start, pre_end)
            sc = score_row(hist, bench_pre, bonus_map.get(symbol, 0.0))
            if sc is None:
                continue
            wk = safe_history(symbol, ws.strftime("%Y-%m-%d"), eval_end)
            r = week_return(wk)
            rows.append({"test_id": w.test_id, "week_start": w.week_start, "week_end": w.week_end, "symbol": symbol, **sc, "week_return": r})

        rank = pd.DataFrame(rows)
        if rank.empty:
            print(f"No data for {w.test_id}")
            continue
        rank = rank.sort_values(["score", "ret5", "vol1_ratio"], ascending=[False, False, False], na_position="last").reset_index(drop=True)
        rank["rank"] = np.arange(1, len(rank) + 1)
        all_rankings.append(rank)

        top5 = rank.head(5)
        valid = top5.week_return.dropna()
        s4_ret = float(valid.mean()) if len(valid) else np.nan
        leader = rank.loc[rank.week_return.idxmax()] if rank.week_return.notna().any() else None
        leader_symbol = str(leader.symbol) if leader is not None else ""
        leader_return = float(leader.week_return) if leader is not None else np.nan
        leader_rank = int(leader["rank"]) if leader is not None else None

        summaries.append({
            "test_id": w.test_id,
            "week_start": w.week_start,
            "week_end": w.week_end,
            "universe_mode": "CURRENT_XU100_PROXY",
            "universe_n": len(rank),
            "top5": ";".join(top5.symbol.tolist()),
            "s4_top5_equal_weight_return": s4_ret,
            "bist100_return": bench_ret,
            "alpha_vs_bist100": s4_ret - bench_ret if np.isfinite(s4_ret) and np.isfinite(bench_ret) else np.nan,
            "actual_leader_in_proxy_universe": leader_symbol,
            "actual_leader_return": leader_return,
            "leader_s4_rank": leader_rank,
            "leader_captured_top5": bool(leader_rank is not None and leader_rank <= 5),
        })
        print(w.test_id, top5.symbol.tolist(), s4_ret, bench_ret, leader_symbol, leader_rank)

    summary = pd.DataFrame(summaries)
    rankings = pd.concat(all_rankings, ignore_index=True) if all_rankings else pd.DataFrame()
    summary.to_csv(OUT / "summary.csv", index=False)
    rankings.to_csv(OUT / "rankings.csv", index=False)

    if not summary.empty:
        stats = pd.DataFrame([{
            "weeks": len(summary),
            "leader_top5_capture_rate": summary.leader_captured_top5.mean(),
            "weeks_beating_bist100": int((summary.alpha_vs_bist100 > 0).sum()),
            "avg_s4_return": summary.s4_top5_equal_weight_return.mean(),
            "avg_bist100_return": summary.bist100_return.mean(),
            "avg_alpha": summary.alpha_vs_bist100.mean(),
            "method_note": "OHLCV is ex-ante; universe uses CURRENT XU100 as historical proxy unless archived constituent snapshots are supplied. Catalyst bonuses only include verified pre-week events in config/catalysts.csv.",
        }])
        stats.to_csv(OUT / "stats.csv", index=False)


if __name__ == "__main__":
    main()
