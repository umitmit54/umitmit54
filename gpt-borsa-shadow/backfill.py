#!/usr/bin/env python3
import csv, json, math, re, time, urllib.request, urllib.parse
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

KAP_URL = "https://www.kap.org.tr/tr/api/disclosure/members/byCriteria"
KAP_REFERER = "https://www.kap.org.tr/tr/bildirim-sorgu"
NEWS_BASE = "https://news.google.com/rss/search"

HEADERS = {
    "Origin": "https://www.kap.org.tr",
    "Referer": KAP_REFERER,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Content-Type": "application/json",
}
NEWS_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

HARD_RE = re.compile(
    r"(\d|%|\bTL\b|\bTRY\b|\bUSD\b|\bEUR\b|milyon|milyar|trilyon|MW|MWh|GWh|adet|ton|kapasite|"
    r"sözleşme|bedel|tutar|ciro|kâr|kar\b|satış|yatırım|ihale|sipariş|temettü|geri alım|"
    r"borçlanma|sermaye|pay geri|finansal sonuç)", re.I)

def fetch_json_post(url, payload, retries=4):
    data = json.dumps(payload).encode("utf-8")
    last = None
    for i in range(retries):
        req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                obj = json.loads(resp.read().decode("utf-8", errors="replace"))
            if isinstance(obj, list): return obj
            if isinstance(obj, dict):
                for k in ("data","list","result","resultList","items"):
                    if isinstance(obj.get(k), list): return obj[k]
                return [obj]
            return []
        except Exception as e:
            last = e; time.sleep(2**i)
    raise RuntimeError(f"KAP POST failed: {last}")

def kap_week(start, end):
    payload = {
        "fromDate":start,"toDate":end,"memberType":"","mkkMemberOidList":[],
        "inactiveMkkMemberOidList":[],"disclosureClass":"","subjectList":[],"isLate":"",
        "mainSector":"","sector":"","subSector":"","marketOid":"","index":"",
        "bdkReview":"","bdkMemberOidList":[],"year":"","term":"","ruleType":"",
        "period":"","fromSrc":False,"srcCategory":"","disclosureIndexList":[]}
    return fetch_json_post(KAP_URL, payload)

def stock_codes(row):
    raw = row.get("stockCodes") or row.get("stockCode") or row.get("relatedStocks") or ""
    vals = raw if isinstance(raw,list) else re.split(r"[,;/\s]+", str(raw))
    return {v.strip().upper() for v in vals if v and v.strip()}

def news_count(ticker, start, end, retries=4):
    q = f'"{ticker}" BIST after:{start} before:{end}'
    url = NEWS_BASE + "?" + urllib.parse.urlencode({"q":q,"hl":"tr","gl":"TR","ceid":"TR:tr"})
    last=None
    for i in range(retries):
        req=urllib.request.Request(url,headers=NEWS_HEADERS)
        try:
            with urllib.request.urlopen(req,timeout=30) as resp: xml=resp.read()
            return len(ET.fromstring(xml).findall(".//item")),url
        except Exception as e:
            last=e; time.sleep(1.5*(i+1))
    return None,url

def rankdata(vals):
    pairs=sorted(enumerate(vals),key=lambda x:x[1]); ranks=[0.0]*len(vals); i=0
    while i<len(pairs):
        j=i+1
        while j<len(pairs) and pairs[j][1]==pairs[i][1]: j+=1
        avg=(i+1+j)/2.0
        for k in range(i,j): ranks[pairs[k][0]]=avg
        i=j
    return ranks

def pearson(x,y):
    n=len(x)
    if n<3:return None
    mx=sum(x)/n;my=sum(y)/n; sx=sum((a-mx)**2 for a in x);sy=sum((b-my)**2 for b in y)
    if sx<=0 or sy<=0:return None
    return sum((a-mx)*(b-my) for a,b in zip(x,y))/math.sqrt(sx*sy)

def spearman(x,y): return pearson(rankdata(x),rankdata(y)) if len(x)>=3 else None
def mean(xs):
    xs=[x for x in xs if x is not None]
    return sum(xs)/len(xs) if xs else None

with open("gpt-borsa-shadow/panels.csv",encoding="utf-8-sig",newline="") as f: panels=list(csv.DictReader(f))
from datetime import date,timedelta
import hashlib
for p in panels:
    p["excess_ret"]=float(p["excess_ret"]) if p.get("excess_ret") not in ("",None) else None
    p["ca_flag"]=p.get("ca_flag") or None
    ys,ws=p["week"].split("-W"); freeze=date.fromisocalendar(int(ys),int(ws),5)
    p["freeze"]=freeze.isoformat();p["curr_start"]=(freeze-timedelta(days=7)).isoformat();p["curr_end"]=freeze.isoformat()
    p["prev_start"]=(freeze-timedelta(days=14)).isoformat();p["prev_end"]=(freeze-timedelta(days=7)).isoformat()
    p["row_status"]="EXCLUDE_CA" if p["ca_flag"] else "VALID"
    p["selection_hash"]=hashlib.sha256(f"GPTBORSA-A0-v0.4|{p['week']}|{p['ticker']}".encode()).hexdigest()
observed_at=datetime.now(timezone.utc).isoformat()

