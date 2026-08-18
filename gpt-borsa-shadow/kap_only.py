#!/usr/bin/env python3
import csv,json,math,re,time,urllib.request
from datetime import date,timedelta,datetime,timezone
import hashlib

KAP_URL="https://www.kap.org.tr/tr/api/disclosure/members/byCriteria"
HEADERS={"Origin":"https://www.kap.org.tr","Referer":"https://www.kap.org.tr/tr/bildirim-sorgu","User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36","Accept":"application/json, text/plain, */*","Accept-Language":"tr-TR,tr;q=0.9,en;q=0.8","Content-Type":"application/json"}
HARD_RE=re.compile(r"(\d|%|\bTL\b|\bTRY\b|\bUSD\b|\bEUR\b|milyon|milyar|trilyon|MW|MWh|GWh|adet|ton|kapasite|sözleşme|bedel|tutar|ciro|kâr|kar\b|satış|yatırım|ihale|sipariş|temettü|geri alım|borçlanma|sermaye|pay geri|finansal sonuç)",re.I)

def post(payload,retries=4):
    raw=json.dumps(payload).encode();last=None
    for i in range(retries):
        try:
            req=urllib.request.Request(KAP_URL,data=raw,headers=HEADERS,method="POST")
            with urllib.request.urlopen(req,timeout=45) as r: obj=json.loads(r.read().decode("utf-8",errors="replace"))
            if isinstance(obj,list):return obj
            if isinstance(obj,dict):
                for k in ("data","list","result","resultList","items"):
                    if isinstance(obj.get(k),list):return obj[k]
                return [obj]
        except Exception as e:last=e;time.sleep(2**i)
    raise RuntimeError(repr(last))

def fetch_window(a,b):
    return post({"fromDate":a,"toDate":b,"memberType":"","mkkMemberOidList":[],"inactiveMkkMemberOidList":[],"disclosureClass":"","subjectList":[],"isLate":"","mainSector":"","sector":"","subSector":"","marketOid":"","index":"","bdkReview":"","bdkMemberOidList":[],"year":"","term":"","ruleType":"","period":"","fromSrc":False,"srcCategory":"","disclosureIndexList":[]})

def codes(r):
    raw=r.get("stockCodes") or r.get("stockCode") or r.get("relatedStocks") or ""
    vals=raw if isinstance(raw,list) else re.split(r"[,;/\s]+",str(raw))
    return {x.strip().upper() for x in vals if x and x.strip()}
def mean(xs):
    xs=[x for x in xs if x is not None];return sum(xs)/len(xs) if xs else None
def ranks(v):
    p=sorted(enumerate(v),key=lambda x:x[1]);o=[0.]*len(v);i=0
    while i<len(p):
        j=i+1
        while j<len(p) and p[j][1]==p[i][1]:j+=1
        q=(i+1+j)/2
        for k in range(i,j):o[p[k][0]]=q
        i=j
    return o
def corr(x,y):
    if len(x)<3:return None
    mx=sum(x)/len(x);my=sum(y)/len(y);sx=sum((a-mx)**2 for a in x);sy=sum((b-my)**2 for b in y)
    return None if sx<=0 or sy<=0 else sum((a-mx)*(b-my) for a,b in zip(x,y))/math.sqrt(sx*sy)
def spear(x,y):return corr(ranks(x),ranks(y))

with open("gpt-borsa-shadow/panels.csv",encoding="utf-8-sig",newline="") as f:panels=list(csv.DictReader(f))
for p in panels:
    p["excess_ret"]=float(p["excess_ret"]);p["ca_flag"]=p.get("ca_flag") or None
    y,w=p["week"].split("-W");fr=date.fromisocalendar(int(y),int(w),5)
    p["curr_start"]=(fr-timedelta(days=7)).isoformat();p["curr_end"]=fr.isoformat();p["prev_start"]=(fr-timedelta(days=14)).isoformat();p["prev_end"]=(fr-timedelta(days=7)).isoformat()
    p["selection_hash"]=hashlib.sha256(f"GPTBORSA-A0-v0.4|{p['week']}|{p['ticker']}".encode()).hexdigest()

wins={}
for p in panels:
    wins[(p["curr_start"],p["curr_end"])]=None;wins[(p["prev_start"],p["prev_end"])]=None
errs={}
for a,b in sorted(wins):
    try:wins[(a,b)]=fetch_window(a,b)
    except Exception as e:wins[(a,b)]=[];errs[f"{a}|{b}"]=repr(e)
    time.sleep(.55)

def sel(t,a,b):
    m=[r for r in wins[(a,b)] if t in codes(r)];h=[]
    for r in m:
        txt=" ".join(str(r.get(k) or "") for k in ("summary","subject","memberTitle","kapTitle"))
        if HARD_RE.search(txt):h.append(r)
    return m,h

out=[]
for p in panels:
    kc,hc=sel(p["ticker"],p["curr_start"],p["curr_end"]);kp,hp=sel(p["ticker"],p["prev_start"],p["prev_end"])
    out.append({**p,"kap_curr7":len(kc),"kap_prev7":len(kp),"kap_shock":math.log1p(len(kc))-math.log1p(len(kp)),"hard_curr7":len(hc),"hard_prev7":len(hp),"hard_shock":math.log1p(len(hc))-math.log1p(len(hp)),"kap_ids_curr":"|".join(str(r.get("disclosureIndex")) for r in kc if r.get("disclosureIndex") is not None),"kap_ids_prev":"|".join(str(r.get("disclosureIndex")) for r in kp if r.get("disclosureIndex") is not None)})

with open("kap_only_backfill.csv","w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
weekly=[]
for wk in sorted({r["week"] for r in out}):
    wr=[r for r in out if r["week"]==wk and not r["ca_flag"]]
    def stat(k):
        x=[r[k] for r in wr];y=[r["excess_ret"] for r in wr];ic=spear(x,y)
        top=sorted(wr,key=lambda r:(r[k],r["selection_hash"]),reverse=True)[:10]
        return ic,mean([r["excess_ret"] for r in top])
    ki,kt=stat("kap_shock");hi,ht=stat("hard_shock")
    weekly.append({"week":wk,"n":len(wr),"kap_rank_ic":ki,"kap_top10_excess":kt,"hard_rank_ic":hi,"hard_top10_excess":ht,"kap_events":sum(r["kap_curr7"] for r in wr),"hard_events":sum(r["hard_curr7"] for r in wr)})
with open("kap_weekly_summary.csv","w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f,fieldnames=list(weekly[0]));w.writeheader();w.writerows(weekly)
overall={"observed_at":datetime.now(timezone.utc).isoformat(),"rows":len(out),"weeks":len(weekly),"kap_mean_weekly_ic":mean([r["kap_rank_ic"] for r in weekly]),"kap_mean_top10_excess":mean([r["kap_top10_excess"] for r in weekly]),"hard_mean_weekly_ic":mean([r["hard_rank_ic"] for r in weekly]),"hard_mean_top10_excess":mean([r["hard_top10_excess"] for r in weekly]),"total_kap_events":sum(r["kap_curr7"] for r in out),"total_hard_events":sum(r["hard_curr7"] for r in out),"kap_errors":errs,"note":"Frozen GPTBORSA-A0-v0.4 panel; KAP event-count and simple hard-information proxy only; novelty not scored."}
with open("kap_overall.json","w") as f:json.dump(overall,f,ensure_ascii=False,indent=2)
print(json.dumps(overall,ensure_ascii=False,indent=2))
