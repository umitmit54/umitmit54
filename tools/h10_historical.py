#!/usr/bin/env python3
import csv,json,math,re,time,urllib.request,io
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import date,datetime,timedelta,timezone

BASE='https://www.kap.org.tr'; DISC=BASE+'/tr/api/disclosure/members/byCriteria'; IDX='33E5FED8013D00EAE0530A4A622B2AEA'
HEAD={'Origin':BASE,'Referer':BASE+'/tr/bildirim-sorgu','User-Agent':'Mozilla/5.0 (GPT-BORSA-H10 research)','Accept':'application/json, text/plain, */*','Content-Type':'application/json'}
CHANGES={
'2022-Q1':('ADESE BASGZ BRYAT CEMAS GENIL GESAN IPEKE NTHOL RTALB','AKCNS ALBRK AYGAZ CEMTS HLGYO MPARK NETAS TMSN TRILC'),
'2022-Q2':('ARASE GSDHO GWIND JANTS KONTR KUTPO KZBGY NUGYO SNGYO TRILC','ADESE CEMAS GESAN IZMDC KERVT KRVGD RTALB SARKY VERUS YATAS'),
'2022-Q3':('AKFGY ALBRK BAGFS BUCIM CEMTS INVES PSGYO YATAS','ARASE BIOEN BRISA CANTE ESEN KARTN KUTPO KZBGY'),
'2022-Q4':('GESAN KARTN PRKAB SMRTG TMSN TSPOR TUKAS YYLGD','ARDYZ INDES INVES PARSN TKNSA TRILC ZOREN ZRGYO'),
'2023-Q1':('ASUZU BIOEN EUREN FENER KCAER KERVT KLRHO KMPUR KZBGY TKNSA ZOREN','GOZDE DEVA GENIL ISMEN KARTN LOGO NUGYO PRKAB QUAGR TRGYO YATAS'),
'2023-Q2':('ALFAS GENIL IZMDC KONYA ULUUN','ALGYO ISFIN JANTS NTHOL TSPOR'),
'2023-Q3':('AHGAZ AKCNS ASTOR BRSAN CANTE ECZYT ISMEN PENTA QUAGR','ALKIM BASGZ ERBOS FENER KERVT KLRHO TMSN TURSG ULUUN'),
'2023-Q4':('AKFYE BIENY CWENE EUPWR IMASM KAYSE MIATK YEOTK','ASUZU AYDEM BAGFS BIOEN CEMTS GSDHO SELEC TKNSA'),
'2024-Q1':('ASGYO BIOEN BOBET ENERY IZENR KLSER SDTTR TATEN','AKFGY GENIL GLYHO IMASM KZBGY PSGYO SNGYO VESBE'),
'2024-Q2':('AGROT AKFGY ANSGR BFREN BTCIM REEDR SAYAS TABGD TURSG VESBE','AGHOL ASGYO BUCIM ISDMR IZMDC KARSN KMPUR KORDS PENTA TATEN'),
'2024-Q3':('AGHOL ARDYZ BINHO GOLTS KTLEV LMKDC OBAMS PEKGY TKNSA TMSN','AHGAZ AKCNS ALBRK ANSGR BIENY BIOEN BOBET GWIND IPEKE SAYAS'),
'2024-Q4':('ADEL ALTNY ANSGR BJKAS CLEBI FENER KARSN MPARK PAPIL RGYAS','BFREN ECZYT EUREN ISGYO IZENR KAYSE QUAGR SDTTR TKNSA YYLGD'),
'2025-Q1':('ANHYT BTCIM CVKMD IEYHO LIDER MAGEN NTHOL PASEU SDTTR SELEC TSPOR','BJKAS VESBE ADEL AKFGY BINHO KTLEV LMKDC OBAMS PAPIL PEKGY RGYAS'),
'2025-Q2':('AHGAZ AVPGY EFORC GRTHO GSRAY KTLEV LMKDC OBAMS RALYH RYGYO','AKFYE CVKMD FENER KLSER LIDER NTHOL SDTTR TMSN TSPOR TUKAS'),
'2025-Q3':('BALSU BINHO DSTKF FENER GENIL GLRMK GRSEL IPEKE KUYAS TUREX','AGROT AHGAZ ANHYT ARDYZ ECILC GOLTS KARSN KONYA RYGYO SELEC'),
'2025-Q4':('DAPGM ECILC PATEK TSPOR','ALFAS AVPGY BERA LMKDC'),
'2026-Q1':('IZENR KLRHO QUAGR','BINHO CLEBI IEYHO'),
'2026-Q2':('CVKMD EUREN PAHOL PSGYO SARKY','EGEEN KCAER TSPOR TTRAK YEOTK'),
'2026-Q3':('ESEN IEYHO ODINE','AGHOL TABGD TUREX')}
QS=sorted(CHANGES)
def post(a,b,index='',tries=4):
 p={'fromDate':a,'toDate':b,'memberType':'IGS','mkkMemberOidList':[],'inactiveMkkMemberOidList':[],'disclosureClass':'','subjectList':[],'isLate':'','mainSector':'','sector':'','subSector':'','marketOid':'','index':index,'bdkReview':'','bdkMemberOidList':[],'year':'','term':'','ruleType':'','period':'','fromSrc':False,'srcCategory':'','disclosureIndexList':[]}
 for i in range(tries):
  try:
   req=urllib.request.Request(DISC,data=json.dumps(p).encode(),headers=HEAD,method='POST')
   with urllib.request.urlopen(req,timeout=60) as r:o=json.loads(r.read().decode())
   if isinstance(o,list):return o
   for k in ('data','list','result','items'):
    if isinstance(o.get(k),list):return o[k]
  except Exception as e:
   if i==tries-1:raise
   time.sleep(1.5*(i+1))
 return []