windows={}
for p in panels:
    for a,b in ((p["curr_start"],p["curr_end"]),(p["prev_start"],p["prev_end"])): windows[(a,b)]=None
kap_errors={}
for a,b in sorted(windows):
    try: windows[(a,b)]=kap_week(a,b)
    except Exception as e: windows[(a,b)]=[];kap_errors[f"{a}|{b}"]=repr(e)
    time.sleep(.45)

def kap_for(t,a,b):
    matched=[r for r in windows.get((a,b),[]) if t.upper() in stock_codes(r)];hard=[]
    for r in matched:
        txt=" ".join(str(r.get(k) or "") for k in ("summary","subject","memberTitle","kapTitle"))
        if HARD_RE.search(txt):hard.append(r)
    return matched,hard
news_cache={}
def get_news(t,a,b):
    key=(t,a,b)
    if key not in news_cache:
        news_cache[key]=news_count(t,a,b);time.sleep(.18)
    return news_cache[key]

rows_out=[];raw_kap={}
for p in panels:
    t=p["ticker"];nc,nurlc=get_news(t,p["curr_start"],p["curr_end"]);np_,nurlp=get_news(t,p["prev_start"],p["prev_end"])
    kc,khc=kap_for(t,p["curr_start"],p["curr_end"]);kp,khp=kap_for(t,p["prev_start"],p["prev_end"])
    ns=(math.log1p(nc)-math.log1p(np_)) if nc is not None and np_ is not None else None
    ks=math.log1p(len(kc))-math.log1p(len(kp));khs=math.log1p(len(khc))-math.log1p(len(khp))
    rows_out.append({**p,"news_curr7":nc,"news_prev7":np_,"news_shock":ns,"news_curr_url":nurlc,"news_prev_url":nurlp,
      "kap_curr7":len(kc),"kap_prev7":len(kp),"kap_shock":ks,"kap_hard_curr7":len(khc),"kap_hard_prev7":len(khp),"kap_hard_shock":khs,
      "kap_ids_curr":"|".join(str(r.get("disclosureIndex")) for r in kc if r.get("disclosureIndex") is not None),
      "kap_ids_prev":"|".join(str(r.get("disclosureIndex")) for r in kp if r.get("disclosureIndex") is not None),"observed_at":observed_at})
    raw_kap[f"{p['week']}|{t}|curr"]=kc;raw_kap[f"{p['week']}|{t}|prev"]=kp

with open("shadow_backfill.csv","w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f,fieldnames=list(rows_out[0].keys()));w.writeheader();w.writerows(rows_out)
weekly=[]
for week in sorted({r["week"] for r in rows_out}):
    wr=[r for r in rows_out if r["week"]==week and r["row_status"]=="VALID" and not r.get("ca_flag")]
    def stats(name):
        z=[r for r in wr if r.get(name) is not None and r.get("excess_ret") is not None]
        ic=spearman([r[name] for r in z],[r["excess_ret"] for r in z]) if len(z)>=10 else None
        top=sorted(z,key=lambda r:(r[name],r["selection_hash"]),reverse=True)[:10]
        return len(z),ic,mean([r["excess_ret"] for r in top]) if len(top)>=5 else None
    nn,nic,ntop=stats("news_shock");kn,kic,ktop=stats("kap_shock");hn,hic,htop=stats("kap_hard_shock")
    weekly.append({"week":week,"valid_n":len(wr),"news_n":nn,"news_rank_ic":nic,"news_top10_excess":ntop,
      "kap_n":kn,"kap_rank_ic":kic,"kap_top10_excess":ktop,"kap_hard_n":hn,"kap_hard_rank_ic":hic,"kap_hard_top10_excess":htop})
with open("weekly_summary.csv","w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f,fieldnames=list(weekly[0].keys()));w.writeheader();w.writerows(weekly)
overall={"observed_at":observed_at,"rows":len(rows_out),"weeks":len(weekly),
 "news_mean_weekly_ic":mean([r["news_rank_ic"] for r in weekly]),"news_mean_top10_excess":mean([r["news_top10_excess"] for r in weekly]),
 "kap_mean_weekly_ic":mean([r["kap_rank_ic"] for r in weekly]),"kap_mean_top10_excess":mean([r["kap_top10_excess"] for r in weekly]),
 "kap_hard_mean_weekly_ic":mean([r["kap_hard_rank_ic"] for r in weekly]),"kap_hard_mean_top10_excess":mean([r["kap_hard_top10_excess"] for r in weekly]),
 "kap_errors":kap_errors,"news_missing_rows":sum(1 for r in rows_out if r["news_shock"] is None),
 "source_notes":{"KAP":KAP_URL,"GoogleNews":NEWS_BASE,"protocol":"GPTBORSA-A0-v0.4 shadow; no outcome-driven tuning",
 "news_query":"\"TICKER\" BIST after:START before:END","kap_hard_proxy":HARD_RE.pattern,"novelty":"NOT_SCORED_IN_THIS_RUN"}}
with open("overall.json","w",encoding="utf-8") as f:json.dump(overall,f,ensure_ascii=False,indent=2)
with open("kap_raw.json","w",encoding="utf-8") as f:json.dump(raw_kap,f,ensure_ascii=False,indent=2)
print(json.dumps(overall,ensure_ascii=False,indent=2))
