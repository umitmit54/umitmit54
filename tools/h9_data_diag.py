#!/usr/bin/env python3
import json,time,urllib.request,datetime as dt
BASE='https://www.kap.org.tr'; END=BASE+'/tr/api/disclosure/members/byCriteria'; IDX='33E5FED8013D00EAE0530A4A622B2AEA'
HEAD={'Origin':BASE,'Referer':BASE+'/tr/bildirim-sorgu','User-Agent':'Mozilla/5.0','Accept':'application/json, text/plain, */*','Content-Type':'application/json'}
def post(a,b,index=''):
 p={'fromDate':a,'toDate':b,'memberType':'IGS','mkkMemberOidList':[],'inactiveMkkMemberOidList':[],'disclosureClass':'','subjectList':[],'isLate':'','mainSector':'','sector':'','subSector':'','marketOid':'','index':index,'bdkReview':'','bdkMemberOidList':[],'year':'','term':'','ruleType':'','period':'','fromSrc':False,'srcCategory':'','disclosureIndexList':[]}
 req=urllib.request.Request(END,data=json.dumps(p).encode(),headers=HEAD,method='POST')
 with urllib.request.urlopen(req,timeout=60) as r:o=json.loads(r.read().decode())
 if isinstance(o,list):return o
 for k in ('data','list','result','items'):
  if isinstance(o.get(k),list):return o[k]
 return []
# current XU100 membership inferred from official KAP current index filter across many chunks
t=set(); d=dt.date(2026,1,1); end=dt.date(2026,8,11)
while d<=end:
 b=min(d+dt.timedelta(days=6),end); rows=post(d.isoformat(),b.isoformat(),IDX)
 for e in rows:
  for x in str(e.get('stockCodes') or '').replace(',',' ').split():
   if x.isalpha() and 3<=len(x)<=6:t.add(x)
 print('INDEX_CHUNK',d,b,len(rows),'UNION',len(t),flush=True); d=b+dt.timedelta(days=1); time.sleep(.05)
print('CURRENT_XU100_COUNT',len(t)); print('CURRENT_XU100',','.join(sorted(t)))
# Yahoo price diagnostics
def yahoo(sym):
 p1=int(dt.datetime(2026,7,20,tzinfo=dt.timezone.utc).timestamp());p2=int(dt.datetime(2026,8,18,tzinfo=dt.timezone.utc).timestamp())
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=history&includeAdjustedClose=true'
 req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
 try:
  with urllib.request.urlopen(req,timeout=30) as r:o=json.loads(r.read().decode())
  res=o['chart']['result'][0]; print('YAHOO',sym,'N',len(res.get('timestamp') or []),'META_SYMBOL',res.get('meta',{}).get('symbol'),'ERR',o['chart'].get('error'))
 except Exception as e: print('YAHOO_FAIL',sym,repr(e))
for s in ['ASELS.IS','GARAN.IS','XU100.IS','^XU100']:yahoo(s)
