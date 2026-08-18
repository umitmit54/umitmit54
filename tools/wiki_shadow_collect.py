#!/usr/bin/env python3
"""GPT BORSA v0.4 conservative Wikimedia pageview shadow backfill.

Entity resolution is deliberately conservative and outcome-blind:
1) resolve BIST ticker -> official KAP company title;
2) search Turkish Wikipedia using official title + ticker;
3) accept a page only if its lead extract explicitly contains the ticker as a
   whole token and also mentions BIST/Borsa Istanbul, OR it is one of the five
   preregistered/validated manual aliases below;
4) otherwise retain UNAVAILABLE/AMBIGUOUS (never zero-impute pageviews).

Attention shock = log1p(mean daily views in current 7 calendar days) -
                  log1p(mean daily views in immediately preceding 28 days).
"""
import ast, base64, csv, gzip, io, json, math, re, time, unicodedata
import urllib.parse, urllib.request
from datetime import date, timedelta

OLD_SOURCE = "tools/news_shadow_collect.py"
OUT_ROWS = "wiki_shadow_rows_7v28.csv"
OUT_WEEKLY = "wiki_shadow_weekly_7v28.csv"
UA = "GPT-BORSA-Shadow/0.4 research-contact github.com/umitmit54"
KAP_BASE = "https://www.kap.org.tr"
KAP_COMPANY = KAP_BASE + "/tr/api/company/items"
WIKI_API = "https://tr.wikipedia.org/w/api.php"
PV_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/tr.wikipedia/all-access/user"
KAP_HEADERS = {
    "Origin": KAP_BASE,
    "Referer": KAP_BASE + "/tr/bildirim-sorgu",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}
MANUAL = {
    "ASELS": "ASELSAN",
    "BIMAS": "BİM",
    "AKBNK": "Akbank",
    "EREGL": "Ereğli Demir ve Çelik Fabrikaları",
    "GARAN": "Garanti BBVA",
}


