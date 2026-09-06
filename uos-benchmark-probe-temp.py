import json, urllib.parse, urllib.request
from pathlib import Path
import yfinance as yf
out=Path('uos-benchmark-probe-output'); out.mkdir(exist_ok=True)
r={'yahoo':{},'isyatirim':{}}
for t in ['XU100_CFNNTLTL.IS','XU100_CFNTLTL.IS','XU100.IS','^XU100']:
    try:
        d=yf.download(t,start='2018-01-01',end='2026-09-06',interval='1d',auto_adjust=False,actions=True,repair=True,progress=False,threads=False,timeout=30)
        if getattr(d.columns,'nlevels',1)>1:
            try:d=d.xs(t,axis=1,level=-1,drop_level=True)
            except Exception:pass
        r['yahoo'][t]={'rows':len(d)} if not d.empty else {'rows':0,'error':'empty'}
    except Exception as e:r['yahoo'][t]={'rows':0,'error':repr(e)}
base='https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/HisseTekil'
column_sets={
 'default':None,
 'open_probe':'HGDG_HS_KODU,HGDG_TARIH,HGDG_ACILIS,HGDG_KAPANIS,HGDG_MIN,HGDG_MAX,HGDG_HACIM,HGDG_HACIMTL,HG_ACILIS,HG_KAPANIS,HG_HACIM',
 'known_plus_open':'HGDG_HS_KODU,HGDG_TARIH,HGDG_ACILIS,HGDG_KAPANIS,HGDG_AOF,HGDG_MIN,HGDG_MAX,HGDG_HACIM,HG_ACILIS,HG_KAPANIS,HG_AOF,HG_MIN,HG_MAX,HG_HACIM'
}
for name,cols in column_sets.items():
    q={'hisse':'AKBNK','startdate':'02-01-2024','enddate':'05-01-2024','historicalData':True}
    if cols:q['columns']=cols
    url=base+'?'+urllib.parse.urlencode(q)
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
        b=urllib.request.urlopen(req,timeout=30).read(); o=json.loads(b)
        vals=o.get('value') if isinstance(o,dict) else o
        vals=vals or []
        r['isyatirim'][name]={'rows':len(vals),'url':url,'top_keys':list(o.keys()) if isinstance(o,dict) else None,
            'row_keys':sorted(vals[0].keys()) if vals and isinstance(vals[0],dict) else None,
            'first_row':vals[0] if vals else None}
    except Exception as e:r['isyatirim'][name]={'error':repr(e),'url':url}
(out/'probe.json').write_text(json.dumps(r,indent=2,ensure_ascii=False,default=str))
print(json.dumps(r,indent=2,ensure_ascii=False,default=str))
