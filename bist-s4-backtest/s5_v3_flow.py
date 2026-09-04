from __future__ import annotations

from pathlib import Path
import re, time
import borsapy as bp
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output_s5v3'; OUT.mkdir(exist_ok=True)
KAP_LIST='https://www.kap.org.tr/tr/api/disclosure/members/byCriteria'
KAP_PAGE='https://www.kap.org.tr/tr/bildirim-sorgu'
UA='Mozilla/5.0 (compatible; bist-s5v3-research/1.0)'

def norm(df):
    x=df.copy(); x.columns=[str(c).strip().lower().replace(' ','_') for c in x.columns]
    if 'adj_close' in x.columns and 'close' not in x.columns: x=x.rename(columns={'adj_close':'close'})
    if not isinstance(x.index,pd.DatetimeIndex):
        try:x.index=pd.to_datetime(x.index)
        except:pass
    return x.sort_index()

def fetch_stock(s,a,b):
    try:
        d=bp.Ticker(s).history(start=a,end=b)
        return pd.DataFrame() if d is None or len(d)==0 else norm(d)
    except Exception as e:
        print('WARN',s,e); return pd.DataFrame()

def universe(): return sorted({str(x).strip().upper() for x in bp.Index('XU100').component_symbols if x})
def pct(a,b):
    try:return float(b)/float(a)-1 if float(a) else np.nan
    except:return np.nan

def sl(df,a,b):
    if df.empty or not isinstance(df.index,pd.DatetimeIndex):return pd.DataFrame()
    a,b=pd.Timestamp(a),pd.Timestamp(b); idx=df.index
    if idx.tz is not None:a,b=a.tz_localize(idx.tz),b.tz_localize(idx.tz)
    return df[(idx>=a)&(idx<=b)].copy()

def session():
    s=requests.Session(); s.headers.update({'User-Agent':UA,'Referer':KAP_PAGE,'Accept':'application/json, text/plain, */*'})
    try:s.get(KAP_PAGE,timeout=20)
    except:pass
    return s

def kap_window(s,a,b):
    r=s.post(KAP_LIST,json={'fromDate':a.strftime('%Y-%m-%d'),'toDate':b.strftime('%Y-%m-%d'),'mkkMemberOidList':[],'subjectList':[]},timeout=30)
    r.raise_for_status(); d=r.json(); return d if isinstance(d,list) else []

def tickers(d):
    raw=' '.join(str(d.get(k) or '') for k in ('stockCodes','relatedStocks'))
    return sorted(set(re.findall(r'\b[A-ZÇĞİÖŞÜ0-9]{4,6}\b',raw.upper())))

def txt(d): return ' '.join(str(d.get(k) or '') for k in ('subject','summary','kapTitle')).lower()

def num_strength(t):
    vals=[]
    for m in re.finditer(r'(?<!\w)(\d{1,3}(?:[\.\s]\d{3})+|\d+)(?:[,.](\d+))?',t):
        raw=m.group(0).replace(' ','').replace('.','').replace(',','.')
        try: vals.append(float(raw))
        except: pass
    if not vals:return 0.0
    mx=max(vals)
    if mx>=1_000_000_000:return 2.0
    if mx>=100_000_000:return 1.5
    if mx>=10_000_000:return 1.0
    if mx>=1_000_000:return 0.5
    return 0.0

def directional_event(d,age):
    t=txt(d); score=0.0; flow=0.0; kind='OTHER'
    low=['sorumluluk beyanı','faaliyet raporu','finansal rapor','kurumsal yönetim','sürdürülebilirlik raporu']
    if any(x in t for x in low): return 0.0,0.0,'ROUTINE'
    # Insider/shareholder flow direction
    buy=bool(re.search(r'\b(alım|alış|satın al|pay alım|geri alım)\b',t))
    sell=bool(re.search(r'\b(satım|satış|elden çıkar|pay satım)\b',t))
    if buy and not sell: flow+=4.0; kind='FLOW_BUY'
    elif sell and not buy: flow-=3.0; kind='FLOW_SELL'
    elif buy and sell: flow+=0.5; kind='FLOW_MIXED'
    if re.search(r'yeni iş|iş ilişkisi|sözleşme|sipariş|ihale|proje',t): score+=4; kind='CONTRACT'
    if re.search(r'yatırım|kapasite art|tesis|üretim|ruhsat|lisans',t): score+=3; kind='INVESTMENT'
    if re.search(r'ortaklık|iş birliği|işbirliği|stratejik',t): score+=2.5; kind='PARTNERSHIP'
    if re.search(r'endeks|msci|ftse',t): score+=3.5; kind='INDEX'
    if re.search(r'bedelsiz|sermaye artırımı',t): score+=1.5; kind='CAPITAL'
    if re.search(r'finansal duran varlık edinimi|devral|satın alma',t): score+=2; kind='ACQUISITION'
    if re.search(r'iflas|konkordato|tasfiye',t): score-=6; kind='DISTRESS'
    if re.search(r'ceza|yaptırım|faaliyet.*durdur',t): score-=3; kind='NEGATIVE'
    # size proxy from explicitly reported figures; capped
    size=min(num_strength(t),2.0)
    if score>0: score+=size
    if flow>0: flow+=0.5*size
    decay=max(0.25,1.0-0.10*max(age,0))
    return score*decay,flow*decay,kind

