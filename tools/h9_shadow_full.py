#!/usr/bin/env python3
import csv, json, math, re, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone

BASE='https://www.kap.org.tr'; DISC=BASE+'/tr/api/disclosure/members/byCriteria'; IDX='33E5FED8013D00EAE0530A4A622B2AEA'
HEAD={'Origin':BASE,'Referer':BASE+'/tr/bildirim-sorgu','User-Agent':'Mozilla/5.0 (GPT-BORSA-H9 research)','Accept':'application/json, text/plain, */*','Accept-Language':'tr-TR,tr;q=0.9,en;q=0.8','Content-Type':'application/json'}
Q2_IN={'CVKMD','EUREN','PAHOL','PSGYO','SARKY'}; Q2_OUT={'EGEEN','KCAER','TSPOR','TTRAK','YEOTK'}
Q3_IN={'ESEN','IEYHO','ODINE'}; Q3_OUT={'AGHOL','TABGD','TUREX'}
TARGETS={(2025,'Yıllık',4):'2025-A',(2026,'3 Aylık',1):'2026-3A',(2026,'6 Aylık',2):'2026-6A'}
PRIOR={(2026,'3 Aylık',1):(2025,'3 Aylık',1),(2026,'6 Aylık',2):(2025,'6 Aylık',2)}


def post_kap(a,b,index='',tries=4):
    p={'fromDate':a,'toDate':b,'memberType':'IGS','mkkMemberOidList':[],'inactiveMkkMemberOidList':[],'disclosureClass':'','subjectList':[],'isLate':'','mainSector':'','sector':'','subSector':'','marketOid':'','index':index,'bdkReview':'','bdkMemberOidList':[],'year':'','term':'','ruleType':'','period':'','fromSrc':False,'srcCategory':'','disclosureIndexList':[]}
    body=json.dumps(p).encode(); last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(DISC,data=body,headers=HEAD,method='POST')
            with urllib.request.urlopen(req,timeout=60) as r:o=json.loads(r.read().decode())
            if isinstance(o,list):return o
            for k in ('data','list','result','items'):
                if isinstance(o.get(k),list):return o[k]
            return []
        except Exception as e:
            last=e; time.sleep(1.2*(i+1))
    raise last

def parse_dt(s):
    for f in ('%d.%m.%Y %H:%M:%S','%Y-%m-%dT%H:%M:%S','%Y-%m-%d %H:%M:%S'):
        try:return datetime.strptime(str(s)[:19],f)
        except:pass
    return None

def codes(s):return [x.strip().upper() for x in re.split(r'[,;/\s]+',str(s or '')) if x.strip()]

def collect_range(a,b,index='',chunk=7):
    out=[]; d=a
    while d<=b:
        e=min(d+timedelta(days=chunk-1),b); rows=post_kap(d.isoformat(),e.isoformat(),index); out.extend(rows)
        d=e+timedelta(days=1); time.sleep(.04)
    return out

def current_xu100():
    # Current KAP XU100 filter + broad window: every constituent is expected to have >=1 disclosure.
    rows=collect_range(date(2026,1,1),date(2026,8,11),IDX,7); s=set()
    for e in rows:
        for c in codes(e.get('stockCodes')):
            if re.fullmatch(r'[A-Z0-9]{3,6}',c):s.add(c)
    return s

def pit_sets(q3):
    q2=(set(q3)-Q3_IN)|Q3_OUT
    q1=(set(q2)-Q2_IN)|Q2_OUT
    return q1,q2,set(q3)

def pit_for(d,q1,q2,q3):
    return q1 if d<date(2026,4,1) else q2 if d<date(2026,7,1) else q3

def actual_fr(e):
    return str(e.get('disclosureCategory') or '').upper()=='FR' and str(e.get('subject') or '').strip().lower()=='finansal rapor'

def key_of(e):
    try:return (int(e.get('year')),str(e.get('ruleType') or ''),int(e.get('period')))
    except:return None

