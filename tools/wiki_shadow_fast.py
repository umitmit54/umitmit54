#!/usr/bin/env python3
"""Fast conservative Wikimedia 12-week backfill for GPT BORSA v0.4.

Methodology is unchanged from A0-10:
- attention shock = log1p(current 7d daily mean pageviews) - log1p(prior 28d daily mean)
- no zero imputation for unresolved entities / failed API calls
- entity resolution is outcome-blind and conservative

Implementation optimization only:
1) KAP IGS/other member maps provide official ticker -> issuer title.
2) Wikidata Query Service resolves exact ticker symbols in one batch; a ticker is
   accepted only when it maps to exactly one Turkish-Wikipedia article.
3) Missing tickers get a bounded MediaWiki fallback using official KAP title.
4) Historical pageviews are fetched once per resolved article for the whole
   shadow period, then sliced locally into weekly 7d/prior28d windows.
"""
import ast, base64, csv, gzip, io, json, math, re, time
import urllib.parse, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

OLD_SOURCE='tools/news_shadow_collect.py'
OUT_ROWS='wiki_shadow_rows_fast.csv'
OUT_WEEKLY='wiki_shadow_weekly_fast.csv'
OUT_ENTITY='wiki_shadow_entity_map_fast.csv'
UA='GPT-BORSA-Shadow/0.4 (research; github.com/umitmit54)'
KAP_BASE='https://www.kap.org.tr'
KAP_COMPANY=KAP_BASE+'/tr/api/company/items'
WIKI_API='https://tr.wikipedia.org/w/api.php'
WDQS='https://query.wikidata.org/sparql'
PV_API='https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/tr.wikipedia/all-access/user'
KAP_HEADERS={
 'Origin':KAP_BASE,'Referer':KAP_BASE+'/tr/bildirim-sorgu',
 'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
 'Accept':'application/json, text/plain, */*','Accept-Language':'tr-TR,tr;q=0.9,en;q=0.8'
}


