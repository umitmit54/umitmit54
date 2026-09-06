import io, json, zipfile
from pathlib import Path
import pandas as pd, requests
out=Path('uos-symbol-changes'); out.mkdir(exist_ok=True)
url='https://www.borsaistanbul.com/datum/payadvekoddegisiklikleri.zip'
r=requests.get(url,timeout=30); r.raise_for_status(); (out/'source.zip').write_bytes(r.content)
with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    names=z.namelist()
    meta={'url':url,'members':names}
    for n in names:
        if n.lower().endswith('.xls'):
            b=z.read(n); p=out/Path(n).name; p.write_bytes(b)
            try:
                df=pd.read_excel(io.BytesIO(b),engine='xlrd')
                df.to_csv(out/(Path(n).stem+'.csv'),index=False)
                meta[Path(n).name]={'rows':len(df),'columns':list(map(str,df.columns))}
            except Exception as e:
                meta[Path(n).name]={'error':repr(e)}
(out/'meta.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
print(json.dumps(meta,ensure_ascii=False,indent=2))
