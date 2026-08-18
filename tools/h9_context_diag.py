#!/usr/bin/env python3
import json,re,urllib.request,time
from bs4 import BeautifulSoup
BASE='https://www.kap.org.tr'; END=BASE+'/tr/api/disclosure/members/byCriteria'
HEAD={'Origin':BASE,'Referer':BASE+'/tr/bildirim-sorgu','User-Agent':'Mozilla/5.0','Accept':'application/json, text/plain, */*','Content-Type':'application/json'}
def post(a,b):
 p={'fromDate':a,'toDate':b,'memberType':'IGS','mkkMemberOidList':[],'inactiveMkkMemberOidList':[],'disclosureClass':'','subjectList':[],'isLate':'','mainSector':'','sector':'','subSector':'','marketOid':'','index':'','bdkReview':'','bdkMemberOidList':[],'year':'','term':'','ruleType':'','period':'','fromSrc':False,'srcCategory':'','disclosureIndexList':[]}
 req=urllib.request.Request(END,data=json.dumps(p).encode(),headers=HEAD,method='POST')
 with urllib.request.urlopen(req,timeout=60) as r:o=json.loads(r.read().decode())
 return o if isinstance(o,list) else next((o[k] for k in ('data','list','result','items') if isinstance(o.get(k),list)),[])
def actual(e): return str(e.get('disclosureCategory') or '').upper()=='FR' and str(e.get('subject') or '').strip().lower()=='finansal rapor'
def fetch_page(did):
 req=urllib.request.Request(BASE+'/tr/Bildirim/'+str(did),headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(req,timeout=90) as r:s=r.read().decode('utf-8','replace')
 for a,b in [('\\u003c','<'),('\\u003e','>'),('\\u0026','&'),('\\u0027',"'"),('\\u0022','"'),('\\/','/')]:s=s.replace(a,b)
 return s.replace('\\"','"')
def outer_segment(s,token):
 p=s.find(token)
 if p<0:return ''
 a=s.rfind('<tr class="',0,p)
 m=re.search(r'<tr class="[^"]*data-input-row',s[p+1:])
 b=(p+1+m.start()) if m else min(len(s),p+50000)
 return s[a:b]
def inspect(did,label):
 s=fetch_page(did); soup=BeautifulSoup(s,'html.parser')
 print('\n###',label,'ID',did,flush=True)
 # locate exact Assets row in parsed DOM then walk backward in containing table for date/header rows
 target=None
 for tr in soup.find_all('tr'):
  fn=tr.find(class_='taxonomy-field-name')
  if fn and fn.get_text(strip=True).startswith('ifrs-full_Assets|'):
   target=tr;break
 if not target:
  print('NO_ASSETS_ROW');return
 vals=[]
 for td in target.find_all('td',recursive=False):
  cls=' '.join(td.get('class',[]))
  if 'taxonomy-context-value' in cls:
   raw=td.find(attrs={'title':re.compile(r'^-?\d+(?:\.\d+)?$')})
   vals.append((cls, raw.get('title') if raw else None,' '.join(td.stripped_strings)))
 print('ASSET_VALUES',vals)
 # previous rows in same parent, nearest first
 prev=[]; x=target.previous_sibling
 while x is not None and len(prev)<35:
  if getattr(x,'name',None)=='tr':
   txt=' '.join(x.stripped_strings)
   if txt:prev.append((x.get('class',[]),txt[:1600]))
  x=x.previous_sibling
 for cl,txt in prev:
  if re.search(r'(Cari Dönem|Önceki Dönem|Current Period|Previous Period|31\.12|31\.03|30\.06|30\.09|Dipnot Referansı|Footnote Reference)',txt,re.I):
   print('PREV_HEADER',cl,txt)
 # all nearby rows before assets token in raw source that contain col-order/date clues
 tok=s.find('ifrs-full_Assets|')
 near=s[max(0,tok-80000):tok]
 ss=BeautifulSoup(near,'html.parser')
 cands=[]
 for tr in ss.find_all('tr')[-80:]:
  txt=' '.join(tr.stripped_strings)
  if re.search(r'(Cari Dönem|Önceki Dönem|Current Period|Previous Period|31\.12|31\.03|30\.06|30\.09)',txt,re.I):cands.append(txt[:1800])
 for z in cands[-10:]:print('NEAR_HEADER',z)

rows=[]
for a,b in [('2026-07-20','2026-08-11'),('2026-02-01','2026-03-31')]:
 try:rows+=post(a,b)
 except Exception as e:print('POST_FAIL',a,b,e)
seen=set(); samples=[]
for e in sorted(rows,key=lambda x:str(x.get('publishDate') or '')):
 if not actual(e) or e.get('modifyStatus'):continue
 stocks=str(e.get('stockCodes') or '')
 for t in ['AKBNK','GARAN','ISCTR','TSKB']:
  if t in re.split(r'[,;/\s]+',stocks):
   k=(t,int(e['disclosureIndex']))
   if k not in seen:samples.append((t,int(e['disclosureIndex']),e.get('publishDate'),e.get('year'),e.get('ruleType'),e.get('period')));seen.add(k)
print('SAMPLES',samples)
for x in samples[-8:]:inspect(x[1],str(x))
inspect(1548084,'ISFIN annual known')
