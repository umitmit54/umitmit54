import json
from pathlib import Path
import pandas as pd
import borsapy as bp
out=Path('uos-return-index-probe'); out.mkdir(exist_ok=True)
res={}
for code in ['XU100_CFNNTLTL','XU100']:
    try:
        d=bp.Index(code).history(start='2018-01-01', end='2026-09-06', interval='1d')
        res[code]={'rows':int(len(d)),'columns':list(map(str,d.columns)),'first':str(d.index.min()) if len(d) else None,'last':str(d.index.max()) if len(d) else None}
        if len(d): d.to_csv(out/f'{code}.csv')
    except Exception as e:
        res[code]={'error':repr(e)}
(out/'probe.json').write_text(json.dumps(res,indent=2,ensure_ascii=False))
print(json.dumps(res,indent=2,ensure_ascii=False))
