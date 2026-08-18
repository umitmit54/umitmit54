#!/usr/bin/env python3
import csv, math, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET, gzip, base64, io
from datetime import datetime, date, timedelta
from collections import defaultdict

PANEL_B64='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'
OUT_ROWS='news_shadow_rows.csv'
OUT_WEEKLY='news_shadow_weekly.csv'
USER_AGENT='GPT-BORSA-Shadow/0.4 research-contact github.com/umitmit54'
ALIASES={'ASELS':'("ASELSAN" OR ASELS)','BIMAS':'("Bim Birlesik Magazalar" OR BIMAS)','AKBNK':'(Akbank OR AKBNK)','EREGL':'("Eregli Demir ve Celik" OR EREGL)','GARAN':'("Garanti BBVA" OR GARAN)'}
def fetch(url, tries=4):
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(url, headers={'User-Agent':USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as r:return r.read()
        except Exception as e:
            last=e; time.sleep(1.5*(i+1))
    raise last
def parse_pubdate(text):return datetime.strptime(text,'%a, %d %b %Y %H:%M:%S %Z').date()
def news_query(ticker):return ALIASES.get(ticker,f'"{ticker}" hisse')
def month_starts(d0,d1):
    cur=date(d0.year,d0.month,1)
    while cur<=d1:
        nxt=date(cur.year+1,1,1) if cur.month==12 else date(cur.year,cur.month+1,1)
        yield cur,nxt;cur=nxt
def rss_for_ticker(ticker,global_start,global_end):
    items=[];seen=set();qbase=news_query(ticker)
    for mstart,mnext in month_starts(global_start,global_end):
        qs=max(global_start,mstart);qe=min(global_end+timedelta(days=1),mnext)
        if qs>=qe:continue
        q=f'{qbase} after:{qs.isoformat()} before:{qe.isoformat()}'
        url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q,'hl':'tr','gl':'TR','ceid':'TR:tr'})
        try:
            root=ET.fromstring(fetch(url))
            for it in root.findall('.//item'):
                title=(it.findtext('title') or '').strip();pub=(it.findtext('pubDate') or '').strip();src=it.find('source');source=(src.text or '').strip() if src is not None else ''
                if not title or not pub:continue
                try:d=parse_pubdate(pub)
                except:continue
                key=(title.lower(),source.lower(),d.isoformat())
                if key in seen:continue
                seen.add(key);items.append({'date':d,'title':title,'source':source})
        except Exception as e:print(f'WARN {ticker} {qs}..{qe}: {e}',flush=True)
        time.sleep(.15)
    return items
def ranks(xs):
    order=sorted(range(len(xs)),key=lambda i:xs[i]);r=[0.0]*len(xs);i=0
    while i<len(order):
        j=i+1
        while j<len(order) and xs[order[j]]==xs[order[i]]:j+=1
        avg=(i+1+j)/2
        for k in range(i,j):r[order[k]]=avg
        i=j
    return r
def pearson(a,b):
    if len(a)<3:return None
    ma=sum(a)/len(a);mb=sum(b)/len(b);xa=[x-ma for x in a];xb=[x-mb for x in b];den=(sum(x*x for x in xa)*sum(y*y for y in xb))**.5
    return None if den==0 else sum(x*y for x,y in zip(xa,xb))/den
def spearman(a,b):return pearson(ranks(a),ranks(b))
def fnum(x):
    try:return float(x)
    except:return None
rows=[];panel_text=gzip.decompress(base64.b64decode(PANEL_B64)).decode()
for r in csv.DictReader(io.StringIO(panel_text)):
    for c in ['CurrStart','CurrEnd','PrevStart','PrevEnd']:r[c+'D']=date.fromisoformat(r[c])
    rows.append(r)
valid=[r for r in rows if r['RowStatus']=='VALID'];g0=min(r['PrevStartD'] for r in valid);g1=max(r['CurrEndD'] for r in valid)-timedelta(days=1);tickers=sorted({r['Ticker'] for r in valid})
print(len(valid),len(tickers),g0,g1,flush=True);cache={}
for i,t in enumerate(tickers,1):cache[t]=rss_for_ticker(t,g0,g1);print(i,len(tickers),t,len(cache[t]),flush=True)
out=[]
for r in rows:
    items=cache.get(r['Ticker'],[]);curr=[x for x in items if r['CurrStartD']<=x['date']<r['CurrEndD']];prev=[x for x in items if r['PrevStartD']<=x['date']<r['PrevEndD']]
    relay=('kap','kamuyu aydınlatma','kamuyu aydinlatma');ci=len(curr)-sum(any(z in x['title'].lower() for z in relay) for x in curr);pi=len(prev)-sum(any(z in x['title'].lower() for z in relay) for x in prev)
    d={k:r[k] for k in ['Week','Freeze','Ticker','ExcessRet','CAFlag','RowStatus','CurrStart','CurrEnd','PrevStart','PrevEnd']};d.update(NewsQuery=news_query(r['Ticker']),NewsCurr=len(curr),NewsPrev=len(prev),NewsShock=math.log1p(len(curr))-math.log1p(len(prev)),NewsCurrSources=len({x['source'] for x in curr if x['source']}),NewsPrevSources=len({x['source'] for x in prev if x['source']}),NewsCurrIndependent=ci,NewsPrevIndependent=pi,NewsIndependentShock=math.log1p(ci)-math.log1p(pi));out.append(d)
with open(OUT_ROWS,'w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
weekly=[]
for week in sorted({r['Week'] for r in out}):
    wr=[r for r in out if r['Week']==week and r['RowStatus']=='VALID' and fnum(r['ExcessRet']) is not None];ys=[float(r['ExcessRet']) for r in wr];xs=[float(r['NewsShock']) for r in wr];ix=[float(r['NewsIndependentShock']) for r in wr];top=sorted(wr,key=lambda r:float(r['NewsShock']),reverse=True)[:10];itop=sorted(wr,key=lambda r:float(r['NewsIndependentShock']),reverse=True)[:10]
    weekly.append({'Week':week,'N':len(wr),'NewsRankIC':spearman(xs,ys),'NewsTop10Excess':sum(float(r['ExcessRet']) for r in top)/len(top),'IndependentNewsRankIC':spearman(ix,ys),'IndependentNewsTop10Excess':sum(float(r['ExcessRet']) for r in itop)/len(itop),'TotalCurrNews':sum(int(r['NewsCurr']) for r in wr),'TotalPrevNews':sum(int(r['NewsPrev']) for r in wr)})
base=list(weekly);weekly.append({'Week':'OVERALL_MEAN','N':sum(r['N'] for r in base),'NewsRankIC':sum(r['NewsRankIC'] for r in base)/len(base),'NewsTop10Excess':sum(r['NewsTop10Excess'] for r in base)/len(base),'IndependentNewsRankIC':sum(r['IndependentNewsRankIC'] for r in base)/len(base),'IndependentNewsTop10Excess':sum(r['IndependentNewsTop10Excess'] for r in base)/len(base),'TotalCurrNews':sum(r['TotalCurrNews'] for r in base),'TotalPrevNews':sum(r['TotalPrevNews'] for r in base)})
with open(OUT_WEEKLY,'w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(weekly[0]));w.writeheader();w.writerows(weekly)
for r in weekly:print(r,flush=True)
