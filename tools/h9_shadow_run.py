#!/usr/bin/env python3
# Execution wrapper: preregistered H9 logic unchanged; only outcome-blind source/parser fixes are applied.
p='tools/h9_shadow_full.py'
s=open(p,encoding='utf-8').read()

# 1) Current XU100 from Borsa İstanbul official components CSV.
old='''def current_xu100():\n    # Current KAP XU100 filter + broad window: every constituent is expected to have >=1 disclosure.\n    rows=collect_range(date(2026,1,1),date(2026,8,11),IDX,7); s=set()\n    for e in rows:\n        for c in codes(e.get('stockCodes')):\n            if re.fullmatch(r'[A-Z0-9]{3,6}',c):s.add(c)\n    return s\n'''
new='''def current_xu100():\n    import io\n    url="https://www.borsaistanbul.com/datum/hisse_endeks_ds.csv"\n    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})\n    with urllib.request.urlopen(req,timeout=60) as r: raw=r.read()\n    text=None\n    for enc in ("utf-8-sig","cp1254","latin-1"):\n        try:text=raw.decode(enc);break\n        except:pass\n    rd=csv.DictReader(io.StringIO(text),delimiter=";")\n    out=set()\n    for r in rd:\n        if str(r.get("ENDEKS KODU") or "").strip()=="XU100":\n            t=re.sub(r"\\.E$","",str(r.get("BILESEN KODU") or "").strip().upper())\n            if re.fullmatch(r"[A-Z0-9]{3,6}",t):out.add(t)\n    print("BORSA_OFFICIAL_XU100_COUNT",len(out),sorted(out),flush=True)\n    return out\n'''
if old not in s:raise SystemExit('expected current_xu100 block not found')
s=s.replace(old,new,1)

# 2) KAP taxonomy parser. Outer data rows contain nested <tr> title markup; stop at NEXT data-input-row,
# not the first nested </tr>. Financial-company balance sheets use TP/YP/Total x current/prior,
# so total assets are col3 and col6 of the numeric contexts. General schemas use current/prior directly.
start=s.index('def row_values(s,field_prefix):')
end=s.index('def fetch_reports(ids):',start)
replacement=r'''def row_values(s,field_prefix):
    p=s.find(field_prefix)
    if p<0:return None
    a=s.rfind('<tr class="',0,p)
    if a<0:return None
    nxt=re.search(r'<tr class="[^"]*data-input-row',s[p+1:],re.I)
    b=(p+1+nxt.start()) if nxt else min(len(s),p+50000)
    row=s[a:b]
    vals=[]
    for td in re.findall(r'<td[^>]*class="[^"]*taxonomy-context-value[^"]*"[^>]*>(.*?)</td>',row,re.S|re.I):
        m=re.search(r'title="\s*(-?[0-9]+(?:\.[0-9]+)?)\s*"',td)
        if m: vals.append(float(m.group(1)))
    return vals

def report_fields(s):
    earn_type='OWNER'
    ev=row_values(s,'ifrs-full_ProfitLossAttributableToOwnersOfParent|')
    if not ev or len(ev)<2:
        earn_type='PROFITLOSS'
        ev=row_values(s,'ifrs-full_ProfitLoss|')
    if not ev or len(ev)<2:
        earn_type='MISSING'; ev=None
    av=row_values(s,'ifrs-full_Assets|')
    asset_schema='MISSING'; ac=None; ap=None
    if av:
        if len(av)>=6:
            # Financial schema: TP, YP, Total for current period; then TP, YP, Total for previous period.
            asset_schema='FIN_TP_YP_TOTAL'; ac=av[2]; ap=av[5]
        elif len(av)>=2:
            asset_schema='GENERAL_CURRENT_PRIOR'; ac=av[0]; ap=av[1]
    return {'earn_type':earn_type,'ni_current':ev[0] if ev and len(ev)>0 else None,
            'ni_prior':ev[1] if ev and len(ev)>1 else None,
            'assets_current':ac,'assets_prior':ap,'asset_schema':asset_schema,'asset_n':len(av) if av else 0}

'''
s=s[:start]+replacement+s[end:]
exec(compile(s,p,'exec'),{'__name__':'__main__','__file__':p})
