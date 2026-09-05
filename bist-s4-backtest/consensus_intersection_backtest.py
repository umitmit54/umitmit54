from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import borsapy as bp

from backtest import fetch_stock, fetch_index, slice_dates, score_row, week_return
from s5_v7_regime_holdout_2021 import bench_regime
from s5_v5_valueflow_2022 import features, pr

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output_consensus_intersection'; OUT.mkdir(exist_ok=True)

CASES=[
 {'id':'BT-2022NOV','entry':'2022-11-01','end':'2022-11-04','S1':'BIMAS;FROTO;TAVHL;AKBNK;KCHOL','S2':'THYAO;HEKTS;PGSUS;TUPRS;TCELL','S3':'AKBNK;GARAN;YKBNK;TOASO;TAVHL'},
 {'id':'BT-2023MAY','entry':'2023-05-02','end':'2023-05-05','S1':'TUPRS;TAVHL;FROTO;AKBNK;BIMAS','S2':'BIMAS;THYAO;MGROS;HEKTS;SAHOL','S3':'GARAN;AKBNK;FROTO;ARCLK;TOASO'},
 {'id':'BT-2024MAR','entry':'2024-03-01','end':'2024-03-07','S1':'TUPRS;MGROS;SAHOL;TCELL;TAVHL','S2':'GUBRF;TAVHL;ARCLK;MGROS;FROTO','S3':'AKBNK;YKBNK;GARAN;ISCTR;TAVHL'},
 {'id':'BT-2025MAR','entry':'2025-03-03','end':'2025-03-07','S1':'TCELL;THYAO;MGROS;ASELS;BIMAS','S2':'ISCTR;ASELS;AKBNK;GARAN;YKBNK','S3':'ASELS;FROTO;GARAN;ISCTR;TAVHL'},
 {'id':'HIST-2026JUL','entry':'2026-07-31','end':'2026-08-07','S1':'TUPRS;ASTOR;ASELS;KCHOL;TCELL','S2':'EFOR;ODINE;BIMAS;EUPWR;AKSEN','S3':'TAVHL;GARAN;ANHYT;AKGRT;BIGCH'},
 {'id':'CHK-002-2026AUG','entry':'2026-08-31','end':'2026-09-04','S1':'TUPRS;AKBNK;ASELS;ASTOR;TEHOL','S2':'TKFEN;BRSAN;GUBRF;TRALT;ALTNY','S3':'BIMAS;TAVHL;MPARK;KCHOL;CCOLA'},
]

def universe():
    return sorted({str(s).strip().upper() for s in bp.Index('XU100').component_symbols if s})

def s5_rank(rows: pd.DataFrame, regime:str):
    cand=rows.copy()
    gate=(cand.tech>=4)|(cand.reversal==1)|(cand.value1>=1.8)|(cand.value5>=1.4)
    if gate.sum()>=20: cand=cand[gate].copy()
    for col in ['ret20','ret3','flow10','value1','tech']:
        med=cand[col].median() if cand[col].notna().any() else 0
        cand[col+'_p']=pr(cand[col].replace([np.inf,-np.inf],np.nan).fillna(med))
    if regime=='weak':
        w={'ret20_p':.18,'ret3_p':.08,'flow10_p':.18,'value1_p':.12,'tech_p':.08}
    else:
        w={'ret20_p':.36,'ret3_p':.18,'flow10_p':.10,'value1_p':.10,'tech_p':.12}
    den=sum(w.values()); cand['s5_score']=sum((wt/den)*cand[col] for col,wt in w.items())
    return cand.sort_values(['s5_score','ret20','flow10'],ascending=False).reset_index(drop=True)

