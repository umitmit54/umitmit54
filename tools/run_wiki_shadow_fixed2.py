#!/usr/bin/env python3
p='tools/wiki_shadow_collect.py'
s=open(p,encoding='utf-8').read()
old_fields='title=(r.get("memberTitle") or "").strip(); codes=(r.get("stockCodes") or "")'
new_fields='title=(r.get("kapMemberTitle") or r.get("memberTitle") or "").strip(); codes=(r.get("stockCode") or r.get("stockCodes") or "")'
old_types='for typ in ["HT","YK","PYS","BDK","DCS","DDK","DK","KVH"]:'
new_types='for typ in ["IGS","IGMS","KVS","HT","YK","PYS","BDK","DCS","DDK","DK","KVH"]:'
if old_fields not in s: raise SystemExit('expected live-field mapping line not found')
if old_types not in s: raise SystemExit('expected KAP member-type line not found')
s=s.replace(old_fields,new_fields,1).replace(old_types,new_types,1)
exec(compile(s,p,'exec'),{'__name__':'__main__','__file__':p})