def choose_events(rows,allowed=None):
    # first original/non-corrected actual FR per ticker+period. Corrections retained separately in diagnostics.
    grouped={}
    for e in rows:
        if not actual_fr(e):continue
        k=key_of(e)
        if allowed is not None and k not in allowed:continue
        dt=parse_dt(e.get('publishDate'))
        if not dt:continue
        for t in codes(e.get('stockCodes')):
            grouped.setdefault((t,k),[]).append((dt,e))
    chosen={}; meta={}
    for kk,evs in grouped.items():
        evs.sort(key=lambda z:z[0]); originals=[z for z in evs if not z[1].get('modifyStatus')]
        if originals: chosen[kk]=originals[0][1]; meta[kk]={'n':len(evs),'corrections':len(evs)-len(originals)}
        else: meta[kk]={'n':len(evs),'corrections':len(evs),'only_corrected':1}
    return chosen,meta

ESC=[('\\u003c','<'),('\\u003e','>'),('\\u0026','&'),('\\u0027',"'"),('\\u0022','"'),('\\/','/')]
def fetch_page(did,tries=3):
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(BASE+'/tr/Bildirim/'+str(did),headers={'User-Agent':'Mozilla/5.0','Accept-Language':'tr-TR,tr;q=0.9'})
            with urllib.request.urlopen(req,timeout=70) as r:s=r.read().decode('utf-8','replace')
            for a,b in ESC:s=s.replace(a,b)
            s=s.replace('\\"','"')
            return s
        except Exception as e:last=e;time.sleep(1+i)
    raise last

def row_values(s,field_prefix):
    # Find taxonomy row by exact field prefix and extract raw numeric title attributes from context-value cells.
    p=s.find(field_prefix)
    if p<0:return None
    a=s.rfind('<tr',max(0,p-1000),p); b=s.find('</tr>',p)
    if a<0 or b<0:return None
    row=s[a:b+5]
    vals=[]
    # context cells only; title contains machine numeric value
    for td in re.findall(r'<td[^>]*class="[^"]*taxonomy-context-value[^"]*"[^>]*>(.*?)</td>',row,re.S|re.I):
        m=re.search(r'title="\s*(-?[0-9]+(?:\.[0-9]+)?)\s*"',td)
        if m:vals.append(float(m.group(1)))
    return vals

def report_fields(s):
    # Consolidated owners-of-parent profit is preferred; comprehensive income is intentionally excluded.
    earn_type='OWNER'
    ev=row_values(s,'ifrs-full_ProfitLossAttributableToOwnersOfParent|')
    if not ev or len(ev)<2:
        earn_type='PROFITLOSS'
        ev=row_values(s,'ifrs-full_ProfitLoss|')
    if not ev or len(ev)<2:
        earn_type='NETPERIOD_FALLBACK'
        ev=row_values(s,'kap-fr_CurrentPeriodNetProfitOrLossClassifiedInEquity|')
    av=row_values(s,'ifrs-full_Assets|')
    if not av:
        # fallback by label, restricted to row containing TOPLAM VARLIKLAR / Total assets
        mm=re.search(r'<tr[^>]*>.*?(?:TOPLAM VARLIKLAR|Total assets).*?</tr>',s,re.S|re.I)
        if mm:
            av=[]
            for td in re.findall(r'<td[^>]*class="[^"]*taxonomy-context-value[^"]*"[^>]*>(.*?)</td>',mm.group(0),re.S|re.I):
                m=re.search(r'title="\s*(-?[0-9]+(?:\.[0-9]+)?)\s*"',td)
                if m:av.append(float(m.group(1)))
    return {'earn_type':earn_type,'ni_current':ev[0] if ev and len(ev)>0 else None,'ni_prior':ev[1] if ev and len(ev)>1 else None,'assets_current':av[0] if av else None,'assets_prior':av[1] if av and len(av)>1 else None}

def fetch_reports(ids):
    out={}
    def one(i):
        try:return i,report_fields(fetch_page(i)),None
        except Exception as e:return i,None,repr(e)
    with ThreadPoolExecutor(max_workers=10) as ex:
        fut=[ex.submit(one,i) for i in sorted(set(ids))]
        for j,f in enumerate(as_completed(fut),1):
            i,v,e=f.result(); out[i]={'fields':v,'error':e}
            if j%25==0:print('REPORTS',j,'/',len(fut),flush=True)
    return out

