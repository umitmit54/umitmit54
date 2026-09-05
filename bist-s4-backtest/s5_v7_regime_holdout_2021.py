from __future__ import annotations
from pathlib import Path
import time
import numpy as np
import pandas as pd
import borsapy as bp
from s5_v5_valueflow_2022 import universe,fetch_stock,sl,features,session,kap_window,tickers,event_kind_and_direction,wret,pr,pct

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output_s5v7_regime_2021'; OUT.mkdir(exist_ok=True)

def fetch_index(a,b):
    try:
        d=bp.Index('XU100').history(start=a,end=b)
        if d is None or len(d)==0:return pd.DataFrame()
        x=d.copy(); x.columns=[str(c).strip().lower().replace(' ','_') for c in x.columns]
        if 'adj_close' in x.columns and 'close' not in x.columns:x=x.rename(columns={'adj_close':'close'})
        if not isinstance(x.index,pd.DatetimeIndex):x.index=pd.to_datetime(x.index)
        return x.sort_index()
    except:return pd.DataFrame()

def bench_regime(bench,ws):
    b=sl(bench,ws-pd.Timedelta(days=45),ws-pd.Timedelta(days=1))
    if len(b)<21 or 'close' not in b:return 'neutral',np.nan,np.nan
    c=b.close.astype(float); b5=pct(c.iloc[-6],c.iloc[-1]); b20=pct(c.iloc[-21],c.iloc[-1])
    weak=(np.isfinite(b20) and b20<0) or (np.isfinite(b5) and b5<-0.01)
    return ('weak' if weak else 'strong'),b5,b20

def safe_kap(a,b,max_tries=4):
    for attempt in range(max_tries):
        try:return kap_window(session(),a,b),True
        except Exception as e:
            print('WARN KAP',a.date(),b.date(),'attempt',attempt+1,repr(e)); time.sleep(.8*(attempt+1))
    return [],False

