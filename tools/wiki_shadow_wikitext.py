#!/usr/bin/env python3
"""Conservative Wikimedia backfill using full Wikipedia wikitext for BIST/ticker proof.

A0-10 feature is unchanged. This only fixes entity resolution: many Turkish
Wikipedia articles keep exchange/ticker evidence in the infobox rather than the
lead extract. A page is accepted only if the full source contains the exact
BIST ticker token and BIST/Borsa Istanbul evidence. Pageviews are fetched
sequentially with 429 backoff, once per article for the whole shadow period.
"""
import ast, base64, csv, gzip, io, json, math, re, time
import urllib.parse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

OLD_SOURCE='tools/news_shadow_collect.py'
OUT_ROWS='wiki_shadow_rows_wikitext.csv'
OUT_WEEKLY='wiki_shadow_weekly_wikitext.csv'
OUT_ENTITY='wiki_shadow_entity_map_wikitext.csv'
UA='GPT-BORSA-Shadow/0.4 (research; github.com/umitmit54)'
KAP_BASE='https://www.kap.org.tr'
KAP_COMPANY=KAP_BASE+'/tr/api/company/items'
WIKI_API='https://tr.wikipedia.org/w/api.php'
PV_API='https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/tr.wikipedia/all-access/user'
KAP_HEADERS={'Origin':KAP_BASE,'Referer':KAP_BASE+'/tr/bildirim-sorgu','User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36','Accept':'application/json, text/plain, */*','Accept-Language':'tr-TR,tr;q=0.9,en;q=0.8'}


