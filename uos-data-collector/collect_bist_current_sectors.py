from pathlib import Path
import io, json, requests, pandas as pd
URL='https://www.borsaistanbul.com/datum/hisse_endeks_ds.csv'
OUT=Path(__file__).resolve().parent/'bist_current_sectors'; OUT.mkdir(parents=True,exist_ok=True)
r=requests.get(URL,timeout=60,headers={'User-Agent':'Mozilla/5.0 UOS research collector'}); r.raise_for_status()
(OUT/'hisse_endeks_ds.csv').write_bytes(r.content)
text=None
for enc in ('utf-8-sig','cp1254','latin1'):
    try: text=r.content.decode(enc); break
    except UnicodeDecodeError: pass
if text is None: raise RuntimeError('decode failed')
df=pd.read_csv(io.StringIO(text),sep=';',dtype=str,low_memory=False)
if len(df) and str(df.iloc[0].get('BILESEN KODU','')).strip().upper() in ('COMPONENT CODE','COMPONENT'):
    df=df.iloc[1:].copy()
df['symbol']=df['BILESEN KODU'].astype(str).str.strip().str.replace(r'\.E$','',regex=True)
df['index_code']=df['ENDEKS KODU'].astype(str).str.strip()
df['index_name']=df['ENDEKS ADI'].astype(str).str.strip()
df[['symbol','index_code','index_name']].drop_duplicates().to_csv(OUT/'all_index_memberships.csv',index=False)
main={'XUSIN':'SANAYI','XUHIZ':'HIZMETLER','XUMAL':'MALI','XUTEK':'TEKNOLOJI'}
m=df[df.index_code.isin(main)].copy(); m['sector']=m.index_code.map(main)
# Each pay should map to one broad main sector. Keep diagnostics instead of silently choosing on conflict.
counts=m.groupby('symbol').sector.nunique().reset_index(name='n_sectors')
conf=counts[counts.n_sectors!=1]; conf.to_csv(OUT/'sector_conflicts.csv',index=False)
cur=m[['symbol','sector','index_code','index_name']].drop_duplicates().sort_values(['symbol','sector'])
cur.to_csv(OUT/'current_main_sector.csv',index=False)
status={'url':URL,'rows_raw':int(len(df)),'symbols_with_main_sector':int(cur.symbol.nunique()),'conflicts':int(len(conf))}
(OUT/'STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)); print(json.dumps(status,ensure_ascii=False))
