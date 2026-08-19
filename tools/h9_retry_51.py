#!/usr/bin/env python3
import csv,time,urllib.request
from bs4 import BeautifulSoup
IDS=[1476218,1476236,1476272,1477038,1477044,1477077,1477134,1477177,1478721,1479473,1479519,1479562,1480120,1480657,1480799,1546392,1549019,1550376,1551575,1552068,1552588,1552722,1553968,1554106,1601474,1601478,1601482,1602017,1602029,1602046,1602061,1602065,1603692,1603696,1603726,1603827,1603855,1603905,1604961,1604997,1605085,1605086,1605118,1605171,1605190,1605209,1605215,1605226,1605233,1605247,1605251]
BASE='https://www.kap.org.tr'
ESC=[('\\u003c','<'),('\\u003e','>'),('\\u0026','&'),('\\u0027',"'"),('\\u0022','"'),('\\/','/')]

def fetch_page(did,tries=10):
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(BASE+'/tr/Bildirim/'+str(did),headers={'User-Agent':'Mozilla/5.0','Accept-Language':'tr-TR,tr;q=0.9'})
            with urllib.request.urlopen(req,timeout=90) as r:s=r.read().decode('utf-8','replace')
            for a,b in ESC:s=s.replace(a,b)
            s=s.replace('\\"','"')
            if 'taxonomy-field-name-cell' not in s or 'data-input-row' not in s:
                raise RuntimeError('KAP_PAGE_INCOMPLETE')
            return s
        except Exception as e:
            last=e
            print('RETRY',did,i+1,repr(e),flush=True)
            time.sleep(min(20,2*(i+1)))
    raise last

def report_fields(s):
    soup=BeautifulSoup(s,'html.parser')
    def values_for(field_prefix):
        candidates=[]
        for td in soup.find_all('td'):
            if 'taxonomy-field-name-cell' not in (td.get('class') or []):continue
            field=' '.join(td.stripped_strings).strip()
            if not field.startswith(field_prefix):continue
            tr=td.find_parent('tr')
            if tr is None or 'data-input-row' not in (tr.get('class') or []):continue
            vals=[]
            for cell in tr.find_all('td',recursive=False):
                if 'taxonomy-context-value' not in (cell.get('class') or []):continue
                for node in cell.find_all(attrs={'title':True}):
                    try:
                        vals.append(float(str(node.get('title')).strip()));break
                    except (TypeError,ValueError):pass
            if vals:candidates.append(vals)
        return max(candidates,key=len) if candidates else None
    earn='OWNER'; ev=values_for('ifrs-full_ProfitLossAttributableToOwnersOfParent|')
    if not ev or len(ev)<2:
        earn='PROFITLOSS';ev=values_for('ifrs-full_ProfitLoss|')
    if not ev or len(ev)<2:earn='MISSING';ev=None
    av=values_for('ifrs-full_Assets|'); schema='MISSING';ac=ap=None
    if av:
        if len(av)>=6:schema='FIN_TP_YP_TOTAL';ac=av[2];ap=av[5]
        elif len(av)>=2:schema='GENERAL_CURRENT_PRIOR';ac=av[0];ap=av[1]
    return {'EarnField':earn,'NI_Current':ev[0] if ev else None,'NI_PriorSamePeriod':ev[1] if ev else None,'Assets_Current':ac,'Assets_Prior':ap,'AssetSchema':schema,'AssetN':len(av) if av else 0}

rows=[]
for j,did in enumerate(IDS,1):
    try:
        f=report_fields(fetch_page(did));f.update({'DisclosureIndex':did,'FetchStatus':'OK','Error':''})
    except Exception as e:
        f={'DisclosureIndex':did,'FetchStatus':'ERROR','Error':repr(e),'EarnField':'','NI_Current':'','NI_PriorSamePeriod':'','Assets_Current':'','Assets_Prior':'','AssetSchema':'','AssetN':''}
    rows.append(f)
    print('DONE',j,'/',len(IDS),did,f.get('FetchStatus'),f.get('EarnField'),f.get('NI_Current'),f.get('Assets_Current'),flush=True)
    time.sleep(1.0)
fields=['DisclosureIndex','FetchStatus','Error','EarnField','NI_Current','NI_PriorSamePeriod','Assets_Current','Assets_Prior','AssetSchema','AssetN']
with open('h9_retry_51.csv','w',newline='',encoding='utf-8') as out:
    w=csv.DictWriter(out,fieldnames=fields);w.writeheader();w.writerows(rows)
print('SUMMARY','OK',sum(r['FetchStatus']=='OK' for r in rows),'ERROR',sum(r['FetchStatus']=='ERROR' for r in rows),flush=True)