def yahoo_series(sym,start=date(2025,12,1),end=date(2026,8,19),tries=3):
    p1=int(datetime(start.year,start.month,start.day,tzinfo=timezone.utc).timestamp()); p2=int(datetime(end.year,end.month,end.day,tzinfo=timezone.utc).timestamp())
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=history&includeAdjustedClose=true'
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=35) as r:o=json.loads(r.read().decode())
            res=o['chart']['result'][0]; ts=res.get('timestamp') or []; q=res['indicators']['quote'][0]; adj=(res['indicators'].get('adjclose') or [{}])[0].get('adjclose') or q.get('close')
            d={}
            for t,v in zip(ts,adj):
                if v is not None:d[datetime.fromtimestamp(t,timezone.utc).date()]=float(v)
            return d
        except Exception as e:last=e;time.sleep(1+i)
    raise last

def fetch_prices(tickers):
    out={}
    def one(t):
        syms=[t+'.IS'] if t!='__INDEX__' else ['XU100.IS','^XU100']
        for s in syms:
            try:
                v=yahoo_series(s)
                if len(v)>20:return t,v,s,None
            except Exception as e:last=e
        return t,{},syms[-1],repr(last)
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut=[ex.submit(one,t) for t in sorted(set(tickers)|{'__INDEX__'})]
        for j,f in enumerate(as_completed(fut),1):
            t,v,s,e=f.result();out[t]={'series':v,'symbol':s,'error':e}
            if j%25==0:print('PRICES',j,'/',len(fut),flush=True)
    return out

def ret(a,b):return (b/a-1) if a and b else None

def event_returns(event_dt,stock,index):
    common=sorted(set(stock)&set(index)); d=event_dt.date(); pre=[x for x in common if x<d]; post=[x for x in common if x>d]
    if len(pre)<6 or len(post)<6:return None
    t0=pre[-1]; tm5=pre[-6]; t1=post[0]; t5=post[5]
    ir=ret(stock[t0],stock[t1])-ret(index[t0],index[t1])
    pr=ret(stock[tm5],stock[t0])-ret(index[tm5],index[t0])
    fw=ret(stock[t1],stock[t5])-ret(index[t1],index[t5])
    return {'Tminus5':tm5,'T0':t0,'T1':t1,'T5':t5,'InitialExcess':ir,'Prior5Excess':pr,'Forward5Excess':fw}

def ranks(vals):
    n=len(vals); order=sorted(range(n),key=lambda i: vals[i]); r=[0.0]*n;i=0
    while i<n:
        j=i+1
        while j<n and vals[order[j]]==vals[order[i]]:j+=1
        avg=(i+j-1)/2
        pct=0.5 if n==1 else avg/(n-1)
        for k in range(i,j):r[order[k]]=pct
        i=j
    return r

def spearman(x,y):
    if len(x)<3 or len(set(x))<2 or len(set(y))<2:return None
    rx=ranks(x);ry=ranks(y);mx=sum(rx)/len(rx);my=sum(ry)/len(ry)
    a=[z-mx for z in rx];b=[z-my for z in ry];den=(sum(z*z for z in a)*sum(z*z for z in b))**.5
    return sum(u*v for u,v in zip(a,b))/den if den else None

def mean(v):return sum(v)/len(v) if v else None

def fmt(x):return '' if x is None else x

print('STEP universe',flush=True)
q3=current_xu100(); print('CURRENT_XU100',len(q3),sorted(q3),flush=True)
if len(q3)!=100: raise SystemExit(f'GATE FAIL: current XU100 union={len(q3)}, expected 100')
q1,q2,q3=pit_sets(q3)
if not(len(q1)==len(q2)==len(q3)==100):raise SystemExit('GATE FAIL: PIT quarter sets not 100')
print('PIT_Q1_Q2_Q3',len(q1),len(q2),len(q3),flush=True)

print('STEP current FR events',flush=True)
rows26=collect_range(date(2026,1,1),date(2026,8,11),'',7); chosen26,meta26=choose_events(rows26,set(TARGETS))
events=[]
for (t,k),e in chosen26.items():
    dt=parse_dt(e['publishDate']);
    if t in pit_for(dt.date(),q1,q2,q3):
        events.append({'ticker':t,'period_key':k,'cohort':TARGETS[k],'event':e,'dt':dt})
