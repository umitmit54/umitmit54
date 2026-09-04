import re,requests
from bs4 import BeautifulSoup
SPECS={
'TRKCM':['trakya-cam'],
'ANACM':['anadolu-cam'],
'SODA':['soda-sanayi','soda-sanayii','soda-sanayi-as'],
'ADANA':['adana-cimento','adana-cimento-a','adana-cimento-sanayi'],
}
H={'User-Agent':'Mozilla/5.0','X-Requested-With':'XMLHttpRequest','Accept':'text/html','Referer':'https://www.investing.com/'}
S=requests.Session();S.headers.update({'User-Agent':'Mozilla/5.0'})

def get_id(slug):
    u='https://www.investing.com/equities/'+slug+'-historical-data'
    r=S.get(u,timeout=20)
    if not r.ok:return None,u,r.status_code
    pats=[r'pair_ID\s*[=:]\s*["\']?(\d+)',r'curr_id["\']?\s*[:=]\s*["\']?(\d+)',r'data-pair-id=["\'](\d+)']
    for p in pats:
        m=re.search(p,r.text,re.I)
        if m:return m.group(1),u,r.status_code
    # fallback scan near symbol page scripts
    m=re.search(r'pairId["\']?\s*[:=]\s*["\']?(\d+)',r.text,re.I)
    return (m.group(1) if m else None),u,r.status_code

def hist(cid,sym):
    data={'curr_id':cid,'smlID':'1234567','header':sym+' Historical Data','st_date':'01/01/2019','end_date':'12/31/2020','interval_sec':'Daily','sort_col':'date','sort_ord':'DESC','action':'historical_data'}
    h=dict(H);h['Content-Type']='application/x-www-form-urlencoded';h['Origin']='https://www.investing.com'
    r=S.post('https://www.investing.com/instruments/HistoricalDataAjax',data=data,headers=h,timeout=30)
    soup=BeautifulSoup(r.text,'html.parser');rows=[]
    for tr in soup.select('table#curr_table tbody tr'):
        td=[x.get_text(' ',strip=True) for x in tr.find_all('td')]
        if len(td)>=6:rows.append(td)
    return r.status_code,len(rows),rows[:2],r.text[:80]

for sym,slugs in SPECS.items():
    ok=False
    for slug in slugs:
        try:
            cid,u,st=get_id(slug);print('PAGE',sym,slug,st,'id',cid)
            if cid:
                z=hist(cid,sym);print('HIST',sym,slug,z[:3]);
                if z[1]>20:ok=True;break
        except Exception as e:print('ERR',sym,slug,repr(e))
    if not ok:print('NONE',sym)
