from __future__ import annotations

from pathlib import Path
import re
import time

import borsapy as bp
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
CFG = ROOT / "config"
OUT = ROOT / "output_s5v2"
OUT.mkdir(exist_ok=True)

KAP_LIST = "https://www.kap.org.tr/tr/api/disclosure/members/byCriteria"
KAP_PAGE = "https://www.kap.org.tr/tr/bildirim-sorgu"
UA = "Mozilla/5.0 (compatible; bist-s5v2-research/1.0)"

# Generic, ex-ante event relevance. These weights are fixed before reading target-week returns.
POSITIVE_EVENT_PATTERNS = [
    (r"yeni iş|iş ilişkisi|sözleşme|sipariş|ihale|proje", 4.0),
    (r"yatırım|kapasite art|tesis|üretim|ruhsat|lisans", 3.0),
    (r"ortaklık|iş birliği|işbirliği|stratejik", 2.5),
    (r"geri alım|payların geri alınması", 2.5),
    (r"sermaye artırımı|bedelsiz", 2.0),
    (r"finansal duran varlık edinimi|satın alma|devral", 2.0),
    (r"endeks|msci|ftse", 3.0),
    (r"kar payı|temettü", 1.0),
]
NEGATIVE_EVENT_PATTERNS = [
    (r"iflas|konkordato|tasfiye", -5.0),
    (r"dava|ceza|yaptırım|faaliyet.*durdur", -2.5),
    (r"sermaye azaltımı", -2.0),
]
LOW_SIGNAL_PATTERNS = [
    r"sorumluluk beyanı", r"faaliyet raporu", r"finansal rapor", r"kurumsal yönetim", r"sürdürülebilirlik raporu"
]


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
        print(f"WARN stock {symbol}: {exc}")
        return pd.DataFrame()


def current_universe() -> list[str]:
    return sorted({str(x).strip().upper() for x in bp.Index("XU100").component_symbols if x})


def pct(a, b):
    try:
        a = float(a); b = float(b)
        return b / a - 1.0 if a else np.nan
    except Exception:
        return np.nan


def slice_dates(df: pd.DataFrame, start, end) -> pd.DataFrame:
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return pd.DataFrame()
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    idx = df.index
    if idx.tz is not None:
        s, e = s.tz_localize(idx.tz), e.tz_localize(idx.tz)
    return df.loc[(idx >= s) & (idx <= e)].copy()


