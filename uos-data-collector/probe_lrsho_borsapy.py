import json
from pathlib import Path
import pandas as pd
import borsapy as bp
out=Path('uos-lrsho-probe'); out.mkdir(exist_ok=True)
res={}
for s in ['AEFES','LRSHO']:
 try:
  d=bp.Ticker(s).history(start='2018-01-01',end='2026-09-06',interval='1d',actions=True,adjust=True,auto_adjust=True)
  d.to_csv(out/f'{s}.csv')
  res[s]={'rows':len(d),'first':str(d.index.min()),'last':str(d.index.max()),'columns':list(map(str,d.columns)),'div_sum':float(pd.to_numeric(d.get('Dividends',0),errors='coerce').fillna(0).sum()) if 'Dividends' in d else None}
 except Exception as e: res[s]={'error':repr(e)}
(out/'probe.json').write_text(json.dumps(res,ensure_ascii=False,indent=2))
print(json.dumps(res,ensure_ascii=False,indent=2))
