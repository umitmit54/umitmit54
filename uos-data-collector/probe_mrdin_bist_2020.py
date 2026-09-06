from pathlib import Path
import io, zipfile, json, hashlib
from datetime import date, timedelta
import pandas as pd, requests
OUT=Path('uos-mrdin-bist'); OUT.mkdir(parents=True,exist_ok=True)
BASE='https://www.borsaistanbul.com/data/thb/{y}/{m:02d}/thb{y}{m:02d}{d:02d}1.zip'
rows=[]; manifest=[]; d=date(2020,1,1); end=date(2020,5,29)
s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0 UOS research collector'})
while d<=end:
    if d.weekday()<5:
        url=BASE.format(y=d.year,m=d.month,d=d.day)
        rec={'date':d.isoformat(),'url':url}
        try:
            r=s.get(url,timeout=30); rec['status_code']=r.status_code
            if r.status_code==200 and r.content.startswith(b'PK'):
                with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                    names=[n for n in z.namelist() if n.lower().endswith('.csv')]
                    if names:
                        body=z.read(names[0]); txt=None
                        for enc in ('utf-8-sig','cp1254','latin1'):
                            try: txt=body.decode(enc); break
                            except: pass
                        df=pd.read_csv(io.StringIO(txt),sep=';',dtype=str,low_memory=False)
                        if len(df) and str(df.iloc[0].get('TARIH','')).strip().upper()=='TRADE DATE': df=df.iloc[1:].copy()
                        cc='ISLEM  KODU'; df['ticker']=df[cc].astype(str).str.strip().str.replace(r'\.E$','',regex=True)
                        g=df[df.ticker.eq('MRDIN')].copy()
                        if len(g):
                            g.insert(0,'source_date',d.isoformat()); rows.append(g); rec['rows']=len(g)
            manifest.append(rec)
        except Exception as e:
            rec['error']=repr(e); manifest.append(rec)
    d+=timedelta(days=1)
if rows:
    raw=pd.concat(rows,ignore_index=True); raw.to_csv(OUT/'MRDIN_BIST_RAW_2020.csv',index=False)
    num={'ACILIS FIYATI':'open','EN DUSUK FIYAT':'low','EN YUKSEK FIYAT':'high','KAPANIS FIYATI':'close','A.O.F':'vwap','TOPLAM ISLEM HACMI':'turnover','TOPLAM ISLEM ADEDI':'volume'}
    n=pd.DataFrame({'date':raw.source_date,'instrument_id':'MRDIN'})
    for src,dst in num.items(): n[dst]=pd.to_numeric(raw[src],errors='coerce')
    n.to_csv(OUT/'MRDIN_BIST_OHLCV_2020.csv',index=False)
pd.DataFrame(manifest).to_csv(OUT/'manifest.csv',index=False)
status={'rows':int(sum(len(x) for x in rows)),'days':int(len(rows)),'first':rows[0].source_date.iloc[0] if rows else None,'last':rows[-1].source_date.iloc[0] if rows else None}
(OUT/'STATUS.json').write_text(json.dumps(status,indent=2)); print(json.dumps(status))
