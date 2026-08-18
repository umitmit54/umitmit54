#!/usr/bin/env python3
import re,urllib.request
from bs4 import BeautifulSoup
for did in [1643141,1548084]:
 req=urllib.request.Request('https://www.kap.org.tr/tr/Bildirim/'+str(did),headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(req,timeout=90) as r:s=r.read().decode('utf-8','replace')
 for a,b in [('\\u003c','<'),('\\u003e','>'),('\\u0026','&'),('\\u0027',"'"),('\\u0022','"'),('\\/','/')]:s=s.replace(a,b)
 s=s.replace('\\"','"')
 print('\nID',did)
 for tok in ['ifrs-full_ProfitLossAttributableToOwnersOfParent|','ifrs-full_ProfitLoss|','ifrs-full_Assets|']:
  p=s.find(tok); a=s.rfind('<tr class="',0,p)
  m=re.search(r'<tr class="[^"]*data-input-row',s[p+1:]); b=(p+1+m.start()) if m else min(len(s),p+40000)
  seg=s[a:b]
  soup=BeautifulSoup(seg,'html.parser')
  vals=[]
  for td in soup.find_all('td'):
   cl=td.get('class') or []
   if 'taxonomy-context-value' not in cl:continue
   vals.append({'class':' '.join(cl),'text':' '.join(td.stripped_strings),'attrs':dict(td.attrs),'children':[(x.name,dict(x.attrs),x.get_text(' ',strip=True)[:80]) for x in td.find_all(True)[:5]]})
  print('TOKEN',tok,'SEG_LEN',len(seg),'NVAL',len(vals))
  for x in vals[:6]:print(x)
