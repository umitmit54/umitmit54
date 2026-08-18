#!/usr/bin/env python3
import re, urllib.request
from bs4 import BeautifulSoup

def decode(raw):
    s=raw
    # KAP embeds rendered taxonomy HTML as escaped strings
    for a,b in [('\\u003c','<'),('\\u003e','>'),('\\u0026','&'),('\\u0027',"'"),('\\u0022','"'),('\\/','/')]: s=s.replace(a,b)
    s=s.replace('\\"','"')
    return s
for did in [1643141,1619494,1548084]:
    req=urllib.request.Request('https://www.kap.org.tr/tr/Bildirim/'+str(did),headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=90) as r: raw=r.read().decode('utf-8','replace')
    soup=BeautifulSoup(decode(raw),'html.parser')
    print('\n### ID',did)
    # rows with relevant target labels
    hits=[]
    for tr in soup.find_all('tr'):
        text=' '.join(tr.stripped_strings)
        if any(x.lower() in text.lower() for x in ['net dönem karı veya zararı','ana ortaklık payları','toplam varlıklar']):
            vals=[]
            for td in tr.find_all('td',recursive=False):
                cls=' '.join(td.get('class',[])); t=' '.join(td.stripped_strings)
                vals.append((cls,t[:180]))
            hits.append((text[:500],vals))
    for text,vals in hits[:10]:
        print('ROW',text)
        for v in vals: print('  TD',v)
    # candidate header/context rows mentioning dates or current/previous periods
    n=0
    for tr in soup.find_all('tr'):
        text=' '.join(tr.stripped_strings)
        if re.search(r'(31[./ -]?(03|12)|30[./ -]?(06|09)|01[./ -]?01|Cari Dönem|Önceki Dönem|Current Period|Previous Period)',text,re.I):
            if 'taxonomy' in ' '.join(tr.get('class',[])) or len(text)<500:
                print('HDR',text[:700])
                n+=1
                if n>=20:break