def get_json(url, headers=None, tries=2, timeout=22):
    h={'User-Agent':UA,'Accept':'application/json'}; h.update(headers or {})
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(url,headers=h)
            with urllib.request.urlopen(req,timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            last=e
            if i+1<tries: time.sleep(1.0*(i+1))
    raise last


def extract_panel():
    src=open(OLD_SOURCE,encoding='utf-8').read(); m=re.search(r'^PANEL_B64=(.+)$',src,re.M)
    b64=ast.literal_eval(m.group(1))
    return list(csv.DictReader(io.StringIO(gzip.decompress(base64.b64decode(b64)).decode('utf-8'))))


def load_kap_titles():
    out={}
    for typ in ['IGS','IGMS','KVS','HT','YK','PYS','BDK','DCS','DDK','DK','KVH']:
        try: rows=get_json(f'{KAP_COMPANY}/{typ}/A',KAP_HEADERS,tries=2,timeout=25)
        except Exception as e:
            print('WARN KAP',typ,e,flush=True); continue
        if isinstance(rows,dict): rows=rows.get('data') or rows.get('list') or []
        for r in rows:
            title=(r.get('kapMemberTitle') or r.get('memberTitle') or '').strip()
            codes=(r.get('stockCode') or r.get('stockCodes') or '')
            for code in re.split(r'[,;/\s]+',codes):
                code=code.strip().upper()
                if code and title: out[code]=title
    return out


def wdqs_batch(tickers):
    vals=' '.join(json.dumps(t,ensure_ascii=False) for t in tickers)
    q=f'''SELECT ?ticker ?item ?article WHERE {{
      VALUES ?ticker {{ {vals} }}
      ?item wdt:P249 ?ticker .
      ?article schema:about ?item ; schema:isPartOf <https://tr.wikipedia.org/> .
    }}'''
    url=WDQS+'?'+urllib.parse.urlencode({'query':q,'format':'json'})
    obj=get_json(url,{'Accept':'application/sparql-results+json'},tries=2,timeout=45)
    out=defaultdict(set)
    for b in obj.get('results',{}).get('bindings',[]):
        t=b.get('ticker',{}).get('value','').upper().strip(); a=b.get('article',{}).get('value','')
        if t and a:
            title=urllib.parse.unquote(a.rsplit('/',1)[-1]).replace('_',' ')
            out[t].add(title)
    return out


def wiki_generator_search(query,limit=5):
    params={'action':'query','generator':'search','gsrsearch':query,'gsrlimit':limit,
            'prop':'extracts','exintro':1,'explaintext':1,'redirects':1,'format':'json','utf8':1}
    obj=get_json(WIKI_API+'?'+urllib.parse.urlencode(params),tries=2,timeout=20)
    return list((obj.get('query',{}).get('pages') or {}).values())


def fallback_resolve(ticker,company):
    if not company: return None,'NO_KAP_TITLE',''
    for q in [f'"{company}" {ticker}', company]:
        try: pages=wiki_generator_search(q,5)
        except Exception as e: continue
        for p in pages:
            title=p.get('title') or ''; ex=p.get('extract') or ''; txt=title+' '+ex
            ticker_ok=re.search(rf'(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])',txt,re.I) is not None
            market_ok=('Borsa İstanbul' in txt or 'Borsa Istanbul' in txt or re.search(r'\bBIST\b',txt,re.I) is not None)
            if ticker_ok and market_ok: return title,'AUTO_EXPLICIT_TICKER_MARKET',ex[:240]
    return None,'UNAVAILABLE_OR_AMBIGUOUS',''


def pageviews_all(title,start,end):
    enc=urllib.parse.quote(title.replace(' ','_'),safe='')
    url=f"{PV_API}/{enc}/daily/{start.strftime('%Y%m%d')}00/{end.strftime('%Y%m%d')}00"
    obj=get_json(url,tries=2,timeout=25)
    return {date.fromisoformat(x['timestamp'][:4]+'-'+x['timestamp'][4:6]+'-'+x['timestamp'][6:8]):int(x.get('views',0)) for x in obj.get('items',[])}


def ranks(xs):
    order=sorted(range(len(xs)),key=lambda i:xs[i]); out=[0.0]*len(xs); i=0
    while i<len(order):
        j=i+1
        while j<len(order) and xs[order[j]]==xs[order[i]]: j+=1
        avg=(i+1+j)/2
        for k in range(i,j): out[order[k]]=avg
        i=j
    return out

def pearson(a,b):
    if len(a)<3:return None
    ma=sum(a)/len(a); mb=sum(b)/len(b); xa=[x-ma for x in a]; xb=[x-mb for x in b]
    den=(sum(x*x for x in xa)*sum(y*y for y in xb))**.5
    return None if den==0 else sum(x*y for x,y in zip(xa,xb))/den

def spearman(a,b): return pearson(ranks(a),ranks(b))

panel=extract_panel(); tickers=sorted({r['Ticker'] for r in panel}); titles=load_kap_titles()
print('tickers',len(tickers),'kap_titles',sum(t in titles for t in tickers),flush=True)

resolved={}
try:
    wdm=wdqs_batch(tickers)
    print('wdqs_tickers_with_trwiki',len(wdm),flush=True)
except Exception as e:
    print('WARN WDQS failed',repr(e),flush=True); wdm={}

fallback=[]
for t in tickers:
    arts=sorted(wdm.get(t,set()))
    if len(arts)==1:
        resolved[t]=(arts[0],'WIKIDATA_EXACT_TICKER_UNIQUE_TRWIKI','')
    elif len(arts)>1:
        resolved[t]=(None,'WIKIDATA_AMBIGUOUS_MULTI_TRWIKI','|'.join(arts)[:240])
    else:
        fallback.append(t)

print('wdqs_unique',sum(1 for v in resolved.values() if v[0]),'fallback',len(fallback),flush=True)
with ThreadPoolExecutor(max_workers=6) as ex:
    fut={ex.submit(fallback_resolve,t,titles.get(t,'')):t for t in fallback}
    for f in as_completed(fut):
        t=fut[f]
        try: resolved[t]=f.result()
        except Exception as e: resolved[t]=(None,'RESOLVE_API_ERROR',str(e)[:240])
        print('resolve',t,resolved[t][1],resolved[t][0] or '-',flush=True)

# Whole-period pageviews: one call per resolved page.
all_starts=[]; all_ends=[]
for r in panel:
    cs=date.fromisoformat(r['CurrStart']); ce=date.fromisoformat(r['CurrEnd'])-timedelta(days=1)
    all_starts.append(cs-timedelta(days=28)); all_ends.append(ce)
span_start=min(all_starts); span_end=max(all_ends)
series={}
unique_pages=sorted({v[0] for v in resolved.values() if v[0]})
print('resolved_pages',len(unique_pages),'span',span_start,span_end,flush=True)
with ThreadPoolExecutor(max_workers=6) as ex:
    fut={ex.submit(pageviews_all,p,span_start,span_end):p for p in unique_pages}
    for f in as_completed(fut):
        p=fut[f]
        try: series[p]=f.result(); print('pv_ok',p,len(series[p]),flush=True)
        except Exception as e: series[p]=None; print('pv_fail',p,repr(e),flush=True)

with open(OUT_ENTITY,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['Ticker','KAPCompanyTitle','WikiPage','ResolveStatus','ResolveEvidence'])
    for t in tickers:
        p,s,e=resolved.get(t,(None,'UNAVAILABLE','')); w.writerow([t,titles.get(t,''),p or '',s,e])

out=[]
for r in panel:
    t=r['Ticker']; page,status,evidence=resolved.get(t,(None,'UNAVAILABLE',''))
    cs=date.fromisoformat(r['CurrStart']); ce=date.fromisoformat(r['CurrEnd'])-timedelta(days=1)
    bs=cs-timedelta(days=28); be=cs-timedelta(days=1)
    rec={'Week':r['Week'],'Freeze':r['Freeze'],'Ticker':t,'KAPCompanyTitle':titles.get(t,''),'WikiPage':page or '',
         'ResolveStatus':status,'ResolveEvidence':evidence,'RowStatus':r['RowStatus'],'ExcessRet':r['ExcessRet'],
         'CurrStart':cs.isoformat(),'CurrEnd':ce.isoformat(),'BaseStart':bs.isoformat(),'BaseEnd':be.isoformat()}
    s=series.get(page) if page else None
    if page and s is not None:
        cv=[s.get(cs+timedelta(days=i),0) for i in range((ce-cs).days+1)]
        bv=[s.get(bs+timedelta(days=i),0) for i in range((be-bs).days+1)]
        if len(cv)>=6 and len(bv)>=24:
            cm=sum(cv)/len(cv); bm=sum(bv)/len(bv)
            rec.update(CurrViews=sum(cv),BaseViews=sum(bv),CurrDays=len(cv),BaseDays=len(bv),CurrDailyMean=cm,BaseDailyMean=bm,
                       WikiShock7v28=math.log1p(cm)-math.log1p(bm),Coverage='OK')
        else: rec.update(Coverage='LOW')
    elif page: rec.update(Coverage='UNAVAILABLE_API')
    else: rec.update(Coverage='UNAVAILABLE')
    out.append(rec)

fields=[]
for r in out:
    for k in r:
        if k not in fields: fields.append(k)
with open(OUT_ROWS,'w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(out)

weekly=[]
for week in sorted({r['Week'] for r in out}):
    denom=[r for r in panel if r['Week']==week and r['RowStatus']=='VALID']
    wr=[r for r in out if r['Week']==week and r.get('Coverage')=='OK' and r['RowStatus']=='VALID' and r.get('WikiShock7v28') is not None and r.get('ExcessRet') not in (None,'')]
    xs=[float(r['WikiShock7v28']) for r in wr]; ys=[float(r['ExcessRet']) for r in wr]
    ic=spearman(xs,ys) if len(wr)>=5 and len(set(xs))>1 else None
    top=sorted(wr,key=lambda r:float(r['WikiShock7v28']),reverse=True)[:max(1,len(wr)//3)] if wr else []
    weekly.append({'Week':week,'CoveredN':len(wr),'CoveragePct':len(wr)/len(denom) if denom else None,
                   'WikiRankIC':ic,'TopThirdExcess':sum(float(r['ExcessRet']) for r in top)/len(top) if top else None})
valid_ic=[x for x in weekly if x['WikiRankIC'] is not None]
weekly.append({'Week':'OVERALL_MEAN','CoveredN':sum(x['CoveredN'] for x in weekly),
               'CoveragePct':sum(x['CoveredN'] for x in weekly)/sum(1 for r in panel if r['RowStatus']=='VALID'),
               'WikiRankIC':sum(x['WikiRankIC'] for x in valid_ic)/len(valid_ic) if valid_ic else None,
               'TopThirdExcess':sum(x['TopThirdExcess'] for x in valid_ic)/len(valid_ic) if valid_ic else None})
with open(OUT_WEEKLY,'w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(weekly[0])); w.writeheader(); w.writerows(weekly)
for x in weekly: print(x,flush=True)
