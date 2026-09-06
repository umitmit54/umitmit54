from __future__ import annotations
import argparse, datetime as dt, hashlib, json, random, time, urllib.parse, urllib.request
from pathlib import Path
import pandas as pd

BASE=Path(__file__).resolve().parent
ENDPOINT='https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/HisseTekil'
START='01-01-2018'; END='05-09-2026'

def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def fetch(sym):
    q={'hisse':sym,'startdate':START,'enddate':END,'historicalData':True}
    url=ENDPOINT+'?'+urllib.parse.urlencode(q)
    err=''
    for n in range(5):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (UOS research; low-rate collector)'})
            with urllib.request.urlopen(req,timeout=60) as resp: b=resp.read()
            o=json.loads(b); vals=o.get('value',[]) if isinstance(o,dict) else []
            if not vals: raise RuntimeError('empty value')
            return o,url,''
        except Exception as e:
            err=repr(e); time.sleep(min(20,2**n)+random.random())
    return None,url,err

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--shard-index',type=int,required=True); ap.add_argument('--shard-count',type=int,default=3); a=ap.parse_args()
    syms=json.loads((BASE/'symbols_2019_2026.json').read_text())
    n=len(syms); lo=(n*a.shard_index)//a.shard_count; hi=(n*(a.shard_index+1))//a.shard_count; syms=syms[lo:hi]
    OUT=BASE/f'isyatirim_shard_{a.shard_index}'; RAW=OUT/'raw'; TR=OUT/'transformed'; Q=OUT/'quality'
    for p in (RAW,TR,Q): p.mkdir(parents=True,exist_ok=True)
    cov=[]; rows=[]; manifest=[]
    for i,s in enumerate(syms,1):
        print(f'[{i}/{len(syms)}] {s}',flush=True)
        o,url,err=fetch(s)
        if o is None:
            cov.append({'symbol':s,'rows':0,'first':'','last':'','error':err}); continue
        p=RAW/f'{s}.json'; p.write_text(json.dumps(o,ensure_ascii=False))
        vals=o.get('value',[]); dates=[]
        for r in vals:
            d=pd.to_datetime(r.get('HGDG_TARIH'),format='%d-%m-%Y',errors='coerce')
            if pd.isna(d): continue
            ds=d.strftime('%Y-%m-%d'); dates.append(ds)
            rows.append({'date':ds,'instrument_id':s,
              'adj_close':pd.to_numeric(r.get('HGDG_KAPANIS'),errors='coerce'),
              'adj_low':pd.to_numeric(r.get('HGDG_MIN'),errors='coerce'),
              'adj_high':pd.to_numeric(r.get('HGDG_MAX'),errors='coerce'),
              'adj_vwap':pd.to_numeric(r.get('HGDG_AOF'),errors='coerce'),
              'turnover_tl':pd.to_numeric(r.get('HGDG_HACIM'),errors='coerce'),
              'raw_close':pd.to_numeric(r.get('HG_KAPANIS'),errors='coerce'),
              'raw_low':pd.to_numeric(r.get('HG_MIN'),errors='coerce'),
              'raw_high':pd.to_numeric(r.get('HG_MAX'),errors='coerce'),
              'raw_vwap':pd.to_numeric(r.get('HG_AOF'),errors='coerce'),
              'raw_turnover_tl':pd.to_numeric(r.get('HG_HACIM'),errors='coerce'),
              'xu100_price_index_close':pd.to_numeric(r.get('END_DEGER'),errors='coerce'),
              'capital':pd.to_numeric(r.get('SERMAYE'),errors='coerce')})
        cov.append({'symbol':s,'rows':len(dates),'first':min(dates) if dates else '', 'last':max(dates) if dates else '', 'error':''})
        manifest.append({'symbol':s,'url':url,'retrieved_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'rows':len(dates),'sha256':sha256(p)})
        time.sleep(.6+random.random()*.25)
    c=pd.DataFrame(cov); c.to_csv(Q/'coverage.csv',index=False)
    x=pd.DataFrame(rows); x.to_csv(TR/'isyatirim_historical_native.csv',index=False)
    status={'shard_index':a.shard_index,'shard_count':a.shard_count,'symbol_slice':[lo,hi],'requested_symbols':len(syms),'nonempty_symbols':int((c['rows']>0).sum()),'empty_symbols':int((c['rows']==0).sum()),'total_rows':int(c['rows'].sum()),'generated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    (OUT/'STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2))
    (OUT/'manifest.json').write_text(json.dumps({'source':'Is Yatirim HisseTekil','endpoint':ENDPOINT,'start':START,'end':END,'retrievals':manifest},ensure_ascii=False,indent=2))
    print(json.dumps(status,ensure_ascii=False),flush=True)
if __name__=='__main__': main()
