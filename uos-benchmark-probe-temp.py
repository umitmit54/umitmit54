import json, urllib.parse, urllib.request
from pathlib import Path
out=Path('uos-benchmark-probe-output'); out.mkdir(exist_ok=True)
r={}
base='https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/'
endpoints=['HisseTekil','HisseTekBirGunlukKapanis']
for ep in endpoints:
    r[ep]={}
    probes={
      'short':{'hisse':'AKBNK','startdate':'02-01-2024','enddate':'05-01-2024','historicalData':True},
      'single_day':{'hisse':'AKBNK','startdate':'02-01-2024','enddate':'02-01-2024','historicalData':True},
      'with_columns':{'hisse':'AKBNK','startdate':'02-01-2024','enddate':'05-01-2024','historicalData':True,'columns':'HGDG_HS_KODU,HGDG_TARIH,HGDG_ACILIS,HGDG_KAPANIS,HGDG_AOF,HGDG_MIN,HGDG_MAX,HGDG_HACIM,HGDG_HACIM_LOT,HGDG_HACIM_TL,HG_ACILIS,HG_KAPANIS,HG_AOF,HG_MIN,HG_MAX,HG_HACIM'}
    }
    for name,q in probes.items():
        url=base+ep+'?'+urllib.parse.urlencode(q)
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            b=urllib.request.urlopen(req,timeout=30).read(); o=json.loads(b)
            vals=o.get('value') if isinstance(o,dict) else o; vals=vals or []
            r[ep][name]={'rows':len(vals),'url':url,'row_keys':sorted(vals[0].keys()) if vals and isinstance(vals[0],dict) else None,'first_row':vals[0] if vals else None}
        except Exception as e:r[ep][name]={'error':repr(e),'url':url}
(out/'probe.json').write_text(json.dumps(r,indent=2,ensure_ascii=False,default=str))
print(json.dumps(r,indent=2,ensure_ascii=False,default=str))
