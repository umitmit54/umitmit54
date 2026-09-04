from __future__ import annotations
from pathlib import Path
import re,time
import borsapy as bp
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output_s5v4_2023'; OUT.mkdir(exist_ok=True)
KAP_LIST='https://www.kap.org.tr/tr/api/disclosure/members/byCriteria'
KAP_PAGE='https://www.kap.org.tr/tr/bildirim-sorgu'
UA='Mozilla/5.0 (compatible; bist-s5v4-research/1.0)'

def norm(df):
    x=df.copy(); x.columns=[str(c).strip().lower().replace(' ','_') for c in x.columns]
    if 'adj_close' in x.columns and 'close' not in x.columns:x=x.rename(columns={'adj_close':'close'})
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

def universe():return sorted({str(x).strip().upper() for x in bp.Index('XU100').component_symbols if x})
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
def txt(d):return ' '.join(str(d.get(k) or '') for k in ('subject','summary','kapTitle')).lower()

def num_strength(t):
    vals=[]
    for m in re.finditer(r'(?<!\w)(\d{1,3}(?:[\.\s]\d{3})+|\d+)(?:[,.](\d+))?',t):
        raw=m.group(0).replace(' ','').replace('.','').replace(',','.')
        try:vals.append(float(raw))
        except:pass
    if not vals:return 0.0
    mx=max(vals)
    if mx>=1_000_000_000:return 2.0
    if mx>=100_000_000:return 1.5
    if mx>=10_000_000:return 1.0
    if mx>=1_000_000:return 0.5
    return 0.0

def directional_event(d,age):
    t=txt(d); score=0.0; flow=0.0
    if any(x in t for x in ['sorumluluk beyanı','faaliyet raporu','finansal rapor','kurumsal yönetim','sürdürülebilirlik raporu']):return 0.0,0.0
    buy=bool(re.search(r'\b(alım|alış|satın al|pay alım|geri alım)\b',t)); sell=bool(re.search(r'\b(satım|satış|elden çıkar|pay satım)\b',t))
    if buy and not sell:flow+=4.0
    elif sell and not buy:flow-=3.0
    elif buy and sell:flow+=0.5
    if re.search(r'yeni iş|iş ilişkisi|sözleşme|sipariş|ihale|proje',t):score+=4
    if re.search(r'yatırım|kapasite art|tesis|üretim|ruhsat|lisans',t):score+=3
    if re.search(r'ortaklık|iş birliği|işbirliği|stratejik',t):score+=2.5
    if re.search(r'endeks|msci|ftse',t):score+=3.5
    if re.search(r'bedelsiz|sermaye artırımı',t):score+=1.5
    if re.search(r'finansal duran varlık edinimi|devral|satın alma',t):score+=2
    if re.search(r'iflas|konkordato|tasfiye',t):score-=6
    if re.search(r'ceza|yaptırım|faaliyet.*durdur',t):score-=3
    size=min(num_strength(t),2.0)
    if score>0:score+=size
    if flow>0:flow+=0.5*size
    decay=max(0.25,1.0-0.10*max(age,0))
    return score*decay,flow*decay

def features(h):
    if h.empty or len(h)<21 or not {'close','high','low','volume'}.issubset(h.columns):return None
    q=h.iloc[-21:]; c=q.close.astype(float); v=q.volume.astype(float)
    r3=pct(c.iloc[-4],c.iloc[-1]); r5=pct(c.iloc[-6],c.iloc[-1]); r20=pct(c.iloc[0],c.iloc[-1])
    vm=float(v.iloc[:-1].mean()); vol1=float(v.iloc[-1]/vm) if vm else np.nan
    hi=float(q.high.astype(float).max()); dh=float(c.iloc[-1]/hi-1) if hi else np.nan
    tech=0
    tech += 2 if np.isfinite(r20) and r20>0 else 0
    tech += 2 if np.isfinite(r5) and r5>0 else 0
    tech += 2 if np.isfinite(vol1) and vol1>=1.2 else 0
    tech += 1 if np.isfinite(dh) and dh>=-0.08 else 0
    rev=1 if np.isfinite(r5) and -0.12<=r5<=-0.02 and np.isfinite(vol1) and vol1>=1.1 else 0
    return dict(ret3=r3,ret5=r5,ret20=r20,vol1=vol1,dist_high=dh,tech=tech,reversal=rev)
def wret(d):
    if d.empty or not {'open','close'}.issubset(d.columns):return np.nan
    return pct(d.open.iloc[0],d.close.iloc[-1])
def pr(s):return s.rank(pct=True,method='average')

