from __future__ import annotations
from pathlib import Path
import time
import numpy as np
import pandas as pd
import borsapy as bp
from s5_v5_valueflow_2022 import universe,fetch_stock,sl,features,session,kap_window,tickers,event_kind_and_direction,wret,pr

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output_s5v6_2021'; OUT.mkdir(exist_ok=True)

def fetch_index(a,b):
    try:
        d=bp.Index('XU100').history(start=a,end=b)
        if d is None or len(d)==0:return pd.DataFrame()
        x=d.copy(); x.columns=[str(c).strip().lower().replace(' ','_') for c in x.columns]
        if 'adj_close' in x.columns and 'close' not in x.columns:x=x.rename(columns={'adj_close':'close'})
        if not isinstance(x.index,pd.DatetimeIndex):x.index=pd.to_datetime(x.index)
        return x.sort_index()
    except:return pd.DataFrame()

def main():
    weeks=pd.DataFrame({'week_start':pd.date_range('2021-01-04','2021-12-27',freq='W-MON')})
    weeks['week_end']=weeks.week_start+pd.Timedelta(days=4); weeks=weeks[weeks.week_end<=pd.Timestamp('2021-12-31')].copy(); weeks['test_id']=['H21-%02d'%(i+1) for i in range(len(weeks))]
    u=universe(); print('Universe',len(u)); cache={}
    for i,s in enumerate(u,1):
        cache[s]=fetch_stock(s,'2020-11-01','2022-01-07')
        if i%10==0:print('prices',i,'/',len(u))
    bench=fetch_index('2020-11-01','2022-01-07')
    ks=session(); summaries=[]; ranks=[]
    for _,w in weeks.iterrows():
        ws,we=w.week_start,w.week_end; cutoff=ws+pd.Timedelta(hours=9,minutes=55)
        evscore={s:0.0 for s in u}; flowdir={s:0.0 for s in u}; evcount={s:0 for s in u}
        for d in kap_window(ks,ws-pd.Timedelta(days=7),ws):
            try:dt=pd.to_datetime(d.get('publishDate'),format='%d.%m.%Y %H:%M:%S')
            except:continue
            if dt>=cutoff:continue
            es,fd,_=event_kind_and_direction(d,(cutoff-dt).total_seconds()/86400)
            for s in [x for x in tickers(d) if x in evscore]:evscore[s]+=es; flowdir[s]+=fd; evcount[s]+=1
        rows=[]
        for s in u:
            f=features(sl(cache[s],ws-pd.Timedelta(days=50),ws-pd.Timedelta(days=1)))
            if f is None:continue
            gate=(f['tech']>=4) or (f['reversal']==1) or (evscore[s]>=2) or (flowdir[s]>0.5) or (f['value1']>=1.8) or (f['value5']>=1.4)
            rows.append({'symbol':s,**f,'event':evscore[s],'flowdir':flowdir[s],'event_count':evcount[s],'gate':gate,'week_return':wret(sl(cache[s],ws,we))})
        r=pd.DataFrame(rows)
        if r.empty:continue
        cand=r[r.gate].copy()
        if len(cand)<20:cand=r.nlargest(30,'tech').copy()
        # V6 frozen from 2022 diagnostics. Persistent trend and meaningful event density dominate.
        for col in ['ret20','ret3','event','event_count','flow10','value1','tech','flowdir']:
            med=cand[col].median() if cand[col].notna().any() else 0
            cand[col+'_p']=pr(cand[col].replace([np.inf,-np.inf],np.nan).fillna(med))
        cand['v6_score']=(0.30*cand.ret20_p+0.12*cand.ret3_p+0.18*cand.event_p+0.10*cand.event_count_p+
                          0.12*cand.flow10_p+0.08*cand.value1_p+0.08*cand.tech_p+0.02*cand.flowdir_p)
        cand=cand.sort_values(['v6_score','event','ret20','flow10'],ascending=False).reset_index(drop=True); cand['rank']=np.arange(1,len(cand)+1); ranks.append(cand.assign(test_id=w.test_id))
        leader=r.loc[r.week_return.idxmax()] if r.week_return.notna().any() else None
        if leader is None:continue
        m=cand[cand.symbol==leader.symbol]; lr=int(m.iloc[0]['rank']) if len(m) else None; top5=cand.head(5)
        pret=float(top5.week_return.dropna().mean()) if top5.week_return.notna().any() else np.nan
        bret=wret(sl(bench,ws,we))
        summaries.append({'test_id':w.test_id,'week_start':ws.strftime('%Y-%m-%d'),'leader':leader.symbol,'leader_return':leader.week_return,'leader_in_pool':bool(len(m)),'leader_rank':lr,'leader_top5':bool(lr and lr<=5),'leader_top10':bool(lr and lr<=10),'leader_top20':bool(lr and lr<=20),'top5':';'.join(top5.symbol.tolist()),'portfolio_return':pret,'bist100_return':bret,'alpha':pret-bret if np.isfinite(pret) and np.isfinite(bret) else np.nan})
        print(w.test_id,'leader',leader.symbol,'rank',lr); time.sleep(.2)
    sm=pd.DataFrame(summaries); rk=pd.concat(ranks,ignore_index=True) if ranks else pd.DataFrame(); sm.to_csv(OUT/'summary.csv',index=False); rk.to_csv(OUT/'rankings.csv',index=False)
    pd.DataFrame([{'weeks':len(sm),'pool_recall':sm.leader_in_pool.mean(),'top5':sm.leader_top5.mean(),'top10':sm.leader_top10.mean(),'top20':sm.leader_top20.mean(),'median_rank':sm.leader_rank.dropna().median(),'avg_portfolio_return':sm.portfolio_return.mean(),'avg_bist100_return':sm.bist100_return.mean(),'avg_alpha':sm.alpha.mean(),'weeks_beating_bist100':int((sm.alpha>0).sum()),'note':'2021 untouched holdout. V6 weights frozen from 2022 diagnostics; V5 candidate gate retained. CURRENT_XU100_PROXY.'}]).to_csv(OUT/'stats.csv',index=False)
if __name__=='__main__':main()
