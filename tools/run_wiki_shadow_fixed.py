#!/usr/bin/env python3
p='tools/wiki_shadow_collect.py'
s=open(p,encoding='utf-8').read()
old='title=(r.get("memberTitle") or "").strip(); codes=(r.get("stockCodes") or "")'
new='title=(r.get("kapMemberTitle") or r.get("memberTitle") or "").strip(); codes=(r.get("stockCode") or r.get("stockCodes") or "")'
if old not in s:
    raise SystemExit('expected KAP field mapping line not found')
s=s.replace(old,new,1)
exec(compile(s,p,'exec'),{'__name__':'__main__','__file__':p})
