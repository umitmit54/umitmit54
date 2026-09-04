import io,requests,pandas as pd
SYMS=['ADANA','ANACM','DGKLB','GUSGR','ITTFH','KOZAA','SODA','TRKCM']

def try_stooq(sym):
    urls=[f'https://stooq.com/q/d/l/?s={sym.lower()}.tr&d1=20190101&d2=20201231&i=d',f'https://stooq.com/q/d/l/?s={sym.lower()}.is&d1=20190101&d2=20201231&i=d']
    for u in urls:
        try:
            r=requests.get(u,timeout=20); txt=r.text
            if r.ok and txt.startswith('Date,'):
                df=pd.read_csv(io.StringIO(txt));
                if len(df)>20:return 'stooq',u,len(df),df.head(2).to_dict('records')
        except Exception:pass
    return None

def try_yahoo(sym):
    import datetime,time
    p1=int(datetime.datetime(2019,1,1,tzinfo=datetime.timezone.utc).timestamp());p2=int(datetime.datetime(2021,1,1,tzinfo=datetime.timezone.utc).timestamp())
    for suf in ['.IS','']:
        u=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}{suf}?period1={p1}&period2={p2}&interval=1d&events=history'
        try:
            r=requests.get(u,timeout=20,headers={'User-Agent':'Mozilla/5.0'});j=r.json();res=j.get('chart',{}).get('result')
            if res and len(res[0].get('timestamp',[]))>20:return 'yahoo',u,len(res[0]['timestamp']),res[0]['meta'].get('symbol')
        except Exception:pass
    return None

for s in SYMS:
    ans=try_stooq(s) or try_yahoo(s)
    print(s,ans or 'NONE')
