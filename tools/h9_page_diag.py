#!/usr/bin/env python3
import re, html, urllib.request
BASE='https://www.kap.org.tr/tr/Bildirim/'
IDS=[1643141,1619494,1548084]
terms=['Ana Ortaklık','Ana ortaklık','Dönem Kar','Dönem Kâr','Net Dönem','Toplam Varlık','Özkaynak','Profit Loss','Assets']
for did in IDS:
    req=urllib.request.Request(BASE+str(did),headers={'User-Agent':'Mozilla/5.0','Accept-Language':'tr-TR,tr;q=0.9'})
    with urllib.request.urlopen(req,timeout=90) as r: raw=r.read().decode('utf-8','replace')
    txt=html.unescape(re.sub(r'<[^>]+>',' ',raw))
    txt=re.sub(r'\s+',' ',txt)
    print('\nID',did,'HTML_LEN',len(raw),'TEXT_LEN',len(txt))
    for term in terms:
        m=re.search(re.escape(term),txt,re.I)
        if m:
            print('TERM',term,'SNIP',txt[max(0,m.start()-350):m.start()+1200])
    # print snippets containing common XBRL codes/JSON keys
    for pat in [r'oda_[A-Za-z0-9_]{0,80}',r'ifrs-full_[A-Za-z0-9_]{0,100}',r'ProfitLoss[^<,\"]{0,120}',r'Assets[^<,\"]{0,120}']:
        vals=[]
        for m in re.finditer(pat,raw,re.I):
            v=m.group(0)
            if v not in vals: vals.append(v)
            if len(vals)>=8: break
        if vals: print('PAT',pat,vals)
