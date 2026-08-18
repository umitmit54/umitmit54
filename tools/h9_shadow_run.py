#!/usr/bin/env python3
# Execution wrapper: H9 logic unchanged; current XU100 is resolved from Borsa İstanbul's official components CSV.
p='tools/h9_shadow_full.py'
s=open(p,encoding='utf-8').read()
old='''def current_xu100():\n    # Current KAP XU100 filter + broad window: every constituent is expected to have >=1 disclosure.\n    rows=collect_range(date(2026,1,1),date(2026,8,11),IDX,7); s=set()\n    for e in rows:\n        for c in codes(e.get('stockCodes')):\n            if re.fullmatch(r'[A-Z0-9]{3,6}',c):s.add(c)\n    return s\n'''
new='''def current_xu100():\n    # Official Borsa İstanbul index-constituent CSV.\n    import io\n    url="https://www.borsaistanbul.com/datum/hisse_endeks_ds.csv"\n    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})\n    with urllib.request.urlopen(req,timeout=60) as r: raw=r.read()\n    text=None\n    for enc in ("utf-8-sig","cp1254","latin-1"):\n        try:text=raw.decode(enc);break\n        except:pass\n    rd=csv.DictReader(io.StringIO(text),delimiter=";")\n    rows=list(rd)\n    out=set()\n    for r in rows:\n        if str(r.get("ENDEKS KODU") or "").strip()=="XU100":\n            t=str(r.get("BILESEN KODU") or "").strip().upper()\n            t=re.sub(r"\\.E$","",t)\n            if re.fullmatch(r"[A-Z0-9]{3,6}",t):out.add(t)\n    print("BORSA_OFFICIAL_XU100_COUNT",len(out),sorted(out),flush=True)\n    return out\n'''
if old not in s:raise SystemExit('expected current_xu100 block not found')
s=s.replace(old,new,1)
# Outcome-blind parser hardening: never use the balance-sheet classified-in-equity line as earnings fallback.
bad='''    if not ev or len(ev)<2:\n        earn_type='NETPERIOD_FALLBACK'\n        ev=row_values(s,'kap-fr_CurrentPeriodNetProfitOrLossClassifiedInEquity|')\n'''
good='''    if not ev or len(ev)<2:\n        earn_type='MISSING'\n        ev=None\n'''
if bad not in s:raise SystemExit('expected unsafe earnings fallback not found')
s=s.replace(bad,good,1)
exec(compile(s,p,'exec'),{'__name__':'__main__','__file__':p})
