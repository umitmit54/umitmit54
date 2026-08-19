#!/usr/bin/env python3
# Execution wrapper: preregistered H9 logic unchanged; only outcome-blind source/parser fixes are applied.
p='tools/h9_shadow_full.py'
s=open(p,encoding='utf-8').read()

# 1) Current XU100 from Borsa İstanbul official components CSV.
old='''def current_xu100():\n    # Current KAP XU100 filter + broad window: every constituent is expected to have >=1 disclosure.\n    rows=collect_range(date(2026,1,1),date(2026,8,11),IDX,7); s=set()\n    for e in rows:\n        for c in codes(e.get('stockCodes')):\n            if re.fullmatch(r'[A-Z0-9]{3,6}',c):s.add(c)\n    return s\n'''
new='''def current_xu100():\n    import io\n    url="https://www.borsaistanbul.com/datum/hisse_endeks_ds.csv"\n    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})\n    with urllib.request.urlopen(req,timeout=60) as r: raw=r.read()\n    text=None\n    for enc in ("utf-8-sig","cp1254","latin-1"):\n        try:text=raw.decode(enc);break\n        except:pass\n    rd=csv.DictReader(io.StringIO(text),delimiter=";")\n    out=set()\n    for r in rd:\n        if str(r.get("ENDEKS KODU") or "").strip()=="XU100":\n            t=re.sub(r"\\.E$","",str(r.get("BILESEN KODU") or "").strip().upper())\n            if re.fullmatch(r"[A-Z0-9]{3,6}",t):out.add(t)\n    print("BORSA_OFFICIAL_XU100_COUNT",len(out),sorted(out),flush=True)\n    return out\n'''
if old not in s:raise SystemExit('expected current_xu100 block not found')
s=s.replace(old,new,1)

# 2) KAP can return a successful HTTP page without rendered taxonomy under burst load.
# Validate content and retry; use low concurrency for the 320-report backfill.
a=s.index('def fetch_page(did,tries=3):')
b=s.index('def row_values(s,field_prefix):',a)
fetch_replacement=r'''def fetch_page(did,tries=7):
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(BASE+'/tr/Bildirim/'+str(did),headers={'User-Agent':'Mozilla/5.0','Accept-Language':'tr-TR,tr;q=0.9'})
            with urllib.request.urlopen(req,timeout=90) as r:s=r.read().decode('utf-8','replace')
            for aa,bb in ESC:s=s.replace(aa,bb)
            s=s.replace('\\"','"')
            if 'taxonomy-field-name-cell' not in s or 'data-input-row' not in s:
                raise RuntimeError('KAP_PAGE_INCOMPLETE')
            return s
        except Exception as e:
            last=e
            time.sleep(min(12,1.5*(i+1)))
    raise last

'''
s=s[:a]+fetch_replacement+s[b:]

# 3) Parse only actual rendered KAP taxonomy data rows.
start=s.index('def row_values(s,field_prefix):')
end=s.index('def fetch_reports(ids):',start)
parser_replacement=r'''def report_fields(s):
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(s,'html.parser')

    def values_for(field_prefix):
        candidates=[]
        for td in soup.find_all('td'):
            cls=td.get('class') or []
            if 'taxonomy-field-name-cell' not in cls:
                continue
            field=' '.join(td.stripped_strings).strip()
            if not field.startswith(field_prefix):
                continue
            tr=td.find_parent('tr')
            if tr is None or 'data-input-row' not in (tr.get('class') or []):
                continue
            vals=[]
            for cell in tr.find_all('td',recursive=False):
                ccls=cell.get('class') or []
                if 'taxonomy-context-value' not in ccls:
                    continue
                val=None
                for node in cell.find_all(attrs={'title':True}):
                    try:
                        val=float(str(node.get('title')).strip())
                        break
                    except (TypeError,ValueError):
                        pass
                if val is not None:
                    vals.append(val)
            if vals:
                candidates.append(vals)
        return max(candidates,key=len) if candidates else None

    earn_type='OWNER'
    ev=values_for('ifrs-full_ProfitLossAttributableToOwnersOfParent|')
    if not ev or len(ev)<2:
        earn_type='PROFITLOSS'
        ev=values_for('ifrs-full_ProfitLoss|')
    if not ev or len(ev)<2:
        earn_type='MISSING'; ev=None

    av=values_for('ifrs-full_Assets|')
    asset_schema='MISSING'; ac=None; ap=None
    if av:
        if len(av)>=6:
            asset_schema='FIN_TP_YP_TOTAL'; ac=av[2]; ap=av[5]
        elif len(av)>=2:
            asset_schema='GENERAL_CURRENT_PRIOR'; ac=av[0]; ap=av[1]

    return {'earn_type':earn_type,
            'ni_current':ev[0] if ev and len(ev)>0 else None,
            'ni_prior':ev[1] if ev and len(ev)>1 else None,
            'assets_current':ac,'assets_prior':ap,
            'asset_schema':asset_schema,'asset_n':len(av) if av else 0}

'''
s=s[:start]+parser_replacement+s[end:]

# 4) Lower report-page concurrency and surface fetch/parse failures explicitly in logs.
start=s.index('def fetch_reports(ids):')
end=s.index('def yahoo_series(',start)
reports_replacement=r'''def fetch_reports(ids):
    out={}
    def one(i):
        try:
            page=fetch_page(i)
            fields=report_fields(page)
            return i,fields,None
        except Exception as e:
            return i,None,repr(e)
    with ThreadPoolExecutor(max_workers=3) as ex:
        fut=[ex.submit(one,i) for i in sorted(set(ids))]
        errs=0
        for j,f in enumerate(as_completed(fut),1):
            i,v,e=f.result(); out[i]={'fields':v,'error':e}
            if e:
                errs+=1
                if errs<=10:print('REPORT_ERROR',i,e,flush=True)
            if j%25==0:print('REPORTS',j,'/',len(fut),'ERRORS',errs,flush=True)
    print('REPORT_FETCH_ERRORS',errs,flush=True)
    return out

'''
s=s[:start]+reports_replacement+s[end:]
exec(compile(s,p,'exec'),{'__name__':'__main__','__file__':p})
