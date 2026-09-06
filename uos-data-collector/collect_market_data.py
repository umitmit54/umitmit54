from __future__ import annotations
import datetime as dt, hashlib, json, random, time, urllib.parse, urllib.request
from pathlib import Path
import pandas as pd
import yfinance as yf

BASE=Path(__file__).resolve().parent; OUT=BASE/"output"
RY=OUT/"raw"/"yahoo"; RI=OUT/"raw"/"isyatirim"; TR=OUT/"transformed"; Q=OUT/"quality"
for p in (RY,RI,TR,Q): p.mkdir(parents=True,exist_ok=True)
START="2018-01-01"; END="2026-09-06"
ISY="https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/HisseTekil"
FIELDS="HGDG_HS_KODU,HGDG_TARIH,HGDG_KAPANIS,HGDG_AOF,HGDG_MIN,HGDG_MAX,HGDG_HACIM,END_ENDEKS_KODU,END_TARIH,END_SEANS,END_DEGER,HG_KAPANIS,HG_AOF,HG_MIN,HG_MAX,HG_HACIM"

def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def flat(df,t):
    if isinstance(df.columns,pd.MultiIndex):
        lv=list(map(str,df.columns.get_level_values(-1)))
        if t in lv: df=df.xs(t,axis=1,level=-1,drop_level=True)
        else: df.columns=["__".join(map(str,c)).strip("_") for c in df.columns]
    return df

def get_y(t):
    err=""
    for n in range(4):
        try:
            d=yf.download(t,start=START,end=END,interval="1d",auto_adjust=False,actions=True,
                          repair=True,progress=False,threads=False,timeout=45)
            d=flat(d,t)
            if d.empty: raise RuntimeError("empty")
            d.index=pd.to_datetime(d.index).tz_localize(None); d.index.name="Date"
            return d,""
        except Exception as e:
            err=repr(e); time.sleep(min(20,2**(n+1))+random.random())
    return None,err

def split_factor(s):
    r=pd.to_numeric(s,errors="coerce").fillna(0).where(lambda x:x>0,1.0)
    return r.shift(-1,fill_value=1.0).iloc[::-1].cumprod().iloc[::-1]

def trans_y(sym,d):
    need=["Open","High","Low","Close","Adj Close","Volume"]
    if any(c not in d.columns for c in need): raise RuntimeError("missing:"+",".join(c for c in need if c not in d.columns))
    x=pd.DataFrame(index=d.index)
    for c in ["Open","High","Low","Close","Adj Close","Volume"]: x[c]=pd.to_numeric(d[c],errors="coerce")
    f=(x["Adj Close"]/x["Close"]).where(x["Close"]>0)
    x["adj_open"]=x["Open"]*f; x["adj_high"]=x["High"]*f; x["adj_low"]=x["Low"]*f; x["adj_close"]=x["Adj Close"]
    x["dividends"]=pd.to_numeric(d["Dividends"],errors="coerce").fillna(0) if "Dividends" in d else 0.0
    x["stock_splits"]=pd.to_numeric(d["Stock Splits"],errors="coerce").fillna(0) if "Stock Splits" in d else 0.0
    x["volume_split_adj"]=x["Volume"]*split_factor(x["stock_splits"])
    x["symbol"]=sym
    x=x.reset_index().rename(columns={"Date":"date","Open":"raw_open","High":"raw_high","Low":"raw_low","Close":"raw_close","Volume":"volume_raw"})
    x["date"]=pd.to_datetime(x["date"]).dt.strftime("%Y-%m-%d")
    return x

def isy_date(v):
    if not v:return None
    s=str(v)
    if s.startswith("/Date("):
        try:return dt.datetime.fromtimestamp(int(s.split("(")[1].split(")")[0].split("+")[0])/1000,dt.timezone.utc).date().isoformat()
        except:pass
    z=pd.to_datetime(s,errors="coerce",dayfirst=True)
    return None if pd.isna(z) else z.date().isoformat()

def get_i(sym):
    q={"hisse":sym,"startdate":"01-01-2018","enddate":"05-09-2026","historicalData":True,"section":"","webSiteUrl":"","columns":FIELDS}
    url=ISY+"?"+urllib.parse.urlencode(q); err=""
    for n in range(4):
        try:
            time.sleep(1.0+random.random()*.4)
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (UOS research; low-rate client)"})
            b=urllib.request.urlopen(req,timeout=45).read(); o=json.loads(b)
            if not (o.get("value") or []): raise RuntimeError("empty")
            return o,url,""
        except Exception as e:
            err=repr(e); time.sleep(min(25,2**(n+1))+random.random())
    return None,url,err

def trans_i(sym,o):
    a=[]
    for r in o.get("value") or []:
        d=isy_date(r.get("HGDG_TARIH"))
        if d:a.append({"date":d,"symbol":sym,"turnover":pd.to_numeric(r.get("HGDG_HACIM"),errors="coerce"),
                       "isy_adj_close":pd.to_numeric(r.get("HGDG_KAPANIS"),errors="coerce"),
                       "isy_raw_close":pd.to_numeric(r.get("HG_KAPANIS"),errors="coerce"),
                       "isy_index_close":pd.to_numeric(r.get("END_DEGER"),errors="coerce")})
    return pd.DataFrame(a)

