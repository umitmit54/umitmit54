import requests
from bs4 import BeautifulSoup
IDS={'ADANA':19253,'ANACM':19284,'SODA':19570,'TRKCM':19588}
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0','X-Requested-With':'XMLHttpRequest','Accept':'text/html, */*; q=0.01','Referer':'https://www.investing.com/'})
for sym,cid in IDS.items():
    data={'curr_id':str(cid),'smlID':'0','header':f'{sym} Historical Data','st_date':'01/01/2019','end_date':'12/31/2020','interval_sec':'Daily','sort_col':'date','sort_ord':'DESC','action':'historical_data'}
    try:
        r=S.post('https://www.investing.com/instruments/HistoricalDataAjax',data=data,timeout=30,headers={'Origin':'https://www.investing.com','Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'})
        soup=BeautifulSoup(r.text,'html.parser'); rows=[]
        for tr in soup.select('table#curr_table tbody tr, table.genTbl tbody tr'):
            td=[x.get_text(' ',strip=True) for x in tr.find_all('td')]
            if len(td)>=6: rows.append(td)
        print(sym,'status',r.status_code,'rows',len(rows),'head',rows[:2],'prefix',r.text[:60].replace('\n',' '))
    except Exception as e: print(sym,'ERR',repr(e))