def main():
    weeks=pd.DataFrame({'week_start':pd.date_range('2023-01-02','2023-12-25',freq='W-MON')})
    weeks['week_end']=weeks.week_start+pd.Timedelta(days=4); weeks=weeks[weeks.week_end<=pd.Timestamp('2023-12-31')].copy(); weeks['test_id']=['H23-%02d'%(i+1) for i in range(len(weeks))]
    u=universe(); print('Universe',len(u)); cache={}
    for i,s in enumerate(u,1):
        cache[s]=fetch_stock(s,'2022-11-01','2024-01-05')
        if i%10==0:print('prices',i,'/',len(u))
    ks=session(); summaries=[]; ranks=[]
    for _,w in weeks.iterrows():
        ws,we=w.week_start,w.week_end; cutoff=ws+pd.Timedelta(hours=9,minutes=55)
        evscore={s:0.0 for s in u}; flowscore={s:0.0 for s in u}; evcount={s:0 for s in u}
        for d in kap_window(ks,ws-pd.Timedelta(days=7),ws):
            try:dt=pd.to_datetime(d.get('publishDate'),format='%d.%m.%Y %H:%M:%S')
            except:continue
            if dt>=cutoff:continue
            es,fs=directional_event(d,(cutoff-dt).total_seconds()/86400)
            for s in [x for x in tickers(d) if x in evscore]:evscore[s]+=es; flowscore[s]+=fs; evcount[s]+=1
        rows=[]
        for s in u:
            f=features(sl(cache[s],ws-pd.Timedelta(days=50),ws-pd.Timedelta(days=1)))
            if f is None:continue
            gate=(f['tech']>=4) or (f['reversal']==1) or (evscore[s]>=2) or (flowscore[s]>=2)
            rows.append({'symbol':s,**f,'event':evscore[s],'flow':flowscore[s],'event_count':evcount[s],'gate':gate,'week_return':wret(sl(cache[s],ws,we))})
        r=pd.DataFrame(rows)
        if r.empty:continue
        cand=r[r.gate].copy()
        if len(cand)<20:cand=r.nlargest(30,'tech').copy()
        # V4 frozen from 2024 diagnostics: persistent trend + short acceleration + directional flow;
        # generic event count is penalized as noise; being slightly away from recent high is not punished.
        cand['ret20_p']=pr(cand.ret20.fillna(cand.ret20.median()))
        cand['ret3_p']=pr(cand.ret3.fillna(cand.ret3.median()))
        cand['flow_p']=pr(cand.flow.fillna(0))
        cand['tech_p']=pr(cand.tech.fillna(0))
        cand['away_high_p']=pr((-cand.dist_high).fillna(0))
        cand['event_quality_p']=pr(cand.event.fillna(0))
        cand['count_p']=pr(cand.event_count.fillna(0))
        cand['v4_score']=0.32*cand.ret20_p+0.14*cand.ret3_p+0.16*cand.flow_p+0.10*cand.tech_p+0.14*cand.away_high_p+0.10*cand.event_quality_p-0.06*cand.count_p
        cand=cand.sort_values(['v4_score','flow','ret20','ret3'],ascending=False).reset_index(drop=True); cand['rank']=np.arange(1,len(cand)+1); ranks.append(cand.assign(test_id=w.test_id))
        leader=r.loc[r.week_return.idxmax()] if r.week_return.notna().any() else None
        if leader is None:continue
        m=cand[cand.symbol==leader.symbol]; lr=int(m.iloc[0]['rank']) if len(m) else None; top5=cand.head(5)
        summaries.append({'test_id':w.test_id,'week_start':ws.strftime('%Y-%m-%d'),'leader':leader.symbol,'leader_return':leader.week_return,'leader_in_pool':bool(len(m)),'leader_rank':lr,'leader_top5':bool(lr and lr<=5),'leader_top10':bool(lr and lr<=10),'leader_top20':bool(lr and lr<=20),'top5':';'.join(top5.symbol.tolist()),'portfolio_return':float(top5.week_return.dropna().mean()) if top5.week_return.notna().any() else np.nan})
        print(w.test_id,'leader',leader.symbol,'rank',lr,'top5',top5.symbol.tolist()); time.sleep(.2)
    sm=pd.DataFrame(summaries); rk=pd.concat(ranks,ignore_index=True) if ranks else pd.DataFrame(); sm.to_csv(OUT/'summary.csv',index=False); rk.to_csv(OUT/'rankings.csv',index=False)
    pd.DataFrame([{'weeks':len(sm),'pool_recall':sm.leader_in_pool.mean(),'top5':sm.leader_top5.mean(),'top10':sm.leader_top10.mean(),'top20':sm.leader_top20.mean(),'median_rank':sm.leader_rank.dropna().median(),'avg_portfolio_return':sm.portfolio_return.mean(),'note':'2023 untouched holdout. V4 weights frozen from 2024 diagnostics. CURRENT_XU100_PROXY; KAP text-direction only, no true takas/attachment parsing.'}]).to_csv(OUT/'stats.csv',index=False)
if __name__=='__main__':main()
