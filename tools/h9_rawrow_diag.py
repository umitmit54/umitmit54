#!/usr/bin/env python3
import urllib.request
ids=[1643141,1548084]
for did in ids:
 req=urllib.request.Request('https://www.kap.org.tr/tr/Bildirim/'+str(did),headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(req,timeout=90) as r:s=r.read().decode('utf-8','replace')
 for a,b in [('\\u003c','<'),('\\u003e','>'),('\\u0026','&'),('\\u0027',"'"),('\\u0022','"'),('\\/','/')]:s=s.replace(a,b)
 s=s.replace('\\"','"')
 print('\nID',did)
 for tok in ['ifrs-full_ProfitLossAttributableToOwnersOfParent|','ifrs-full_ProfitLoss|','ifrs-full_Assets|']:
  p=s.find(tok); print('TOKEN',tok,'POS',p)
  if p>=0:
   a=s.rfind('<tr',max(0,p-1500),p); b=s.find('</tr>',p)
   print(s[a:b+5][:8000])