def collect(a,b,index='',chunk=7):
 out=[];d=a
 while d<=b:
  e=min(d+timedelta(days=chunk-1),b);out+=post(d.isoformat(),e.isoformat(),index);d=e+timedelta(days=1);time.sleep(.03)
 return out
def codes(s):return [x for x in re.split(r'[,;/\s]+',str(s or '').upper()) if re.fullmatch(r'[A-Z0-9]{3,6}',x)]
def pdt(s):
 for f in ('%d.%m.%Y %H:%M:%S','%Y-%m-%dT%H:%M:%S','%Y-%m-%d %H:%M:%S'):
  try:return datetime.strptime(str(s)[:19],f)
  except:pass
def current():
 url='https://www.borsaistanbul.com/datum/hisse_endeks_ds.csv'
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(req,timeout=60) as r:raw=r.read()
 text=None
 for enc in ('utf-8-sig','cp1254','latin-1'):
  try:text=raw.decode(enc);break
  except:pass
 out=set()
 for row in csv.DictReader(io.StringIO(text),delimiter=';'):
  if str(row.get('ENDEKS KODU') or '').strip()=='XU100':
   t=re.sub(r'\.E$','',str(row.get('BILESEN KODU') or '').strip().upper())
   if re.fullmatch(r'[A-Z0-9]{3,6}',t):out.add(t)
 return out
def universes(cur):
 u={};s=set(cur)
 for q in reversed(QS):
  u[q]=set(s);ins,outs=(set(x.split()) for x in CHANGES[q]);s=(s-ins)|outs
 return u
def qof(d):return f'{d.year}-Q{(d.month-1)//3+1}'
def actual(e):return str(e.get('disclosureCategory') or '').upper()=='FR' and str(e.get('subject') or '').strip().lower()=='finansal rapor'
def choose(rows,u):
 g={}
 for e in rows:
  if not actual(e):continue
  dt=pdt(e.get('publishDate'))
  if not dt or qof(dt.date()) not in u:continue
  for t in codes(e.get('stockCodes')):
   if t in u[qof(dt.date())]:g.setdefault((t,int(e.get('year') or 0),str(e.get('ruleType') or ''),int(e.get('period') or 0)),[]).append((dt,e))
 out=[]
 for k,v in g.items():
  v.sort(key=lambda z:z[0]);orig=[z for z in v if not z[1].get('modifyStatus')]
  if orig:out.append((k[0],orig[0][0],orig[0][1]))
 return out
def yahoo(sym,start=date(2021,12,1),end=date(2026,9,1)):
 p1=int(datetime(*start.timetuple()[:3],tzinfo=timezone.utc).timestamp());p2=int(datetime(*end.timetuple()[:3],tzinfo=timezone.utc).timestamp())
 url=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=history&includeAdjustedClose=true'
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(req,timeout=45) as r:o=json.loads(r.read().decode())
 z=o['chart']['result'][0];ts=z.get('timestamp') or [];q=z['indicators']['quote'][0];a=(z['indicators'].get('adjclose') or [{}])[0].get('adjclose') or q.get('close')
 return {datetime.fromtimestamp(t,timezone.utc).date():float(v) for t,v in zip(ts,a) if v is not None}