def features(h):
    if h.empty or len(h)<21 or not {'close','high','low','volume'}.issubset(h.columns): return None
    q=h.iloc[-21:]; c=q.close.astype(float); v=q.volume.astype(float)
    r3=pct(c.iloc[-4],c.iloc[-1]); r5=pct(c.iloc[-6],c.iloc[-1]); r20=pct(c.iloc[0],c.iloc[-1])
    vm=float(v.iloc[:-1].mean()); vol1=float(v.iloc[-1]/vm) if vm else np.nan
    hi=float(q.high.astype(float).max()); dh=float(c.iloc[-1]/hi-1) if hi else np.nan
    # technical prefilter score only
    tech=0
    tech += 2 if np.isfinite(r20) and r20>0 else 0
    tech += 2 if np.isfinite(r5) and r5>0 else 0
    tech += 2 if np.isfinite(vol1) and vol1>=1.2 else 0
    tech += 1 if np.isfinite(dh) and dh>=-0.08 else 0
    # reversal doorway
    rev=1 if np.isfinite(r5) and -0.12<=r5<=-0.02 and np.isfinite(vol1) and vol1>=1.1 else 0
    return dict(ret3=r3,ret5=r5,ret20=r20,vol1=vol1,dist_high=dh,tech=tech,reversal=rev)

def wret(d):
    if d.empty or not {'open','close'}.issubset(d.columns):return np.nan
    return pct(d.open.iloc[0],d.close.iloc[-1])

def main():
    weeks=pd.DataFrame({'week_start':pd.date_range('2024-01-01','2024-12-23',freq='W-MON')})
    weeks['week_end']=weeks.week_start+pd.Timedelta(days=4); weeks['test_id']=['H24-%02d'%(i+1) for i in range(len(weeks))]
    u=universe(); print('Universe',len(u))
    gs='2023-11-01'; ge='2024-12-31'; cache={}
    for i,s in enumerate(u,1):
        cache[s]=fetch_stock(s,gs,ge)
        if i%10==0: print('prices',i,'/',len(u))
    ks=session(); summaries=[]; ranks=[]
    for _,w in weeks.iterrows():
        ws,we=w.week_start,w.week_end; cutoff=ws+pd.Timedelta(hours=9,minutes=55)
        evs=kap_window(ks,ws-pd.Timedelta(days=7),ws)
        evscore={s:0.0 for s in u}; flowscore={s:0.0 for s in u}; evcount={s:0 for s in u}
        for d in evs:
            try:dt=pd.to_datetime(d.get('publishDate'),format='%d.%m.%Y %H:%M:%S')
            except:continue
            if dt>=cutoff:continue
            es,fs,k=directional_event(d,(cutoff-dt).total_seconds()/86400)
            for s in [x for x in tickers(d) if x in evscore]:
                evscore[s]+=es; flowscore[s]+=fs; evcount[s]+=1
        rows=[]
        for s in u:
            f=features(sl(cache[s],ws-pd.Timedelta(days=50),ws-pd.Timedelta(days=1)))
            if f is None:continue
            # candidate gate: technical strength OR reversal OR meaningful event/flow
            gate=(f['tech']>=4) or (f['reversal']==1) or (evscore[s]>=2) or (flowscore[s]>=2)
            # rank primarily by directional event/flow, tech only tie-break/support
            score=3.0*flowscore[s]+2.2*evscore[s]+0.45*f['tech']+0.5*f['reversal']
            wk=wret(sl(cache[s],ws,we))
            rows.append({'test_id':w.test_id,'symbol':s,**f,'event':evscore[s],'flow':flowscore[s],'event_count':evcount[s],'gate':gate,'score':score,'week_return':wk})
        r=pd.DataFrame(rows)
        if r.empty:continue
        cand=r[r.gate].copy()
        # fallback if narrow
        if len(cand)<20: cand=r.nlargest(30,'tech').copy()
        cand=cand.sort_values(['score','flow','event','tech','ret5'],ascending=[False,False,False,False,False]).reset_index(drop=True); cand['rank']=np.arange(1,len(cand)+1)
        ranks.append(cand)
        top5=cand.head(5); leader=r.loc[r.week_return.idxmax()] if r.week_return.notna().any() else None
        if leader is None: continue
        lm=cand[cand.symbol==leader.symbol]; lr=int(lm.iloc[0]['rank']) if len(lm) else None
        pret=float(top5.week_return.dropna().mean()) if top5.week_return.notna().any() else np.nan
        summaries.append({'test_id':w.test_id,'week_start':ws.strftime('%Y-%m-%d'),'top5':';'.join(top5.symbol),'portfolio_return':pret,'leader':leader.symbol,'leader_return':leader.week_return,'leader_rank':lr,'leader_in_pool':bool(len(lm)),'leader_top5':bool(lr and lr<=5),'leader_top10':bool(lr and lr<=10),'leader_top20':bool(lr and lr<=20),'leader_event':leader.event,'leader_flow':leader.flow})
        print(w.test_id,'leader',leader.symbol,'rank',lr,'top5',top5.symbol.tolist())
        time.sleep(.25)
    sm=pd.DataFrame(summaries); rk=pd.concat(ranks,ignore_index=True)
    sm.to_csv(OUT/'summary.csv',index=False); rk.to_csv(OUT/'rankings.csv',index=False)
    pd.DataFrame([{'weeks':len(sm),'pool_recall':sm.leader_in_pool.mean(),'top5':sm.leader_top5.mean(),'top10':sm.leader_top10.mean(),'top20':sm.leader_top20.mean(),'median_rank':sm.leader_rank.dropna().median(),'avg_portfolio_return':sm.portfolio_return.mean(),'leader_with_positive_event':(sm.leader_event>0).mean(),'leader_with_positive_flow':(sm.leader_flow>0).mean(),'note':'2024 holdout; CURRENT_XU100_PROXY; KAP text-direction parser + OHLCV candidate gate. No attachment/takas data yet.'}]).to_csv(OUT/'stats.csv',index=False)

if __name__=='__main__': main()