def get_json(url,headers=None,tries=3,timeout=25,backoff=1.5):
    h={'User-Agent':UA,'Accept':'application/json'}; h.update(headers or {})
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(url,headers=h)
            with urllib.request.urlopen(req,timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            last=e
            if e.code==429 and i+1<tries:
                ra=e.headers.get('Retry-After')
                try: delay=float(ra) if ra else backoff*(i+1)*2
                except Exception: delay=backoff*(i+1)*2
                time.sleep(delay); continue
            if i+1<tries: time.sleep(backoff*(i+1)); continue
        except Exception as e:
            last=e
            if i+1<tries: time.sleep(backoff*(i+1)); continue
    raise last


def extract_panel():
    src=open(OLD_SOURCE,encoding='utf-8').read(); m=re.search(r'^PANEL_B64=(.+)$',src,re.M)
    return list(csv.DictReader(io.StringIO(gzip.decompress(base64.b64decode(ast.literal_eval(m.group(1)))).decode('utf-8'))))


def load_kap_titles():
    out={}
    for typ in ['IGS','IGMS','KVS','HT','YK','PYS','BDK','DCS','DDK','DK','KVH']:
        try: rows=get_json(f'{KAP_COMPANY}/{typ}/A',KAP_HEADERS,tries=2,timeout=25)
        except Exception as e: print('WARN KAP',typ,e,flush=True); continue
        if isinstance(rows,dict): rows=rows.get('data') or rows.get('list') or []
        for r in rows:
            title=(r.get('kapMemberTitle') or r.get('memberTitle') or '').strip(); codes=(r.get('stockCode') or r.get('stockCodes') or '')
            for code in re.split(r'[,;/\s]+',codes):
                code=code.strip().upper()
                if code and title: out[code]=title
    return out


def search_wikitext(query,limit=4):
    params={'action':'query','generator':'search','gsrsearch':query,'gsrlimit':limit,
            'prop':'revisions','rvprop':'content','rvslots':'main','redirects':1,'format':'json','formatversion':2,'utf8':1}
    obj=get_json(WIKI_API+'?'+urllib.parse.urlencode(params),tries=2,timeout=22)
    return obj.get('query',{}).get('pages') or []


def page_source(p):
    revs=p.get('revisions') or []
    if not revs:return ''
    slots=revs[0].get('slots') or {}; main=slots.get('main') or {}
    return main.get('content') or main.get('*') or ''


def resolve(ticker,company):
    if not company:return None,'NO_KAP_TITLE',''
    queries=[f'"{company}" {ticker}',f'{company} {ticker}',company]
    seen=set()
    for q in queries:
        try: pages=search_wikitext(q,4)
        except Exception: continue
        for p in pages:
            title=p.get('title') or ''
            if not title or title in seen:continue
            seen.add(title); src=page_source(p); txt=title+' '+src
            ticker_ok=re.search(rf'(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])',txt,re.I) is not None
            market_ok=('Borsa İstanbul' in txt or 'Borsa Istanbul' in txt or re.search(r'\bBIST\b',txt,re.I) is not None)
            if ticker_ok and market_ok:
                ev=re.sub(r'\s+',' ',src[:400])
                return title,'AUTO_FULLSOURCE_TICKER_MARKET',ev[:240]
    return None,'UNAVAILABLE_OR_AMBIGUOUS',''


def pageviews_all(title,start,end):
    enc=urllib.parse.quote(title.replace(' ','_'),safe='')
    url=f"{PV_API}/{enc}/daily/{start.strftime('%Y%m%d')}00/{end.strftime('%Y%m%d')}00"
    obj=get_json(url,tries=5,timeout=25,backoff=2.0)
    d={}
    for x in obj.get('items',[]):
        ts=x.get('timestamp','')
        if len(ts)>=8:d[date(int(ts[:4]),int(ts[4:6]),int(ts[6:8]))]=int(x.get('views',0))
    return d


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

panel=extract_panel(); tickers=sorted({r['Ticker'] for r in panel}); titles=load_kap_titles()
print('tickers',len(tickers),'kap_titles',sum(t in titles for t in tickers),flush=True)
resolved={}
with ThreadPoolExecutor(max_workers=5) as ex:
    fut={ex.submit(resolve,t,titles.get(t,'')):t for t in tickers}
    for f in as_completed(fut):
        t=fut[f]
        try:resolved[t]=f.result()
        except Exception as e:resolved[t]=(None,'RESOLVE_API_ERROR',str(e)[:240])
        print('resolve',t,resolved[t][1],resolved[t][0] or '-',flush=True)

all_starts=[];all_ends=[]
for r in panel:
    cs=date.fromisoformat(r['CurrStart']);ce=date.fromisoformat(r['CurrEnd'])-timedelta(days=1)
    all_starts.append(cs-timedelta(days=28));all_ends.append(ce)
span_start=min(all_starts);span_end=max(all_ends)
unique_pages=sorted({v[0] for v in resolved.values() if v[0]});series={}
print('resolved_pages',len(unique_pages),'span',span_start,span_end,flush=True)
for i,p in enumerate(unique_pages,1):
    try:series[p]=pageviews_all(p,span_start,span_end);print('pv_ok',i,len(unique_pages),p,len(series[p]),flush=True)
    except Exception as e:series[p]=None;print('pv_fail',i,len(unique_pages),p,repr(e),flush=True)
    time.sleep(0.35)

with open(OUT_ENTITY,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f);w.writerow(['Ticker','KAPCompanyTitle','WikiPage','ResolveStatus','ResolveEvidence'])
    for t in tickers:
        p,s,e=resolved.get(t,(None,'UNAVAILABLE',''));w.writerow([t,titles.get(t,''),p or '',s,e])
out=[]
for r in panel:
    t=r['Ticker'];page,status,evidence=resolved.get(t,(None,'UNAVAILABLE',''))
    cs=date.fromisoformat(r['CurrStart']);ce=date.fromisoformat(r['CurrEnd'])-timedelta(days=1);bs=cs-timedelta(days=28);be=cs-timedelta(days=1)
    rec={'Week':r['Week'],'Freeze':r['Freeze'],'Ticker':t,'KAPCompanyTitle':titles.get(t,''),'WikiPage':page or '','ResolveStatus':status,'ResolveEvidence':evidence,'RowStatus':r['RowStatus'],'ExcessRet':r['ExcessRet'],'CurrStart':cs.isoformat(),'CurrEnd':ce.isoformat(),'BaseStart':bs.isoformat(),'BaseEnd':be.isoformat()}
    s=series.get(page) if page else None
    if page and s is not None:
        cv=[s.get(cs+timedelta(days=i),0) for i in range((ce-cs).days+1)];bv=[s.get(bs+timedelta(days=i),0) for i in range((be-bs).days+1)]
        cm=sum(cv)/len(cv);bm=sum(bv)/len(bv)
        rec.update(CurrViews=sum(cv),BaseViews=sum(bv),CurrDays=len(cv),BaseDays=len(bv),CurrDailyMean=cm,BaseDailyMean=bm,WikiShock7v28=math.log1p(cm)-math.log1p(bm),Coverage='OK')
    elif page:rec.update(Coverage='UNAVAILABLE_API')
    else:rec.update(Coverage='UNAVAILABLE')
    out.append(rec)
fields=[]
for r in out:
    for k in r:
        if k not in fields:fields.append(k)
with open(OUT_ROWS,'w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
weekly=[]
for week in sorted({r['Week'] for r in out}):
    denom=[r for r in panel if r['Week']==week and r['RowStatus']=='VALID']
    wr=[r for r in out if r['Week']==week and r.get('Coverage')=='OK' and r['RowStatus']=='VALID' and r.get('WikiShock7v28') is not None and r.get('ExcessRet') not in (None,'')]
    xs=[float(r['WikiShock7v28']) for r in wr];ys=[float(r['ExcessRet']) for r in wr]
    ic=spearman(xs,ys) if len(wr)>=5 and len(set(xs))>1 else None
    top=sorted(wr,key=lambda r:float(r['WikiShock7v28']),reverse=True)[:max(1,len(wr)//3)] if wr else []
    weekly.append({'Week':week,'CoveredN':len(wr),'CoveragePct':len(wr)/len(denom) if denom else None,'WikiRankIC':ic,'TopThirdExcess':sum(float(r['ExcessRet']) for r in top)/len(top) if top else None})
valid_ic=[x for x in weekly if x['WikiRankIC'] is not None]
weekly.append({'Week':'OVERALL_MEAN','CoveredN':sum(x['CoveredN'] for x in weekly),'CoveragePct':sum(x['CoveredN'] for x in weekly)/sum(1 for r in panel if r['RowStatus']=='VALID'),'WikiRankIC':sum(x['WikiRankIC'] for x in valid_ic)/len(valid_ic) if valid_ic else None,'TopThirdExcess':sum(x['TopThirdExcess'] for x in valid_ic)/len(valid_ic) if valid_ic else None})
with open(OUT_WEEKLY,'w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(weekly[0]));w.writeheader();w.writerows(weekly)
for x in weekly:print(x,flush=True)