def main():
    syms=json.loads((BASE/"symbols_2019_2026.json").read_text())
    cov=[]; ys=[]; ins=[]; sources=[]
    for k,s in enumerate(syms,1):
        print(f"[{k}/{len(syms)}] {s}",flush=True)
        yd,ye=get_y(s+".IS"); yr=0; yf=yl=""
        if yd is not None:
            p=RY/f"{s}.csv"; yd.to_csv(p); sources.append({"path":str(p.relative_to(OUT)),"sha256":sha(p)})
            try:
                t=trans_y(s,yd); yr=len(t); yf=t.date.min(); yl=t.date.max(); ys.append(t)
            except Exception as e: ye="transform:"+repr(e)
        io,url,ie=get_i(s); ir=0; inf=inl=""
        if io is not None:
            p=RI/f"{s}.json"; p.write_text(json.dumps(io,ensure_ascii=False)); sources.append({"path":str(p.relative_to(OUT)),"sha256":sha(p),"url":url})
            t=trans_i(s,io); ir=len(t)
            if ir: inf=t.date.min(); inl=t.date.max(); ins.append(t)
        cov.append({"symbol":s,"yahoo_rows":yr,"yahoo_first":yf,"yahoo_last":yl,"yahoo_error":ye,
                    "isyatirim_rows":ir,"isyatirim_first":inf,"isyatirim_last":inl,"isyatirim_error":ie})
        time.sleep(.15+random.random()*.15)

    c=pd.DataFrame(cov); c.to_csv(Q/"coverage.csv",index=False)
    ya=pd.concat(ys,ignore_index=True) if ys else pd.DataFrame(); ia=pd.concat(ins,ignore_index=True) if ins else pd.DataFrame()
    if not ya.empty: ya.to_csv(TR/"yahoo_adjusted_ohlcv.csv",index=False)
    if not ia.empty: ia.to_csv(TR/"isyatirim_turnover.csv",index=False)
    if not ya.empty:
        m=ya.merge(ia[["date","symbol","turnover","isy_adj_close","isy_raw_close","isy_index_close"]],on=["date","symbol"],how="left") if not ia.empty else ya.assign(turnover=float("nan"))
        m["instrument_id"]=m.symbol; m["buyable"]=float("nan"); m["sellable"]=float("nan")
        m.to_csv(TR/"prices_audit_full.csv",index=False)
        m[["date","instrument_id","adj_open","adj_high","adj_low","adj_close","turnover","volume_split_adj","buyable","sellable"]].rename(columns={"volume_split_adj":"volume"}).to_csv(TR/"prices_contract_candidate.csv",index=False)
        if not ia.empty:
            z=ya[["date","symbol","adj_close"]].merge(ia[["date","symbol","isy_adj_close"]],on=["date","symbol"])
            z=z[(z.adj_close>0)&(z.isy_adj_close>0)].copy(); z["ratio"]=z.adj_close/z.isy_adj_close
            if not z.empty:
                v=z.groupby("symbol").ratio.agg(["count","mean","std","min","max"]).reset_index(); v["cv"]=v["std"]/v["mean"]; v.to_csv(Q/"yahoo_vs_isyatirim_adjclose.csv",index=False)

    bm={}
    for bt in ["XU100.IS","^XU100"]:
        bd,be=get_y(bt)
        if bd is None: bm[bt]={"error":be}; continue
        try:
            t=trans_y("XU100",bd); p=RY/f"benchmark_{bt.replace('^','caret').replace('.','_')}.csv"; bd.to_csv(p)
            bm[bt]={"rows":len(t),"first":t.date.min(),"last":t.date.max()}
            if bt=="XU100.IS": t[["date","adj_open","adj_close"]].to_csv(TR/"benchmark_contract_candidate.csv",index=False)
        except Exception as e: bm[bt]={"error":repr(e)}
    (Q/"benchmark_meta.json").write_text(json.dumps(bm,indent=2))

    status={"symbols_requested":len(syms),"yahoo_nonempty":int((c.yahoo_rows>0).sum()),"isyatirim_nonempty":int((c.isyatirim_rows>0).sum()),
            "both_nonempty":int(((c.yahoo_rows>0)&(c.isyatirim_rows>0)).sum()),"generated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "blockers":["PIT sector/listing metadata incomplete","buyable/sellable not provided","delisting terminal values require separate verification"]}
    (OUT/"STATUS.json").write_text(json.dumps(status,ensure_ascii=False,indent=2))
    (OUT/"manifest.json").write_text(json.dumps({"kind":"UOS_DATA_COLLECTION","warmup_start":START,"signal_end":"2026-09-04",
        "price_basis":"Yahoo Adj Close; OHLC multiplied by AdjClose/Close daily factor","volume_basis":"Yahoo share volume split-normalized only",
        "turnover_basis":"Is Yatirim HGDG_HACIM","sources":["https://finance.yahoo.com/",ISY],"files":sources,
        "note":"No buyable/sellable or PIT sector fields fabricated."},ensure_ascii=False,indent=2))
    print(json.dumps(status,ensure_ascii=False),flush=True)

if __name__=="__main__": main()
