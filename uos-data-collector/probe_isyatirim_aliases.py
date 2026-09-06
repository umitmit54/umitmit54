import json, urllib.parse, urllib.request, time
from pathlib import Path
import pandas as pd
OUT=Path('uos-alias-probe'); OUT.mkdir(exist_ok=True)
ENDPOINT='https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/HisseTekil'
aliases={
'DGKLB':('DGNMO','2022-01-03'),
'EFORC':('EFOR','2025-11-03'),
'GUSGR':('TURSG','2020-09-01'),
'IPEKE':('TRENJ','2025-11-24'),
'ITTFH':('LRSHO','2023-11-01'),
'KERVT':('BESLR','2025-06-02'),
'KOZAA':('TRMET','2025-11-24'),
'KOZAL':('TRALT','2025-11-24')}
res=[]
for old,(new,chg) in aliases.items():
 q={'hisse':new,'startdate':'01-01-2018','enddate':'05-09-2026','historicalData':True}
 url=ENDPOINT+'?'+urllib.parse.urlencode(q)
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 UOS research alias validation'})
  with urllib.request.urlopen(req,timeout=60) as r: o=json.loads(r.read())
  vals=o.get('value',[]); dates=[]
  for row in vals:
   d=pd.to_datetime(row.get('HGDG_TARIH'),format='%d-%m-%Y',errors='coerce')
   if pd.notna(d): dates.append(d.strftime('%Y-%m-%d'))
  before=sum(d<chg for d in dates); after=sum(d>=chg for d in dates)
  res.append({'old_code':old,'new_code':new,'change_date':chg,'rows':len(dates),'first':min(dates) if dates else None,'last':max(dates) if dates else None,'rows_before_change':before,'rows_on_after_change':after,'url':url})
  (OUT/f'{new}.json').write_text(json.dumps(o,ensure_ascii=False))
 except Exception as e:
  res.append({'old_code':old,'new_code':new,'change_date':chg,'rows':0,'error':repr(e),'url':url})
 time.sleep(.5)
pd.DataFrame(res).to_csv(OUT/'alias_probe.csv',index=False)
print(json.dumps(res,ensure_ascii=False,indent=2))
