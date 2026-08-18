#!/usr/bin/env python3
import csv,json,math,re,time,urllib.request,urllib.parse,hashlib
from datetime import date,timedelta,datetime,timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

MEMBER_URL="https://www.kap.org.tr/tr/api/member/filter/"
NEWS_URL="https://news.google.com/rss/search"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
HEADERS={"User-Agent":UA,"Accept-Language":"tr-TR,tr;q=0.9,en;q=0.8","Referer":"https://www.kap.org.tr/tr/bildirim-sorgu"}
NEWS_HEADERS={"User-Agent":UA,"Accept-Language":"tr-TR,tr;q=0.9,en;q=0.8"}

# Pre-existing ACTIVE aliases from the 2026-08-18 v0.4 Entity Alias Registry.
OVERRIDES={
 "ASELS":'(\"ASELSAN\" OR ASELS)',
 "BIMAS":'(\"Bim Birlesik Magazalar\" OR BIMAS)',
 "AKBNK":'(Akbank OR AKBNK)',
 "EREGL":'(\"Eregli Demir ve Celik\" OR EREGL)',
 "GARAN":'(\"Garanti BBVA\" OR GARAN)',
}
LEGAL_RE=re.compile(r"\s+(T\.?A\.?O\.?|T\.?A\.?Ş\.?|A\.?O\.?|A\.?Ş\.?)\s*$",re.I)

def get_json(url,retries=3):
    last=None
    for i in range(retries):
        try:
            req=urllib.request.Request(url,headers=HEADERS)
            with urllib.request.urlopen(req,timeout=25) as r:return json.loads(r.read().decode("utf-8",errors="replace"))
        except Exception as e:last=e;time.sleep(1.5*(i+1))
    return None

def official_alias(t):
    obj=get_json(MEMBER_URL+urllib.parse.quote(t))
    if isinstance(obj,list) and obj:
        x=obj[0]
    elif isinstance(obj,dict):x=obj
    else:return None,None,None
    title=(x.get("title") or x.get("kapMemberTitle") or "").strip()
    oid=x.get("mkkMemberOid") or x.get("mkkMemberOidList")
    if not title:return None,oid,None
    short=LEGAL_RE.sub("",title).strip()
    expr=f'(\"{short}\" OR {t})'
    return title,oid,expr

def rss_items(expr,start,end,retries=3):
    q=f'{expr} BIST after:{start} before:{end}'
    url=NEWS_URL+"?"+urllib.parse.urlencode({"q":q,"hl":"tr","gl":"TR","ceid":"TR:tr"})
    last=None
    for i in range(retries):
        try:
            req=urllib.request.Request(url,headers=NEWS_HEADERS)
            with urllib.request.urlopen(req,timeout=25) as r:raw=r.read()
            root=ET.fromstring(raw);items=[];seen=set()
            for it in root.findall(".//item"):
                title=(it.findtext("title") or "").strip();link=(it.findtext("link") or "").strip();pub=(it.findtext("pubDate") or "").strip()
                key=link or title
                if key in seen:continue
                seen.add(key)
                try:d=parsedate_to_datetime(pub).date()
                except Exception:d=None
                items.append({"title":title,"link":link,"pubDate":pub,"date":d.isoformat() if d else None})
            return items,url,None
        except Exception as e:last=e;time.sleep(1.5*(i+1))
    return None,url,repr(last)

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
def spear(x,y):
    if len(x)<3:return None
    rx,ry=ranks(x),ranks(y);mx=sum(rx)/len(rx);my=sum(ry)/len(ry);sx=sum((a-mx)**2 for a in rx);sy=sum((b-my)**2 for b in ry)
    return None if sx<=0 or sy<=0 else sum((a-mx)*(b-my) for a,b in zip(rx,ry))/math.sqrt(sx*sy)