def main():
    u=universe(); syms=set(u)
    for c in CASES:
        for k in ['S1','S2','S3']: syms.update(c[k].split(';'))
    start=(pd.Timestamp(min(c['entry'] for c in CASES))-pd.Timedelta(days=70)).strftime('%Y-%m-%d')
    end=(pd.Timestamp(max(c['end'] for c in CASES))+pd.Timedelta(days=3)).strftime('%Y-%m-%d')
    cache={}
    for i,s in enumerate(sorted(syms),1):
        cache[s]=fetch_stock(s,start,end)
        if i%10==0: print('prices',i,'/',len(syms))
    bench=fetch_index(start,end)
    details=[]; summaries=[]
    for c in CASES:
        ws=pd.Timestamp(c['entry']); we=pd.Timestamp(c['end']); pre=ws-pd.Timedelta(days=50)
        bpre=slice_dates(bench,pre,ws-pd.Timedelta(days=1)); regime,_,_=bench_regime(bench,ws)
        rows=[]
        for s in u:
            h=slice_dates(cache.get(s,pd.DataFrame()),pre,ws-pd.Timedelta(days=1))
            sc=score_row(h,bpre,0)
            f=features(h)
            if sc is None or f is None: continue
            wk=slice_dates(cache.get(s,pd.DataFrame()),ws,we)
            rows.append({'symbol':s,'week_return':week_return(wk),**sc,**f})
        r=pd.DataFrame(rows)
        if r.empty: continue
        s4=r.sort_values(['score','ret5','vol1_ratio'],ascending=False).reset_index(drop=True); s4['s4_rank']=np.arange(1,len(s4)+1)
        s5=s5_rank(r,regime); s5['s5_rank']=np.arange(1,len(s5)+1)
        s4top=set(s4.head(10).symbol); s5top=set(s5.head(10).symbol)
        confirm=s4top|s5top
        both=s4top&s5top
        bret=week_return(slice_dates(bench,ws,we))
        for strat in ['S1','S2','S3']:
            basket=c[strat].split(';')
            brow=r[r.symbol.isin(basket)]
            base=float(brow.week_return.dropna().mean()) if brow.week_return.notna().any() else np.nan
            inter5=[x for x in basket if x in s5top]
            inter4=[x for x in basket if x in s4top]
            inter_any=[x for x in basket if x in confirm]
            inter_both=[x for x in basket if x in both]
            def ret(xs):
                z=r[r.symbol.isin(xs)].week_return.dropna(); return float(z.mean()) if len(z) else np.nan
            summaries.append({'case':c['id'],'entry':c['entry'],'regime':regime,'strategy':strat,'basket':';'.join(basket),'base_return':base,'bist100_return':bret,'base_alpha':base-bret if np.isfinite(base) and np.isfinite(bret) else np.nan,
                              's5_overlap':';'.join(inter5),'s5_n':len(inter5),'s5_overlap_return':ret(inter5),'s4_overlap':';'.join(inter4),'s4_n':len(inter4),'s4_overlap_return':ret(inter4),
                              'any_overlap':';'.join(inter_any),'any_n':len(inter_any),'any_overlap_return':ret(inter_any),'both_overlap':';'.join(inter_both),'both_n':len(inter_both),'both_overlap_return':ret(inter_both)})
        details.append(s4[['symbol','s4_rank','score','week_return']].merge(s5[['symbol','s5_rank','s5_score']],on='symbol',how='outer').assign(case=c['id'],entry=c['entry'],regime=regime))
        print(c['id'],regime,'S4',list(s4.head(10).symbol),'S5',list(s5.head(10).symbol))
    sm=pd.DataFrame(summaries); sm.to_csv(OUT/'summary.csv',index=False)
    if details: pd.concat(details,ignore_index=True).to_csv(OUT/'rankings.csv',index=False)
    stats=[]
    for filt,col,ncol in [('S5_TOP10','s5_overlap_return','s5_n'),('S4_TOP10','s4_overlap_return','s4_n'),('S4_OR_S5','any_overlap_return','any_n'),('S4_AND_S5','both_overlap_return','both_n')]:
        z=sm[sm[ncol]>0].copy()
        stats.append({'filter':filt,'rows_with_overlap':len(z),'cases_with_overlap':z['case'].nunique() if len(z) else 0,'avg_overlap_n':z[ncol].mean() if len(z) else np.nan,'avg_filtered_return':z[col].mean() if len(z) else np.nan,'avg_original_return_same_rows':z.base_return.mean() if len(z) else np.nan,'avg_bist100_same_rows':z.bist100_return.mean() if len(z) else np.nan,'uplift_vs_original':(z[col]-z.base_return).mean() if len(z) else np.nan,'alpha_vs_bist100':(z[col]-z.bist100_return).mean() if len(z) else np.nan,'win_vs_original':(z[col]>z.base_return).mean() if len(z) else np.nan})
    pd.DataFrame(stats).to_csv(OUT/'stats.csv',index=False)

    # A+ de-duplicated by case+symbol: candidate must belong to at least one original strategy basket AND be Top10 in both S4 and S5.
    allr=pd.concat(details,ignore_index=True) if details else pd.DataFrame()
    aplus=[]
    if not allr.empty:
        for c in CASES:
            rr=allr[allr['case']==c['id']].copy()
            if rr.empty: continue
            both_syms=set(rr[(rr.s4_rank<=10)&(rr.s5_rank<=10)].symbol)
            orig=set()
            memberships={}
            for strat in ['S1','S2','S3']:
                for s in c[strat].split(';'):
                    orig.add(s); memberships.setdefault(s,[]).append(strat)
            picks=sorted(both_syms & orig)
            for s in picks:
                row=rr[rr.symbol==s].iloc[0]
                aplus.append({'case':c['id'],'entry':c['entry'],'symbol':s,'strategies':'+'.join(memberships.get(s,[])),'s4_rank':int(row.s4_rank),'s5_rank':int(row.s5_rank),'week_return':float(row.week_return) if np.isfinite(row.week_return) else np.nan})
    ap=pd.DataFrame(aplus); ap.to_csv(OUT/'aplus_candidates.csv',index=False)
    if len(ap):
        case_stats=ap.groupby('case').agg(aplus_n=('symbol','nunique'),aplus_return=('week_return','mean')).reset_index()
    else:
        case_stats=pd.DataFrame(columns=['case','aplus_n','aplus_return'])
    case_stats.to_csv(OUT/'aplus_case_stats.csv',index=False)

if __name__=='__main__': main()