print('PIT_TARGET_EVENTS',len(events),{c:sum(1 for x in events if x['cohort']==c) for c in set(TARGETS.values())},flush=True)

print('STEP prior-year FR map',flush=True)
rows25=collect_range(date(2025,1,1),date(2025,9,30),'',7); prior_allowed={(2025,'3 Aylık',1),(2025,'6 Aylık',2)}; chosen25,meta25=choose_events(rows25,prior_allowed)

ids=[]
for x in events:
    ids.append(int(x['event']['disclosureIndex']))
    pk=PRIOR.get(x['period_key'])
    if pk and (x['ticker'],pk) in chosen25:ids.append(int(chosen25[(x['ticker'],pk)]['disclosureIndex']))
print('REPORT_IDS',len(set(ids)),flush=True)
rep=fetch_reports(ids)

print('STEP prices',flush=True)
prices=fetch_prices({x['ticker'] for x in events}); idx=prices['__INDEX__']['series']
if len(idx)<100:raise SystemExit('GATE FAIL: XU100 price series unavailable')

out=[]
for x in events:
    t=x['ticker']; k=x['period_key']; e=x['event']; did=int(e['disclosureIndex']); cur=rep.get(did,{}).get('fields') or {}; status='VALID'; reason=[]
    ni=cur.get('ni_current'); nip=cur.get('ni_prior'); assets_prev=None; prior_did=None; prior_type=None
    if k==(2025,'Yıllık',4): assets_prev=cur.get('assets_prior')
    else:
        pk=PRIOR[k]; pe=chosen25.get((t,pk))
        if pe:
            prior_did=int(pe['disclosureIndex']); pf=rep.get(prior_did,{}).get('fields') or {}; assets_prev=pf.get('assets_current'); prior_type=pf.get('earn_type')
            if cur.get('earn_type') and prior_type and cur.get('earn_type')!=prior_type: reason.append('FINANCIAL_TYPE_MISMATCH')
        else: reason.append('NO_PRIOR_SAME_PERIOD_REPORT')
    if ni is None or nip is None:reason.append('NI_MISSING')
    if assets_prev is None or assets_prev==0:reason.append('ASSETS_PREV_MISSING')
    sue=(ni-nip)/abs(assets_prev) if ni is not None and nip is not None and assets_prev not in (None,0) else None
    ps=prices.get(t,{}).get('series') or {}; rr=event_returns(x['dt'],ps,idx) if ps and idx else None
    if not rr:reason.append('PRICE_WINDOW_MISSING')
    if reason:status='UNAVAILABLE'
    out.append({'Cohort':x['cohort'],'Ticker':t,'DisclosureIndex':did,'PublishDate':e['publishDate'],'RuleType':e.get('ruleType'),'Period':e.get('period'),'ModifyStatus':e.get('modifyStatus'),'EarnField':cur.get('earn_type'),'NI_Current':ni,'NI_PriorSamePeriod':nip,'PriorReportIndex':prior_did,'PriorEarnField':prior_type,'Assets_PriorSamePeriod':assets_prev,'SUEraw':sue,'Tminus5':rr and rr['Tminus5'].isoformat(),'T0':rr and rr['T0'].isoformat(),'T1':rr and rr['T1'].isoformat(),'T5':rr and rr['T5'].isoformat(),'Prior5Excess':rr and rr['Prior5Excess'],'InitialExcess':rr and rr['InitialExcess'],'Forward5Excess':rr and rr['Forward5Excess'],'AbsorptionGap':None,'AlreadyPriced':None,'Status':status,'Reason':'|'.join(reason),'PriceSymbol':prices.get(t,{}).get('symbol')})

# rank within cohort only on valid rows; do not tune/delete based on outcome
for c in sorted({r['Cohort'] for r in out}):
    vv=[r for r in out if r['Cohort']==c and r['Status']=='VALID']
    if len(vv)>=3:
        rs=ranks([r['SUEraw'] for r in vv]); ri=ranks([r['InitialExcess'] for r in vv])
        for r,a,b in zip(vv,rs,ri):
            r['AbsorptionGap']=a-b; r['AlreadyPriced']=1 if ((1 if r['SUEraw']>0 else -1 if r['SUEraw']<0 else 0)*r['Prior5Excess']>0) else 0