with open("gpt-borsa-shadow/panels.csv",encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
for r in rows:
    r["excess_ret"]=float(r["excess_ret"]);r["ca_flag"]=r.get("ca_flag") or None
    y,w=r["week"].split("-W");fr=date.fromisocalendar(int(y),int(w),5)
    r["prev_start"]=(fr-timedelta(days=14));r["curr_start"]=(fr-timedelta(days=7));r["curr_end"]=fr
    r["selection_hash"]=hashlib.sha256(f"GPTBORSA-A0-v0.4|{r['week']}|{r['ticker']}".encode()).hexdigest()

registry={};unique=sorted({r["ticker"] for r in rows})
for t in unique:
    title,oid,derived=official_alias(t)
    expr=OVERRIDES.get(t) or derived
    registry[t]={"ticker":t,"official_title":title,"mkk_oid":oid,"query_expr":expr,"alias_source":"PREREG_V0.4" if t in OVERRIDES else ("KAP_OFFICIAL_TITLE_V0.4B" if expr else "UNAVAILABLE")}
    time.sleep(.12)

cache={};out=[]
for r in rows:
    t=r["ticker"];reg=registry[t];expr=reg["query_expr"]
    valid=True;err=None;items=None;url=None
    if not expr:
        valid=False;err="ALIAS_UNAVAILABLE"
    else:
        key=(t,r["prev_start"].isoformat(),r["curr_end"].isoformat(),expr)
        if key not in cache:
            cache[key]=rss_items(expr,key[1],key[2]);time.sleep(.20)
        items,url,err=cache[key]
        if items is None:valid=False
    curr=prev=None;capped=False
    if valid:
        capped=len(items)>=100
        if capped:valid=False;err="RSS_CAP_100"
        else:
            prev=sum(1 for x in items if x["date"] and r["prev_start"]<=date.fromisoformat(x["date"])<r["curr_start"])
            curr=sum(1 for x in items if x["date"] and r["curr_start"]<=date.fromisoformat(x["date"])<r["curr_end"])
    shock=(math.log1p(curr)-math.log1p(prev)) if valid else None
    out.append({"week":r["week"],"ticker":t,"excess_ret":r["excess_ret"],"ca_flag":r["ca_flag"],"alias_source":reg["alias_source"],"official_title":reg["official_title"],"query_expr":expr,"query_hash":hashlib.sha256((url or str(expr)).encode()).hexdigest(),"prev_start":r["prev_start"].isoformat(),"curr_start":r["curr_start"].isoformat(),"curr_end":r["curr_end"].isoformat(),"news_prev7":prev,"news_curr7":curr,"news_shock":shock,"rss_total":len(items) if items is not None else None,"valid":valid,"error":err,"selection_hash":r["selection_hash"]})

with open("news_alias_backfill.csv","w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
weekly=[]
for wk in sorted({r["week"] for r in out}):
    z=[r for r in out if r["week"]==wk and not r["ca_flag"] and r["valid"] and r["news_shock"] is not None]
    ic=spear([r["news_shock"] for r in z],[r["excess_ret"] for r in z]) if len(z)>=10 else None
    top=sorted(z,key=lambda r:(r["news_shock"],r["selection_hash"]),reverse=True)[:10]
    weekly.append({"week":wk,"valid_n":len(z),"rank_ic":ic,"top10_excess":mean([r["excess_ret"] for r in top]) if len(top)>=5 else None,"positive_shock_n":sum(r["news_shock"]>0 for r in z),"capped_n":sum(r["week"]==wk and r["error"]=="RSS_CAP_100" for r in out),"alias_unavailable_n":sum(r["week"]==wk and r["error"]=="ALIAS_UNAVAILABLE" for r in out)})
with open("news_alias_weekly.csv","w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f,fieldnames=list(weekly[0]));w.writeheader();w.writerows(weekly)
overall={"observed_at":datetime.now(timezone.utc).isoformat(),"scope":"ENTITY_RESOLUTION_SENSITIVITY_NOT_CONFIRMATORY_PRIMARY","rows":len(out),"weeks":len(weekly),"registry_count":len(registry),"preregistered_alias_count":sum(v["alias_source"]=="PREREG_V0.4" for v in registry.values()),"kap_derived_alias_count":sum(v["alias_source"]=="KAP_OFFICIAL_TITLE_V0.4B" for v in registry.values()),"alias_unavailable_count":sum(v["alias_source"]=="UNAVAILABLE" for v in registry.values()),"valid_rows":sum(r["valid"] for r in out),"capped_rows":sum(r["error"]=="RSS_CAP_100" for r in out),"mean_weekly_ic":mean([r["rank_ic"] for r in weekly]),"mean_top10_excess":mean([r["top10_excess"] for r in weekly]),"positive_ic_weeks":sum((r["rank_ic"] or 0)>0 for r in weekly),"note":"Five preregistered ACTIVE aliases are used verbatim. All other aliases are deterministically KAP official title (legal suffix stripped) OR ticker. No outcome-based alias tuning."}
with open("news_alias_overall.json","w",encoding="utf-8") as f:json.dump(overall,f,ensure_ascii=False,indent=2)
with open("alias_registry_derived.json","w",encoding="utf-8") as f:json.dump(registry,f,ensure_ascii=False,indent=2)
print(json.dumps(overall,ensure_ascii=False,indent=2))