def get_json(url, headers=None, tries=4):
    h={"User-Agent":UA,"Accept":"application/json"}; h.update(headers or {})
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(url,headers=h)
            with urllib.request.urlopen(req,timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last=e; time.sleep(1.5*(i+1))
    raise last


def extract_panel():
    src=open(OLD_SOURCE,encoding="utf-8").read(); m=re.search(r"^PANEL_B64=(.+)$",src,re.M)
    b64=ast.literal_eval(m.group(1))
    return list(csv.DictReader(io.StringIO(gzip.decompress(base64.b64decode(b64)).decode("utf-8"))))


def load_kap_titles():
    out={}
    for typ in ["HT","YK","PYS","BDK","DCS","DDK","DK","KVH"]:
        try: rows=get_json(f"{KAP_COMPANY}/{typ}/A",KAP_HEADERS)
        except Exception as e:
            print("WARN KAP company",typ,e,flush=True); continue
        if isinstance(rows,dict): rows=rows.get("data") or rows.get("list") or []
        for r in rows:
            title=(r.get("memberTitle") or "").strip(); codes=(r.get("stockCodes") or "")
            for code in re.split(r"[,;/\s]+",codes):
                code=code.strip().upper()
                if code and title: out[code]=title
    return out


def wiki_search(query, limit=5):
    url=WIKI_API+"?"+urllib.parse.urlencode({"action":"query","list":"search","srsearch":query,"srlimit":limit,"format":"json","utf8":1})
    obj=get_json(url); return obj.get("query",{}).get("search",[])


def wiki_extract(title):
    url=WIKI_API+"?"+urllib.parse.urlencode({"action":"query","prop":"extracts","exintro":1,"explaintext":1,"redirects":1,"titles":title,"format":"json","utf8":1})
    obj=get_json(url); pages=obj.get("query",{}).get("pages",{})
    if not pages:return "",title
    p=next(iter(pages.values())); return p.get("extract") or "", p.get("title") or title


def resolve_page(ticker, company):
    if ticker in MANUAL:
        try:
            ex,canon=wiki_extract(MANUAL[ticker]); return canon,"MANUAL_VALIDATED",ex[:240]
        except Exception as e:return None,"UNAVAILABLE_MANUAL",str(e)
    if not company:return None,"NO_KAP_TITLE",""
    queries=[f'"{company}" {ticker}', company]
    seen=set()
    for q in queries:
        try:cands=wiki_search(q,5)
        except Exception:continue
        for c in cands:
            title=c.get("title") or ""
            if not title or title in seen:continue
            seen.add(title)
            try:ex,canon=wiki_extract(title)
            except Exception:continue
            txt=(canon+" "+ex)
            ticker_ok=re.search(rf"(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])",txt,re.I) is not None
            market_ok=("Borsa İstanbul" in txt or "Borsa Istanbul" in txt or re.search(r"\bBIST\b",txt,re.I) is not None)
            if ticker_ok and market_ok:return canon,"AUTO_EXPLICIT_TICKER_MARKET",ex[:240]
    return None,"UNAVAILABLE_OR_AMBIGUOUS",""


def pageviews(title,start,end):
    # inclusive dates, REST timestamps YYYYMMDD00
    enc=urllib.parse.quote(title.replace(" ","_"),safe="")
    url=f"{PV_API}/{enc}/daily/{start.strftime('%Y%m%d')}00/{end.strftime('%Y%m%d')}00"
    obj=get_json(url); return [int(x.get("views",0)) for x in obj.get("items",[])]


def ranks(xs):
    order=sorted(range(len(xs)),key=lambda i:xs[i]); out=[0.0]*len(xs); i=0
    while i<len(order):
        j=i+1
        while j<len(order) and xs[order[j]]==xs[order[i]]:j+=1
        avg=(i+1+j)/2
        for k in range(i,j):out[order[k]]=avg
        i=j
    return out


def pearson(a,b):
    if len(a)<3:return None
    ma=sum(a)/len(a);mb=sum(b)/len(b);xa=[x-ma for x in a];xb=[x-mb for x in b]
    den=(sum(x*x for x in xa)*sum(y*y for y in xb))**.5
    return None if den==0 else sum(x*y for x,y in zip(xa,xb))/den

def spearman(a,b):return pearson(ranks(a),ranks(b))

panel=extract_panel(); tickers=sorted({r["Ticker"] for r in panel}); titles=load_kap_titles()
print("tickers",len(tickers),"kap titles",sum(t in titles for t in tickers),flush=True)
resolved={}
for i,t in enumerate(tickers,1):
    page,status,evidence=resolve_page(t,titles.get(t,"")); resolved[t]=(page,status,evidence)
    print(i,len(tickers),t,status,page or "-",flush=True); time.sleep(.12)

out=[]
for r in panel:
    t=r["Ticker"]; page,status,evidence=resolved[t]
    curr_start=date.fromisoformat(r["CurrStart"]); curr_end=date.fromisoformat(r["CurrEnd"])-timedelta(days=1)
    base_start=curr_start-timedelta(days=28); base_end=curr_start-timedelta(days=1)
    rec={"Week":r["Week"],"Freeze":r["Freeze"],"Ticker":t,"KAPCompanyTitle":titles.get(t,""),"WikiPage":page or "","ResolveStatus":status,"ResolveEvidence":evidence,"RowStatus":r["RowStatus"],"ExcessRet":r["ExcessRet"],"CurrStart":curr_start.isoformat(),"CurrEnd":curr_end.isoformat(),"BaseStart":base_start.isoformat(),"BaseEnd":base_end.isoformat()}
    if page:
        try:
            cv=pageviews(page,curr_start,curr_end); bv=pageviews(page,base_start,base_end)
            if len(cv)>=6 and len(bv)>=24:
                cm=sum(cv)/len(cv); bm=sum(bv)/len(bv)
                rec.update(CurrViews=sum(cv),BaseViews=sum(bv),CurrDays=len(cv),BaseDays=len(bv),CurrDailyMean=cm,BaseDailyMean=bm,WikiShock7v28=math.log1p(cm)-math.log1p(bm),Coverage="OK")
            else:rec.update(Coverage="LOW")
        except Exception as e:rec.update(Coverage="UNAVAILABLE_API",ResolveEvidence=str(e)[:240])
        time.sleep(.06)
    else:rec.update(Coverage="UNAVAILABLE")
    out.append(rec)

fields=[]
for r in out:
    for k in r:
        if k not in fields:fields.append(k)
with open(OUT_ROWS,"w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
weekly=[]
for week in sorted({r["Week"] for r in out}):
    wr=[r for r in out if r.get("Coverage")=="OK" and r["RowStatus"]=="VALID" and r.get("WikiShock7v28") is not None and r.get("ExcessRet") not in (None,"")]
    wr=[r for r in wr if r["Week"]==week]
    xs=[float(r["WikiShock7v28"]) for r in wr]; ys=[float(r["ExcessRet"]) for r in wr]
    ic=spearman(xs,ys) if len(wr)>=5 and len(set(xs))>1 else None
    top=sorted(wr,key=lambda r:float(r["WikiShock7v28"]),reverse=True)[:max(1,len(wr)//3)] if wr else []
    weekly.append({"Week":week,"CoveredN":len(wr),"CoveragePct":len(wr)/len([r for r in panel if r["Week"]==week and r["RowStatus"]=="VALID"]),"WikiRankIC":ic,"TopThirdExcess":(sum(float(r["ExcessRet"]) for r in top)/len(top)) if top else None})
valid_ic=[x for x in weekly if x["WikiRankIC"] is not None]
weekly.append({"Week":"OVERALL_MEAN","CoveredN":sum(x["CoveredN"] for x in weekly),"CoveragePct":sum(x["CoveredN"] for x in weekly)/sum(1 for r in panel if r["RowStatus"]=="VALID"),"WikiRankIC":sum(x["WikiRankIC"] for x in valid_ic)/len(valid_ic) if valid_ic else None,"TopThirdExcess":sum(x["TopThirdExcess"] for x in valid_ic)/len(valid_ic) if valid_ic else None})
with open(OUT_WEEKLY,"w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=list(weekly[0]));w.writeheader();w.writerows(weekly)
for x in weekly:print(x,flush=True)
