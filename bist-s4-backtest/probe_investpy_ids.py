import io,requests,pandas as pd
URL='https://raw.githubusercontent.com/alvarobartt/investpy/master/investpy/resources/stocks.csv'
targets={'TRKCM','ANACM','SODA','ADANA'}
r=requests.get(URL,timeout=30,headers={'User-Agent':'Mozilla/5.0'}); r.raise_for_status()
df=pd.read_csv(io.StringIO(r.text))
print('COLUMNS',list(df.columns),'ROWS',len(df))
cols={str(c).lower():c for c in df.columns}
for s in sorted(targets):
    z=pd.DataFrame()
    if 'symbol' in cols:
        z=df[df[cols['symbol']].astype(str).str.upper().eq(s)]
    if z.empty:
        mask=False
        for c in df.columns:
            if df[c].dtype=='object':
                m=df[c].astype(str).str.upper().eq(s)
                mask=m if isinstance(mask,bool) else (mask|m)
        z=df[mask] if not isinstance(mask,bool) else pd.DataFrame()
    print('TARGET',s,'COUNT',len(z))
    if len(z): print(z.to_dict('records')[:10])
