import borsapy as bp
ALIASES={'DGKLB':'DGNMO','ITTFH':'LRSHO','GUSGR':'TURSG','KOZAA':'TRMET'}
for old,new in ALIASES.items():
    try:
        d=bp.Ticker(new).history(start='2019-01-01',end='2021-01-01')
        print(old,'->',new,'rows',0 if d is None else len(d),'start',None if d is None or len(d)==0 else str(d.index.min()),'end',None if d is None or len(d)==0 else str(d.index.max()))
    except Exception as e:print(old,'->',new,'ERR',repr(e))
