#!/usr/bin/env python3
import json, urllib.request
BASE='https://www.kap.org.tr'
H={'Origin':BASE,'Referer':BASE+'/tr/bildirim-sorgu','User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36','Accept':'application/json, text/plain, */*'}
out={}
for typ in ['HT','YK','PYS','BDK','DCS','DDK','DK','KVH']:
    url=f'{BASE}/tr/api/company/items/{typ}/A'
    try:
        req=urllib.request.Request(url,headers=H)
        with urllib.request.urlopen(req,timeout=30) as r: obj=json.loads(r.read().decode('utf-8'))
        if isinstance(obj,list): sample=obj[:3]
        elif isinstance(obj,dict): sample={'keys':list(obj.keys()),'values':{k:(v[:3] if isinstance(v,list) else v if not isinstance(v,(dict,list)) else {'type':type(v).__name__,'keys':list(v.keys())[:20]} ) for k,v in list(obj.items())[:20]}}
        else: sample={'type':type(obj).__name__,'repr':repr(obj)[:500]}
        out[typ]={'type':type(obj).__name__,'sample':sample}
    except Exception as e:out[typ]={'error':repr(e)}
open('kap_company_diag.json','w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False,indent=2),flush=True)
