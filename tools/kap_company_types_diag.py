#!/usr/bin/env python3
import json, urllib.request
BASE='https://www.kap.org.tr'; H={'Origin':BASE,'Referer':BASE+'/tr/bildirim-sorgu','User-Agent':'Mozilla/5.0 Chrome/124 Safari/537.36','Accept':'application/json, text/plain, */*'}
targets={'ASELS','BIMAS','AKBNK','EREGL','GARAN','THYAO','TUPRS','KCHOL','TCELL','SISE','PETKM','ASTOR','GESAN','SOKM','ARCLK','MGROS','PGSUS','FROTO'}
out={}
for typ in ['IGS','IGMS','KVS','HT','YK','PYS','DK','KVH']:
    url=f'{BASE}/tr/api/company/items/{typ}/A'
    try:
        req=urllib.request.Request(url,headers=H)
        with urllib.request.urlopen(req,timeout=30) as r: obj=json.loads(r.read().decode('utf-8'))
        rows=obj if isinstance(obj,list) else (obj.get('data') or obj.get('list') or []) if isinstance(obj,dict) else []
        hits=[]
        for x in rows:
            codes=str(x.get('stockCode') or x.get('stockCodes') or '')
            split={c.strip().upper() for c in codes.replace(';',',').split(',') if c.strip()}
            if split & targets:hits.append({'stockCode':codes,'kapMemberTitle':x.get('kapMemberTitle'),'kapMemberType':x.get('kapMemberType'),'kapTypes':x.get('kapTypes')})
        out[typ]={'count':len(rows),'hits':hits[:30]}
    except Exception as e:out[typ]={'error':repr(e)}
open('kap_company_types_diag.json','w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False,indent=2),flush=True)
