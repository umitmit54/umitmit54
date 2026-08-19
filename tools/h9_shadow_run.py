#!/usr/bin/env python3
# Execution wrapper: preregistered H9 logic unchanged; only outcome-blind source/parser fixes are applied.
p='tools/h9_shadow_full.py'
s=open(p,encoding='utf-8').read()

# 1) Current XU100 from Borsa İstanbul official components CSV.
old='''def current_xu100():\n    # Current KAP XU100 filter + broad window: every constituent is expected to have >=1 disclosure.\n    rows=collect_range(date(2026,1,1),date(2026,8,11),IDX,7); s=set()\n    for e in rows:\n        for c in codes(e.get('stockCodes')):\n            if re.fullmatch(r'[A-Z0-9]{3,6}',c):s.add(c)\n    return s\n'''
new='''def current_xu100():\n    import io\n    url="https://www.borsaistanbul.com/datum/hisse_endeks_ds.csv"\n    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})\n    with urllib.request.urlopen(req,timeout=60) as r: raw=r.read()\n    text=None\n    for enc in ("utf-8-sig","cp1254","latin-1"):\n        try:text=raw.decode(enc);break\n        except:pass\n    rd=csv.DictReader(io.StringIO(text),delimiter=";")\n    out=set()\n    for r in rd:\n        if str(r.get("ENDEKS KODU") or "").strip()=="XU100":\n            t=re.sub(r"\\.E$","",str(r.get("BILESEN KODU") or "").strip().upper())\n            if re.fullmatch(r"[A-Z0-9]{3,6}",t):out.add(t)\n    print("BORSA_OFFICIAL_XU100_COUNT",len(out),sorted(out),flush=True)\n    return out\n'''
if old not in s:raise SystemExit('expected current_xu100 block not found')
s=s.replace(old,new,1)

# 2) Parse only actual rendered KAP taxonomy data rows.
# The same taxonomy field can appear earlier in metadata/schema text, so string-first-match is invalid.
start=s.index('def row_values(s,field_prefix):')
end=s.index('def fetch_reports(ids):',start)
replacement=r'''def report_fields(s):
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

    # Consolidated owners-of-parent net profit first; generic ProfitLoss for banks/non-consolidated schemas.
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
        # Financial-company schema may expose TL/FX/Total for each period (6 context cells).
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
s=s[:start]+replacement+s[end:]
exec(compile(s,p,'exec'),{'__name__':'__main__','__file__':p})
