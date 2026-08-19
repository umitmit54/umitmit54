#!/usr/bin/env python3
import urllib.request
from bs4 import BeautifulSoup

ESC=[('\\u003c','<'),('\\u003e','>'),('\\u0026','&'),('\\u0027',"'"),('\\u0022','"'),('\\/','/')]

def fetch_page(did):
    req=urllib.request.Request('https://www.kap.org.tr/tr/Bildirim/'+str(did),headers={'User-Agent':'Mozilla/5.0','Accept-Language':'tr-TR,tr;q=0.9'})
    with urllib.request.urlopen(req,timeout=90) as r:s=r.read().decode('utf-8','replace')
    for a,b in ESC:s=s.replace(a,b)
    s=s.replace('\\"','"')
    return s

def values_for(s,field_prefix):
    soup=BeautifulSoup(s,'html.parser')
    hits=[]
    for td in soup.find_all('td'):
        cls=td.get('class') or []
        if 'taxonomy-field-name-cell' not in cls: continue
        field=' '.join(td.stripped_strings).strip()
        if not field.startswith(field_prefix): continue
        tr=td.find_parent('tr')
        trcls=(tr.get('class') or []) if tr else []
        vals=[]
        if tr:
            for cell in tr.find_all('td',recursive=False):
                ccls=cell.get('class') or []
                if 'taxonomy-context-value' not in ccls: continue
                titles=[]
                for node in cell.find_all(attrs={'title':True}):
                    titles.append(str(node.get('title')))
                    try:
                        vals.append(float(str(node.get('title')).strip()))
                        break
                    except: pass
        hits.append({'field':field[:180],'trcls':trcls,'vals':vals})
    return hits

for did in [1643141,1619494,1548084]:
    s=fetch_page(did)
    print('\nID',did,'LEN',len(s),flush=True)
    for prefix in ['ifrs-full_ProfitLossAttributableToOwnersOfParent|','ifrs-full_ProfitLoss|','ifrs-full_Assets|']:
        hits=values_for(s,prefix)
        print('PREFIX',prefix,'HITS',len(hits),flush=True)
        for h in hits[:6]:print(' HIT',h,flush=True)