def prices(ts):
 out={}
 def one(t):
  for s in ([t+'.IS'] if t!='__INDEX__' else ['XU100.IS','^XU100']):
   try:
    v=yahoo(s)
    if len(v)>100:return t,v,s,''
   except Exception as e:last=repr(e)
  return t,{},s,last
 with ThreadPoolExecutor(max_workers=8) as ex:
  fs=[ex.submit(one,t) for t in sorted(set(ts)|{'__INDEX__'})]
  for n,f in enumerate(as_completed(fs),1):
   t,v,s,e=f.result();out[t]=(v,s,e)
   if n%25==0:print('PRICES',n,'/',len(fs),flush=True)
 return out
def er(dt,s,x,h):
 c=sorted(set(s)&set(x));d=dt.date();pre=[z for z in c if z<d];post=[z for z in c if z>d]
 if not pre or len(post)<=h:return None
 t0=pre[-1];t1=post[0];th=post[h]
 r=lambda a,b,y:y[b]/y[a]-1
 return (r(t0,t1,s)-r(t0,t1,x),r(t1,th,s)-r(t1,th,x),t0,t1,th)
def rank(v):
 o=sorted(range(len(v)),key=lambda i:v[i]);r=[0]*len(v)
 for j,i in enumerate(o):r[i]=j/(len(v)-1) if len(v)>1 else .5
 return r
def rho(a,b):
 if len(a)<3:return None
 x=rank(a);y=rank(b);mx=sum(x)/len(x);my=sum(y)/len(y);den=(sum((z-mx)**2 for z in x)*sum((z-my)**2 for z in y))**.5
 return sum((i-mx)*(j-my) for i,j in zip(x,y))/den if den else None
print('UNIVERSE',flush=True);cur=current();print('CURRENT',len(cur),flush=True)
if len(cur)!=100:raise SystemExit('current XU100 gate failed')
u=universes(cur)
if any(len(x)!=100 for x in u.values()):raise SystemExit('PIT universe gate failed')
print('KAP',flush=True);rows=collect(date(2022,1,1),date(2026,8,19),'',7);ev=choose(rows,u);print('EVENTS',len(ev),flush=True)
pp=prices([t for t,_,_ in ev]);idx=pp['__INDEX__'][0];out=[]
for t,dt,e in ev:
 row={'Cohort':f'{e.get("year")}-{e.get("ruleType")}-{e.get("period")}','Ticker':t,'DisclosureIndex':e.get('disclosureIndex'),'PublishDate':e.get('publishDate')}
 for h in (3,5,10):
  z=er(dt,pp.get(t,({},'', ''))[0],idx,h)
  row[f'InitialExcess_{h}']=z and z[0];row[f'ForwardExcess_{h}']=z and z[1]
 row['Status']='VALID' if row['ForwardExcess_5'] is not None else 'PRICE_WINDOW_MISSING';out.append(row)
summary=[]
for c in sorted(set(r['Cohort'] for r in out)):
 v=[r for r in out if r['Cohort']==c and r['Status']=='VALID'];rec={'Cohort':c,'Events':sum(r['Cohort']==c for r in out),'ValidN':len(v)}
 for h in (3,5,10):
  q=[r for r in v if r[f'ForwardExcess_{h}'] is not None];rec[f'IC_{h}']=rho([r[f'InitialExcess_{h}'] for r in q],[r[f'ForwardExcess_{h}'] for r in q]) if len(q)>=3 else None
  q=sorted(q,key=lambda r:r[f'InitialExcess_{h}']);n=max(1,math.ceil(len(q)/3));rec[f'TopMinusBottom_{h}']=(sum(r[f'ForwardExcess_{h}'] for r in q[-n:])/n-sum(r[f'ForwardExcess_{h}'] for r in q[:n])/n-.002) if q else None
 summary.append(rec)
for fn,data in [('h10_historical_events.csv',out),('h10_historical_summary.csv',summary)]:
 with open(fn,'w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
print('SUMMARY_JSON',json.dumps(summary,ensure_ascii=False),flush=True)
