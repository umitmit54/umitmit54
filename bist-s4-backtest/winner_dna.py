from __future__ import annotations

from pathlib import Path
import borsapy as bp
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output_winner_dna"
OUT.mkdir(exist_ok=True)


def norm_cols(df):
    x = df.copy()
    x.columns = [str(c).strip().lower().replace(' ', '_') for c in x.columns]
    if 'adj_close' in x.columns and 'close' not in x.columns:
        x = x.rename(columns={'adj_close':'close'})
    if not isinstance(x.index, pd.DatetimeIndex):
        x.index = pd.to_datetime(x.index)
    return x.sort_index()


def fetch_stock(sym, start, end):
    try:
        df = bp.Ticker(sym).history(start=start, end=end)
        return pd.DataFrame() if df is None or len(df)==0 else norm_cols(df)
    except Exception as e:
        print('WARN', sym, e); return pd.DataFrame()


def fetch_index(start, end):
    try:
        df = bp.Index('XU100').history(start=start, end=end)
        return pd.DataFrame() if df is None or len(df)==0 else norm_cols(df)
    except Exception as e:
        print('WARN XU100', e); return pd.DataFrame()


def current_universe():
    return sorted({str(s).strip().upper() for s in bp.Index('XU100').component_symbols if s})


def sl(df, a, b):
    if df.empty: return pd.DataFrame()
    a,b = pd.Timestamp(a),pd.Timestamp(b)
    if df.index.tz is not None:
        a,b = a.tz_localize(df.index.tz), b.tz_localize(df.index.tz)
    return df.loc[(df.index>=a)&(df.index<=b)].copy()


def pct(a,b):
    try:
        return b/a-1 if np.isfinite(a) and np.isfinite(b) and a != 0 else np.nan
    except: return np.nan


def feats(hist, bench):
    need={'open','high','low','close','volume'}
    if hist.empty or not need.issubset(hist.columns) or len(hist)<21: return None
    h=hist.iloc[-21:]; c=h.close.astype(float); v=h.volume.astype(float)
    ret20=pct(c.iloc[0],c.iloc[-1]); ret10=pct(c.iloc[-11],c.iloc[-1]); ret5=pct(c.iloc[-6],c.iloc[-1]); ret3=pct(c.iloc[-4],c.iloc[-1]); ret1=pct(c.iloc[-2],c.iloc[-1])
    hi20=float(h.high.astype(float).max()); dist_high=c.iloc[-1]/hi20-1 if hi20 else np.nan
    base=float(v.iloc[:-1].mean()); v1=float(v.iloc[-1]/base) if base else np.nan; v5=float(v.iloc[-5:].mean()/base) if base else np.nan
    bret5=np.nan
    if not bench.empty and 'close' in bench.columns and len(bench)>=6:
        bc=bench.close.astype(float); bret5=pct(bc.iloc[-6],bc.iloc[-1])
    rel5=ret5-bret5 if np.isfinite(ret5) and np.isfinite(bret5) else np.nan
    # compression + range expansion potential
    r5=((h.high.astype(float)-h.low.astype(float))/h.close.astype(float)).iloc[-5:].mean()
    r20=((h.high.astype(float)-h.low.astype(float))/h.close.astype(float)).iloc[:-5].mean()
    compression=float(r5/r20) if r20 and np.isfinite(r20) else np.nan
    return dict(ret1=ret1,ret3=ret3,ret5=ret5,ret10=ret10,ret20=ret20,rel5=rel5,dist_high20=dist_high,vol1_ratio=v1,vol5_ratio=v5,compression_5v20=compression)


def weekret(df):
    if df.empty or not {'open','close'}.issubset(df.columns): return np.nan
    return pct(float(df.open.iloc[0]),float(df.close.iloc[-1]))