def main():
    weeks=pd.DataFrame({'week_start':pd.date_range('2021-01-04','2021-12-27',freq='W-MON')})
    weeks['week_end']=weeks.week_start+pd.Timedelta(days=4); weeks=weeks[weeks.week_end<=pd.Timestamp('2021-12-31')].copy(); weeks['test_id']=['H21-%02d'%(i+1) for i in range(len(weeks))]
    u=universe(); print('Universe',len(u)); cache={}
    for i,s in enumerate(u,1):
        cache[s]=fetch_stock(s,'2020-11-01','2022-01-07')
        if i%10==0:print('prices',i,'/',len(u))
    bench=fetch_index('2020-11-01','2022-01-07'); summaries=[]; ranks=[]
    for _,w in weeks.iterrows():
        ws,we=w.week_start,w.week_end; cutoff=ws+pd.Timedelta(hours=9,minutes=55); regime,b5,b20=bench_regime(bench,ws)
        evscore={s:0.0 for s in u}; flowdir={s:0.0 for s in u}; evcount={s:0 for s in u}
        disclosures,kap_ok=safe_kap(ws-pd.Timedelta(days=7),ws)
        for d in disclosures:
            try:dt=pd.to_datetime(d.get('publishDate'),format='%d.%m.%Y %H:%M:%S')
            except:continue
            if dt>=cutoff:continue
            es,fd,_=event_kind_and_direction(d,(cutoff-dt).total_seconds()/86400)
            for s in [x for x in tickers(d) if x in evscore]:evscore[s]+=es; flowdir[s]+=fd; evcount[s]+=1
        rows=[]
        for s in u:
            if s not in cache:continue
            f=features(sl(cache[s],ws-pd.Timedelta(days=50),ws-pd.Timedelta(days=1)))
            if f is None:continue
            gate=(f['tech']>=4) or (f['reversal']==1) or (evscore[s]>=2) or (flowdir[s]>0.5) or (f['value1']>=1.8) or (f['value5']>=1.4)
            rows.append({'symbol':s,**f,'event':evscore[s],'flowdir':flowdir[s],'event_count':evcount[s],'gate':gate,'week_return':wret(sl(cache[s],ws,we))})
        r=pd.DataFrame(rows)
        if r.empty:continue
        cand=r[r.gate].copy()
        if len(cand)<20:cand=r.nlargest(min(30,len(r)),'tech').copy()
        for col in ['ret20','ret3','event','event_count','flow10','value1','tech','flowdir']:
            med=cand[col].median() if cand[col].notna().any() else 0
            cand[col+'_p']=pr(cand[col].replace([np.inf,-np.inf],np.nan).fillna(med))
        # EXACT frozen V7 weights from 2019-2020 historical test. No retuning on 2021.
        if regime=='weak':
            cand['v7_score']=0.18*cand.ret20_p+0.08*cand.ret3_p+0.22*cand.event_p+0.10*cand.event_count_p+0.18*cand.flow10_p+0.12*cand.value1_p+0.08*cand.tech_p+0.04*cand.flowdir_p
        else:
            cand['v7_score']=0.36*cand.ret20_p+0.18*cand.ret3_p+0.08*cand.event_p+0.04*cand.event_count_p+0.10*cand.flow10_p+0.10*cand.value1_p+0.12*cand.tech_p+0.02*cand.flowdir_p
        cand=cand.sort_values(['v7_score','ret20','event','flow10'],ascending=False).reset_index(drop=True); cand['rank']=np.arange(1,len(cand)+1)
        ranks.append(cand.assign(test_id=w.test_id,regime=regime,kap_ok=kap_ok))
        leader=r.loc[r.week_return.idxmax()] if r.week_return.notna().any() else None
        if leader is None:continue
        m=cand[cand.symbol==leader.symbol]; lr=int(m.iloc[0]['rank']) if len(m) else None; top5=cand.head(5)
        pret=float(top5.week_return.dropna().mean()) if top5.week_return.notna().any() else np.nan; bret=wret(sl(bench,ws,we))
        summaries.append({'test_id':w.test_id,'week_start':ws.strftime('%Y-%m-%d'),'regime':regime,'kap_ok':kap_ok,'pre_bist5':b5,'pre_bist20':b20,'leader':leader.symbol,'leader_return':leader.week_return,'leader_in_pool':bool(len(m)),'leader_rank':lr,'leader_top5':bool(lr and lr<=5),'leader_top10':bool(lr and lr<=10),'leader_top20':bool(lr and lr<=20),'top5':';'.join(top5.symbol.tolist()),'portfolio_return':pret,'bist100_return':bret,'alpha':pret-bret if np.isfinite(pret) and np.isfinite(bret) else np.nan})
        print(w.test_id,regime,'leader',leader.symbol,'rank',lr,'alpha',pret-bret if np.isfinite(pret) and np.isfinite(bret) else np.nan); time.sleep(.1)
    sm=pd.DataFrame(summaries); rk=pd.concat(ranks,ignore_index=True) if ranks else pd.DataFrame(); sm.to_csv(OUT/'summary.csv',index=False); rk.to_csv(OUT/'rankings.csv',index=False)
    rows=[]
    for rg in ['ALL','strong','weak']:
        z=sm if rg=='ALL' else sm[sm.regime==rg]
        rows.append({'segment':rg,'weeks':len(z),'pool_recall':z.leader_in_pool.mean() if len(z) else np.nan,'top5':z.leader_top5.mean() if len(z) else np.nan,'top10':z.leader_top10.mean() if len(z) else np.nan,'median_rank':z.leader_rank.dropna().median() if len(z) else np.nan,'avg_portfolio_return':z.portfolio_return.mean() if len(z) else np.nan,'avg_bist100_return':z.bist100_return.mean() if len(z) else np.nan,'avg_alpha':z.alpha.mean() if len(z) else np.nan,'beat_rate':(z.alpha>0).mean() if len(z) else np.nan,'kap_success_rate':z.kap_ok.mean() if len(z) else np.nan})
    pd.DataFrame(rows).to_csv(OUT/'stats.csv',index=False)
if __name__=='__main__':main()
