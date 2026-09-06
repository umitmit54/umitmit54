from pathlib import Path
import json
import pandas as pd
import yfinance as yf

OUT=Path('uos-ittfh-lrsho-yahoo'); OUT.mkdir(parents=True,exist_ok=True)
status={}
for ticker in ['ITTFH.IS','LRSHO.IS','ERBOS.IS']:
    try:
        df=yf.download(ticker,start='2018-01-01',end='2026-09-06',auto_adjust=False,actions=True,progress=False,threads=False)
        if isinstance(df.columns,pd.MultiIndex):
            df.columns=[c[0] for c in df.columns]
        df=df.reset_index()
        fn=ticker.replace('.IS','')+'.csv'
        df.to_csv(OUT/fn,index=False)
        status[ticker]={'rows':int(len(df)),'columns':list(df.columns),'first':str(df['Date'].min()) if len(df) else None,'last':str(df['Date'].max()) if len(df) else None}
    except Exception as e:
        status[ticker]={'error':repr(e)}
(OUT/'STATUS.json').write_text(json.dumps(status,indent=2,ensure_ascii=False))
print(json.dumps(status,indent=2,ensure_ascii=False))