def main():
    universe=current_universe(); print('universe',len(universe))
    start='2024-11-01'; end='2026-09-05'
    cache={}
    for i,s in enumerate(universe,1):
        cache[s]=fetch_stock(s,start,end)
        if i%10==0: print('downloaded',i)
    bench=fetch_index(start,end)

    mondays=pd.date_range('2025-01-06','2026-08-31',freq='W-MON')
    rows=[]; leader_rows=[]
    for ws in mondays:
        we=ws+pd.Timedelta(days=4); pre0=ws-pd.Timedelta(days=45); pre1=ws-pd.Timedelta(days=1)
        bpw=sl(bench,pre0,pre1)
        wr=[]
        for s in universe:
            hist=sl(cache[s],pre0,pre1); f=feats(hist,bpw)
            if f is None: continue
            w=sl(cache[s],ws,we); r=weekret(w)
            wr.append(dict(week_start=ws.date(),symbol=s,week_return=r,**f))
        d=pd.DataFrame(wr)
        if d.empty or not d.week_return.notna().any(): continue
        # percentile ranks where larger is more leader-like; dist_high closer to 0 is larger already
        metric_cols=['ret1','ret3','ret5','ret10','ret20','rel5','dist_high20','vol1_ratio','vol5_ratio']
        for m in metric_cols:
            d[m+'_pct']=d[m].rank(pct=True,method='average')
        # compression: lower can be interesting; add inverse percentile
        d['compression_inv_pct']=1-d['compression_5v20'].rank(pct=True,method='average')
        leader=d.loc[d.week_return.idxmax()].copy()
        leader['universe_n']=len(d)
        leader_rows.append(leader)
        rows.append(d)
        print(ws.date(), leader.symbol, round(float(leader.week_return)*100,2), 'ret5pct', round(float(leader.ret5_pct),2), 'v1pct', round(float(leader.vol1_ratio_pct),2))

    leaders=pd.DataFrame(leader_rows)
    full=pd.concat(rows,ignore_index=True) if rows else pd.DataFrame()
    leaders.to_csv(OUT/'leaders.csv',index=False)
    full.to_csv(OUT/'all_weekly_features.csv',index=False)

    metrics=['ret1_pct','ret3_pct','ret5_pct','ret10_pct','ret20_pct','rel5_pct','dist_high20_pct','vol1_ratio_pct','vol5_ratio_pct','compression_inv_pct']
    stats=[]
    for m in metrics:
        x=leaders[m].dropna()
        stats.append(dict(metric=m,n=len(x),mean=float(x.mean()),median=float(x.median()),p25=float(x.quantile(.25)),p75=float(x.quantile(.75)),share_top10=float((x>=.90).mean()),share_top20=float((x>=.80).mean()),share_top30=float((x>=.70).mean())))
    pd.DataFrame(stats).to_csv(OUT/'dna_stats.csv',index=False)

    # threshold combos for leader recall; no tuning on returns, descriptive only
    combos=[]
    tests={
      'MOM5_TOP20': leaders.ret5_pct>=.80,
      'VOL1_TOP20': leaders.vol1_ratio_pct>=.80,
      'REL5_TOP20': leaders.rel5_pct>=.80,
      'NEAR_HIGH_TOP20': leaders.dist_high20_pct>=.80,
      'MOM_OR_VOL_TOP20': (leaders.ret5_pct>=.80)|(leaders.vol1_ratio_pct>=.80),
      'MOM_OR_REL_OR_VOL_TOP20': (leaders.ret5_pct>=.80)|(leaders.rel5_pct>=.80)|(leaders.vol1_ratio_pct>=.80),
      'ANY_CORE_TOP30': (leaders.ret5_pct>=.70)|(leaders.rel5_pct>=.70)|(leaders.vol1_ratio_pct>=.70)|(leaders.dist_high20_pct>=.70),
    }
    for name,mask in tests.items(): combos.append({'rule':name,'leader_recall':float(mask.mean()),'leaders_captured':int(mask.sum()),'weeks':len(leaders)})
    pd.DataFrame(combos).to_csv(OUT/'pattern_recall.csv',index=False)

if __name__=='__main__': main()
