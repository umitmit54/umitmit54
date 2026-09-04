import io,requests,pandas as pd
URL='https://raw.githubusercontent.com/alvarobartt/investpy/master/investpy/resources/stocks.csv'
targets={'TRKCM','ANACM','SODA','ADANA'}
r=requests.get(URL,timeout=30,headers={'User-Agent':'Mozilla/5.0'}); r.raise_for_status()
df=pd.read_csv(io.StringIO(r.text))
print('COLUMNS',list(df.columns))
for s in sorted(targets):
    z=df[df.astype(str).apply(lambda row: row.str.upper().eq(s).any(),axis=1)]
    print('\nTARGET',s,'COUNT',len(z))
    if len(z): print(z.to_dict('records')[:10])