def kap_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": KAP_PAGE, "Accept": "application/json, text/plain, */*"})
    try:
        s.get(KAP_PAGE, timeout=20)
    except Exception:
        pass
    return s


def fetch_kap_window(s: requests.Session, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    payload = {
        "fromDate": start.strftime("%Y-%m-%d"),
        "toDate": end.strftime("%Y-%m-%d"),
        "mkkMemberOidList": [],
        "subjectList": [],
    }
    r = s.post(KAP_LIST, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected KAP response: {type(data)}")
    return data


def tickers_from_disclosure(d: dict) -> list[str]:
    raw = " ".join(str(d.get(k) or "") for k in ("stockCodes", "relatedStocks"))
    toks = re.findall(r"\b[A-ZÇĞİÖŞÜ0-9]{4,6}\b", raw.upper())
    return sorted(set(toks))


def event_score(d: dict, age_days: float) -> float:
    text = " ".join(str(d.get(k) or "") for k in ("subject", "summary", "kapTitle")).lower()
    if any(re.search(p, text) for p in LOW_SIGNAL_PATTERNS):
        base = 0.0
    else:
        base = 0.5  # any non-routine disclosure has weak information value
    for p, w in POSITIVE_EVENT_PATTERNS:
        if re.search(p, text):
            base += w
    for p, w in NEGATIVE_EVENT_PATTERNS:
        if re.search(p, text):
            base += w
    if str(d.get("disclosureClass") or "").upper() == "DKB":
        # insider/shareholder flow disclosure: important, but direction unknown without attachment parsing
        base += 1.0
    if d.get("isLate"):
        base *= 0.6
    decay = max(0.25, 1.0 - 0.12 * max(age_days, 0))
    return base * decay


def technical_confirmation(hist: pd.DataFrame) -> dict:
    if hist.empty or len(hist) < 21 or not {"close", "high", "volume"}.issubset(hist.columns):
        return {"ret3": np.nan, "ret5": np.nan, "vol1": np.nan, "dist_high": np.nan, "tech_confirm": 0.0}
    h = hist.iloc[-21:]
    c, v = h.close.astype(float), h.volume.astype(float)
    ret3 = pct(c.iloc[-4], c.iloc[-1])
    ret5 = pct(c.iloc[-6], c.iloc[-1])
    vol20 = float(v.iloc[:-1].mean())
    vol1 = float(v.iloc[-1] / vol20) if vol20 else np.nan
    high20 = float(h.high.astype(float).max())
    dist = float(c.iloc[-1] / high20 - 1.0) if high20 else np.nan
    # confirmation, not primary signal
    tc = 0.0
    tc += 1.5 if np.isfinite(ret3) and ret3 > 0 else 0
    tc += 1.0 if np.isfinite(ret5) and ret5 > 0 else 0
    tc += 1.5 if np.isfinite(vol1) and vol1 >= 1.35 else 0
    tc += 1.0 if np.isfinite(dist) and dist >= -0.05 else 0
    return {"ret3": ret3, "ret5": ret5, "vol1": vol1, "dist_high": dist, "tech_confirm": tc}


def week_return(df: pd.DataFrame) -> float:
    if df.empty or not {"open", "close"}.issubset(df.columns):
        return np.nan
    return pct(df.open.iloc[0], df.close.iloc[-1])


def main():
    weeks = pd.read_csv(CFG / "weeks.csv", dtype=str)
    universe = current_universe()
    print("Universe", len(universe))

    gstart = (pd.Timestamp(weeks.week_start.min()) - pd.Timedelta(days=70)).strftime("%Y-%m-%d")
    gend = (pd.Timestamp(weeks.week_end.max()) + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    cache = {}
    for i, sym in enumerate(universe, 1):
        cache[sym] = fetch_stock(sym, gstart, gend)
        if i % 10 == 0: print("prices", i, "/", len(universe))

    ks = kap_session()
    all_rows, summaries, events_dump = [], [], []

    for _, w in weeks.iterrows():
        ws, we = pd.Timestamp(w.week_start), pd.Timestamp(w.week_end)
        # Information cutoff = Monday 09:55 Europe/Istanbul. Pull preceding 7 calendar days + Monday.
        ev_start = ws - pd.Timedelta(days=7)
        ev_end = ws
        disclosures = fetch_kap_window(ks, ev_start, ev_end)
        cutoff = ws + pd.Timedelta(hours=9, minutes=55)
        scores = {s: 0.0 for s in universe}
        counts = {s: 0 for s in universe}
        strongest = {s: "" for s in universe}
        strongest_score = {s: -999.0 for s in universe}

        for d in disclosures:
            try:
                dt = pd.to_datetime(d.get("publishDate"), format="%d.%m.%Y %H:%M:%S")
            except Exception:
                continue
            if dt >= cutoff:
                continue
            age = (cutoff - dt).total_seconds() / 86400.0
            es = event_score(d, age)
            syms = [s for s in tickers_from_disclosure(d) if s in scores]
            for sym in syms:
                scores[sym] += es
                counts[sym] += 1
                if es > strongest_score[sym]:
                    strongest_score[sym] = es
                    strongest[sym] = f"{d.get('publishDate')} | {d.get('subject')} | {d.get('summary')}"
            if syms:
                events_dump.append({"test_id": w.test_id, "publishDate": d.get("publishDate"), "symbols": ";".join(syms), "event_score": es, "subject": d.get("subject"), "summary": d.get("summary"), "disclosureIndex": d.get("disclosureIndex")})

        rows = []
        for sym in universe:
            hist = slice_dates(cache[sym], ws - pd.Timedelta(days=50), ws - pd.Timedelta(days=1))
            tech = technical_confirmation(hist)
            # Event is primary. Multiple meaningful disclosures get a capped density bonus.
            density = min(max(counts[sym] - 1, 0) * 0.4, 1.6)
            s5v2 = scores[sym] * 2.0 + tech["tech_confirm"] + density
            wk = slice_dates(cache[sym], ws, we)
            rows.append({"test_id": w.test_id, "week_start": w.week_start, "week_end": w.week_end, "symbol": sym,
                         "event_score": scores[sym], "event_count": counts[sym], "density_bonus": density, **tech,
                         "s5v2_score": s5v2, "strongest_event": strongest[sym], "week_return": week_return(wk)})

        rank = pd.DataFrame(rows).sort_values(["s5v2_score", "event_score", "tech_confirm", "ret3"], ascending=[False, False, False, False], na_position="last").reset_index(drop=True)
        rank["rank"] = np.arange(1, len(rank)+1)
        all_rows.append(rank)
        top5 = rank.head(5)
        leader = rank.loc[rank.week_return.idxmax()] if rank.week_return.notna().any() else None
        lr = int(leader["rank"]) if leader is not None else None
        s5ret = float(top5.week_return.dropna().mean()) if top5.week_return.notna().any() else np.nan
        summaries.append({"test_id": w.test_id, "week_start": w.week_start, "week_end": w.week_end,
                          "top5": ";".join(top5.symbol.tolist()), "s5v2_return": s5ret,
                          "actual_leader": str(leader.symbol) if leader is not None else "",
                          "actual_leader_return": float(leader.week_return) if leader is not None else np.nan,
                          "leader_rank": lr, "leader_top5": bool(lr and lr <= 5), "leader_top10": bool(lr and lr <= 10),
                          "leader_top20": bool(lr and lr <= 20), "leader_event_score": float(leader.event_score) if leader is not None else np.nan,
                          "leader_event_count": int(leader.event_count) if leader is not None else 0,
                          "universe_mode": "CURRENT_XU100_PROXY", "method": "KAP_EVENT_PRIMARY+OHLCV_CONFIRM"})
        print(w.test_id, "top5", top5.symbol.tolist(), "leader", leader.symbol if leader is not None else None, "rank", lr)
        time.sleep(0.5)

    summary = pd.DataFrame(summaries)
    rankings = pd.concat(all_rows, ignore_index=True)
    summary.to_csv(OUT / "s5v2_summary.csv", index=False)
    rankings.to_csv(OUT / "s5v2_rankings.csv", index=False)
    pd.DataFrame(events_dump).to_csv(OUT / "s5v2_events.csv", index=False)
    stats = pd.DataFrame([{
        "weeks": len(summary),
        "leader_top5_capture": summary.leader_top5.mean(),
        "leader_top10_capture": summary.leader_top10.mean(),
        "leader_top20_capture": summary.leader_top20.mean(),
        "median_leader_rank": summary.leader_rank.median(),
        "avg_s5v2_return": summary.s5v2_return.mean(),
        "note": "Exploratory V2 on previously inspected 12 weeks. Event feed is ex-ante KAP API; current XU100 is still a historical-universe proxy. Flow direction from DKB attachments not yet parsed."
    }])
    stats.to_csv(OUT / "s5v2_stats.csv", index=False)

if __name__ == "__main__":
    main()
