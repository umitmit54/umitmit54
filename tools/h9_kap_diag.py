#!/usr/bin/env python3
import json, urllib.request, time
from datetime import date,timedelta
BASE='https://www.kap.org.tr'
HEAD={'Origin':BASE,'Referer':BASE+'/tr/bildirim-sorgu','User-Agent':'Mozilla/5.0','Accept':'application/json, text/plain, */*','Accept-Language':'tr-TR,tr;q=0.9,en;q=0.8','Content-Type':'application/json'}

def get(url):
    req=urllib.request.Request(url,headers={k:v for k,v in HEAD.items() if k!='Content-Type'})
    with urllib.request.urlopen(req,timeout=45) as r:return json.loads(r.read().decode())

def post(a,b):
    payload={'fromDate':a,'toDate':b,'memberType':'','mkkMemberOidList':[],'inactiveMkkMemberOidList':[],'disclosureClass':'','subjectList':[],'isLate':'','mainSector':'','sector':'','subSector':'','marketOid':'','index':'','bdkReview':'','bdkMemberOidList':[],'year':'','term':'','ruleType':'','period':'','fromSrc':False,'srcCategory':'','disclosureIndexList':[]}
    req=urllib.request.Request(BASE+'/tr/api/disclosure/members/byCriteria',data=json.dumps(payload).encode(),headers=HEAD,method='POST')
    with urllib.request.urlopen(req,timeout=60) as r:
        obj=json.loads(r.read().decode())
    if isinstance(obj,list):return obj
    for k in ('data','list','result','items'):
        if isinstance(obj.get(k),list):return obj[k]
    return []

# company issuer schema
rows=get(BASE+'/tr/api/company/items/IGS/A')
print('COMPANY_ROWS',len(rows))
for r in rows[:3]: print('COMPANY_SAMPLE',json.dumps(r,ensure_ascii=False)[:2000])
for t in ['ASELS','GARAN','TUPRS']:
    hit=[r for r in rows if t in str(r.get('stockCode','')).split(',') or t in str(r)]
    print('COMPANY_HIT',t,json.dumps(hit[:1],ensure_ascii=False)[:3000])

# sample financial-report events in chunks
allfr=[]
d=date(2026,1,1)
end=date(2026,8,11)
while d<=end:
    b=min(d+timedelta(days=6),end)
    ev=post(d.isoformat(),b.isoformat())
    fr=[]
    for e in ev:
        s=' '.join(str(e.get(k) or '') for k in ['subject','disclosureType','disclosureClass','summary','term','period','year']).lower()
        if 'finansal rapor' in s or str(e.get('disclosureType','')).upper()=='FR': fr.append(e)
    if fr:
        print('CHUNK',d,b,'ALL',len(ev),'FR',len(fr))
        for e in fr[:2]: print('FR_SAMPLE',json.dumps(e,ensure_ascii=False)[:4000])
        allfr.extend(fr)
    d=b+timedelta(days=1); time.sleep(.15)
print('FR_TOTAL',len(allfr))
# unique keys
keys=sorted({k for e in allfr for k in e})
print('FR_KEYS',keys)
