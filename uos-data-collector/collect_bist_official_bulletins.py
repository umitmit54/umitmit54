import argparse, csv, hashlib, io, json, os, time, zipfile
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import requests

BASE='https://www.borsaistanbul.com/data/thb/{y}/{m:02d}/thb{y}{m:02d}{d:02d}1.zip'
NUMERIC_MAP={
 'ONCEKI KAPANIS FIYATI':'prev_close','ACILIS FIYATI':'open','EN DUSUK FIYAT':'low',
 'EN YUKSEK FIYAT':'high','KAPANIS FIYATI':'close','A.O.F':'vwap',
 'TOPLAM ISLEM HACMI':'turnover_tl','TOPLAM ISLEM ADEDI':'volume_shares',
 'TOPLAM SOZLESME SAYISI':'trade_count'
}

def sha256(b): return hashlib.sha256(b).hexdigest()

def parse_args():
 p=argparse.ArgumentParser(); p.add_argument('--year',type=int,required=True); p.add_argument('--out',required=True); return p.parse_args()

def daterange(y):
 d=date(y,1,1); end=date(y,12,31)
 while d<=end:
  if d.weekday()<5: yield d
  d += timedelta(days=1)

def decode_csv(b):
 for enc in ('utf-8-sig','cp1254','latin1'):
  try: return b.decode(enc),enc
  except UnicodeDecodeError: pass
 raise UnicodeDecodeError('unknown',b,0,1,'no supported encoding')

def main():
 a=parse_args(); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
 symbols=set(json.loads((Path(__file__).parent/'symbols_2019_2026.json').read_text()))
 sess=requests.Session(); sess.headers.update({'User-Agent':'Mozilla/5.0 UOS research collector'})
 raw_parts=[]; norm_parts=[]; manifest=[]
 for i,d in enumerate(daterange(a.year),1):
  url=BASE.format(y=d.year,m=d.month,d=d.day)
  rec={'date':d.isoformat(),'url':url,'retrieved_at_utc':pd.Timestamp.utcnow().isoformat()}
  try:
   r=sess.get(url,timeout=30)
   rec['http_status']=r.status_code; rec['bytes']=len(r.content)
   if r.status_code!=200 or not r.content.startswith(b'PK'):
    rec['status']='NO_FILE'; manifest.append(rec); continue
   rec['sha256']=sha256(r.content)
   with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    names=[n for n in z.namelist() if n.lower().endswith('.csv')]
    if not names: rec['status']='ZIP_NO_CSV'; manifest.append(rec); continue
    inner=names[0]; body=z.read(inner); rec['inner_file']=inner; rec['inner_sha256']=sha256(body)
   txt,enc=decode_csv(body); rec['encoding']=enc
   df=pd.read_csv(io.StringIO(txt),sep=';',dtype=str,low_memory=False)
   if len(df) and str(df.iloc[0].get('TARIH','')).strip().upper()=='TRADE DATE': df=df.iloc[1:].copy()
   code_col='ISLEM  KODU'
   if code_col not in df.columns: rec['status']='SCHEMA_MISSING_CODE'; manifest.append(rec); continue
   df['instrument_id']=df[code_col].astype(str).str.strip().str.replace(r'\.E$','',regex=True)
   f=df[df['instrument_id'].isin(symbols)].copy()
   rec['rows_all']=len(df); rec['rows_union']=len(f); rec['status']='OK'; manifest.append(rec)
   if f.empty: continue
   # The URL filename encodes the authoritative bulletin date. Source TARIH formatting changed
   # across years (ISO / DD-MM-YYYY), so do not let locale parsing silently swap day/month.
   f.insert(0,'source_date',d.isoformat()); f['source_url']=url; f['source_zip_sha256']=rec['sha256']; raw_parts.append(f)
   n=pd.DataFrame({'date':[d.isoformat()]*len(f),'instrument_id':f['instrument_id'].to_numpy()})
   for src,dst in NUMERIC_MAP.items(): n[dst]=pd.to_numeric(f[src],errors='coerce').to_numpy() if src in f.columns else pd.NA
   for src in ['BIST 100 ENDEKS','BIST 30 ENDEKS','BRUT TAKAS','OZSERMAYE HALI','GECICI DURDURMA','ACIGA SATIS','PAZAR','YAPISAL BAZDA PIYASA ALT BOLUMU','ISLEM YONTEMI']:
    if src in f.columns: n[src.lower().replace(' ','_').replace('ı','i')]=f[src].to_numpy()
   n['source_url']=url; n['source_zip_sha256']=rec['sha256']; norm_parts.append(n)
   if i%25==0: time.sleep(0.25)
  except Exception as e:
   rec['status']='ERROR'; rec['error']=repr(e); manifest.append(rec)
 pd.DataFrame(manifest).to_csv(out/f'manifest_{a.year}.csv',index=False)
 if raw_parts: pd.concat(raw_parts,ignore_index=True).to_csv(out/f'bist_raw_filtered_{a.year}.csv',index=False)
 if norm_parts:
  norm=pd.concat(norm_parts,ignore_index=True).sort_values(['date','instrument_id'])
  if norm.duplicated(['date','instrument_id']).any():
   raise RuntimeError(f'duplicate date/instrument rows after source-date anchoring: {int(norm.duplicated(["date","instrument_id"]).sum())}')
  norm.to_csv(out/f'bist_ohlcv_{a.year}.csv',index=False)
  summary={'year':a.year,'rows':int(len(norm)),'symbols':int(norm.instrument_id.nunique()),'first_date':norm.date.min(),'last_date':norm.date.max(),'sessions':int(norm.date.nunique()),'fields':list(norm.columns)}
 else: summary={'year':a.year,'rows':0,'symbols':0}
 (out/f'summary_{a.year}.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
 print(json.dumps(summary,indent=2,ensure_ascii=False))

if __name__=='__main__': main()
