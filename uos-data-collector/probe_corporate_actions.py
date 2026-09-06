import json, requests
from pathlib import Path
out=Path('uos-data-collector/corp_probe'); out.mkdir(parents=True,exist_ok=True)
s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0'})
sym='AKBNK'
page=f'https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/sirket-karti.aspx?hisse={sym}'
r={}
try:
    p=s.get(page,timeout=20); r['page']={'status':p.status_code,'bytes':len(p.content),'cookies':list(s.cookies.keys())}
except Exception as e:r['page']={'error':repr(e)}
url='https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/StockInfo/CompanyInfoAjax.aspx/GetSermayeArttirimlari'
headers={'Content-Type':'application/json; charset=UTF-8','Accept':'application/json, text/javascript, */*; q=0.01','X-Requested-With':'XMLHttpRequest','Referer':page,'Origin':'https://www.isyatirim.com.tr'}
payload={'hisseKodu':sym,'hisseTanimKodu':'','yil':0,'zaman':'HEPSI','endeksKodu':'09','sektorKodu':''}
try:
    q=s.post(url,json=payload,headers=headers,timeout=30); r['api']={'status':q.status_code,'bytes':len(q.content),'content_type':q.headers.get('Content-Type'),'text_head':q.text[:1000]}
    if q.ok:
        try:
            obj=q.json(); r['api']['json_type']=type(obj).__name__; r['api']['top_keys']=list(obj.keys()) if isinstance(obj,dict) else None
            (out/'AKBNK_raw.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
        except Exception as e:r['api']['json_error']=repr(e)
except Exception as e:r['api']={'error':repr(e)}
(out/'probe.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
print(json.dumps(r,ensure_ascii=False,indent=2))
