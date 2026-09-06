import json
from pathlib import Path
import yfinance as yf

OUT=Path('uos-benchmark/output'); OUT.mkdir(parents=True,exist_ok=True)
results={}
for t in ['XU100_CFNNTLTL.IS','XU100_CFNTLTL.IS','XU100.IS','^XU100']:
    try:
        d=yf.download(t,start='2018-01-01',end='2026-09-06',interval='1d',auto_adjust=False,actions=True,repair=True,progress=False,threads=False,timeout=45)
        if hasattr(d.columns,'nlevels') and d.columns.nlevels>1:
            try:d=d.xs(t,axis=1,level=-1,drop_level=True)
            except Exception:pass
        if d.empty:
            results[t]={'rows':0,'error':'empty'}; continue
        d.to_csv(OUT/(t.replace('^','caret').replace('.','_')+'.csv'))
        results[t]={'rows':len(d),'first':str(d.index.min()),'last':str(d.index.max()),'columns':list(map(str,d.columns))}
    except Exception as e:
        results[t]={'rows':0,'error':repr(e)}
(OUT/'benchmark_test.json').write_text(json.dumps(results,indent=2,ensure_ascii=False))
print(json.dumps(results,indent=2,ensure_ascii=False))
