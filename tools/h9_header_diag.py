#!/usr/bin/env python3
import re,urllib.request
from bs4 import BeautifulSoup
for did in [1548084,1643141]:
 req=urllib.request.Request('https://www.kap.org.tr/tr/Bildirim/'+str(did),headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(req,timeout=90) as r:s=r.read().decode('utf-8','replace')
 for a,b in [('\\u003c','<'),('\\u003e','>'),('\\u0026','&'),('\\u0027',"'"),('\\u0022','"'),('\\/','/')]:s=s.replace(a,b)
 s=s.replace('\\"','"')
 soup=BeautifulSoup(s,'html.parser')
 target=None
 for tr in soup.find_all('tr'):
  fn=tr.find(class_='taxonomy-field-name')
  if fn and fn.get_text(strip=True).startswith('ifrs-full_Assets|'):target=tr;break
 print('\n### ID',did,'TARGET_CLASS',target.get('class') if target else None)
 if not target:continue
 # all ancestor tables, smallest first
 for i,tbl in enumerate(target.find_parents('table')[:6]):
  print('TABLE',i,'class',tbl.get('class'),'id',tbl.get('id'))
  rows=tbl.find_all('tr',recursive=False)
  print(' direct rows',len(rows))
  # print first 12 direct rows with all cells incl classes/colspan
  for tr in rows[:12]:
   cells=[]
   for c in tr.find_all(['th','td'],recursive=False):
    cells.append({'tag':c.name,'class':' '.join(c.get('class',[])),'colspan':c.get('colspan'),'rowspan':c.get('rowspan'),'text':' '.join(c.stripped_strings)[:400]})
   if cells: print('ROW',tr.get('class'),cells)
  # thead/tbody first rows recursively
  th=tbl.find('thead',recursive=False)
  if th:
   print('THEAD')
   for tr in th.find_all('tr'):
    print([{'class':' '.join(c.get('class',[])),'colspan':c.get('colspan'),'text':' '.join(c.stripped_strings)[:300]} for c in tr.find_all(['th','td'],recursive=False)])
 # find nearest previous rows in document order that mention TP/YP/Toplam or dates
 prev=target.find_all_previous('tr',limit=80)
 for tr in prev:
  txt=' '.join(tr.stripped_strings)
  if re.search(r'(TP|YP|Yabancı|Türk Parası|Toplam|Cari Dönem|Önceki Dönem|31\.12\.2025|31\.12\.2024|30\.06\.2026)',txt,re.I):
   print('PREV_MATCH',tr.get('class'),txt[:1800])