summary=[]
for c in ['2025-A','2026-3A','2026-6A']:
    vv=[r for r in out if r['Cohort']==c and r['Status']=='VALID' and r['AbsorptionGap'] is not None]
    ic=spearman([r['AbsorptionGap'] for r in vv],[r['Forward5Excess'] for r in vv]) if vv else None
    top=sorted(vv,key=lambda r:r['AbsorptionGap'],reverse=True)[:max(1,math.ceil(len(vv)/3))] if vv else []
    bot=sorted(vv,key=lambda r:r['AbsorptionGap'])[:max(1,math.ceil(len(vv)/3))] if vv else []
    na=[r for r in vv if r['AlreadyPriced']==0]; aa=[r for r in vv if r['AlreadyPriced']==1]
    summary.append({'Cohort':c,'Events':sum(1 for r in out if r['Cohort']==c),'ValidN':len(vv),'Coverage':len(vv)/max(1,sum(1 for r in out if r['Cohort']==c)),'GapRankIC':ic,'TopThirdForwardExcess':mean([r['Forward5Excess'] for r in top]),'BottomThirdForwardExcess':mean([r['Forward5Excess'] for r in bot]),'TopMinusBottom':(mean([r['Forward5Excess'] for r in top])-mean([r['Forward5Excess'] for r in bot])) if top and bot else None,'NotAlreadyPricedN':len(na),'NotAlreadyPricedIC':spearman([r['AbsorptionGap'] for r in na],[r['Forward5Excess'] for r in na]) if len(na)>=3 else None,'AlreadyPricedN':len(aa),'AlreadyPricedIC':spearman([r['AbsorptionGap'] for r in aa],[r['Forward5Excess'] for r in aa]) if len(aa)>=3 else None})
valid_s=[r for r in summary if r['GapRankIC'] is not None]
summary.append({'Cohort':'MEAN_ACROSS_COHORTS','Events':sum(r['Events'] for r in summary),'ValidN':sum(r['ValidN'] for r in summary),'Coverage':sum(r['ValidN'] for r in summary)/max(1,sum(r['Events'] for r in summary)),'GapRankIC':mean([r['GapRankIC'] for r in valid_s]),'TopThirdForwardExcess':mean([r['TopThirdForwardExcess'] for r in valid_s]),'BottomThirdForwardExcess':mean([r['BottomThirdForwardExcess'] for r in valid_s]),'TopMinusBottom':mean([r['TopMinusBottom'] for r in valid_s]),'NotAlreadyPricedN':sum(r['NotAlreadyPricedN'] for r in valid_s),'NotAlreadyPricedIC':mean([r['NotAlreadyPricedIC'] for r in valid_s if r['NotAlreadyPricedIC'] is not None]),'AlreadyPricedN':sum(r['AlreadyPricedN'] for r in valid_s),'AlreadyPricedIC':mean([r['AlreadyPricedIC'] for r in valid_s if r['AlreadyPricedIC'] is not None])})

fields=list(out[0].keys()) if out else []
with open('h9_results.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
with open('h9_summary.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(summary[0].keys()));w.writeheader();w.writerows(summary)
with open('h9_universe.csv','w',newline='',encoding='utf-8') as f:
    w=csv.writer(f);w.writerow(['Quarter','Ticker'])
    for q,s in [('Q1',q1),('Q2',q2),('Q3',q3)]:
        for t in sorted(s):w.writerow([q,t])
coverage={}
for r in out:coverage[r['Reason'] or 'VALID']=coverage.get(r['Reason'] or 'VALID',0)+1
with open('h9_coverage.csv','w',newline='',encoding='utf-8') as f:
    w=csv.writer(f);w.writerow(['StatusReason','N']);w.writerows(sorted(coverage.items(),key=lambda x:-x[1]))
print('SUMMARY_JSON',json.dumps(summary,ensure_ascii=False,default=str),flush=True)
print('COVERAGE',coverage,flush=True)
