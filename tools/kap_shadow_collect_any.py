#!/usr/bin/env python3
"""GPT BORSA shadow KAP event-presence collector.

No directional or hard-information classifier is introduced here. This script
only retrieves official KAP disclosures, applies the frozen 7-day timestamp
window ending Friday 18:15 Europe/Istanbul, and records raw event presence/count
for the exact frozen panel. Intended for an exploratory cross-source check.
"""
import ast, base64, csv, gzip, io, json, re, time
import urllib.request
from datetime import datetime, timedelta

OLD_SOURCE = "tools/news_shadow_collect.py"
ENDPOINT = "https://www.kap.org.tr/tr/api/disclosure/members/byCriteria"
REFERER = "https://www.kap.org.tr/tr/bildirim-sorgu"
OUT_ROWS = "kap_shadow_rows_any.csv"
OUT_EVENTS = "kap_shadow_events_any.csv"
HEADERS = {
    "Origin": "https://www.kap.org.tr",
    "Referer": REFERER,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Content-Type": "application/json",
}


def extract_panel():
    src = open(OLD_SOURCE, encoding="utf-8").read()
    m = re.search(r"^PANEL_B64=(.+)$", src, re.M)
    if not m:
        raise RuntimeError("PANEL_B64 not found")
    b64 = ast.literal_eval(m.group(1))
    return list(csv.DictReader(io.StringIO(gzip.decompress(base64.b64decode(b64)).decode("utf-8"))))


def normalize_response(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("data", "list", "result", "items"):
            if isinstance(obj.get(k), list):
                return obj[k]
    raise RuntimeError(f"Unexpected KAP response shape: {type(obj).__name__}")


def post_kap(from_date, to_date, tries=4):
    payload = {
        "fromDate": from_date,
        "toDate": to_date,
        "memberType": "",
        "mkkMemberOidList": [],
        "inactiveMkkMemberOidList": [],
        "disclosureClass": "",
        "subjectList": [],
        "isLate": "",
        "mainSector": "",
        "sector": "",
        "subSector": "",
        "marketOid": "",
        "index": "",
        "bdkReview": "",
        "bdkMemberOidList": [],
        "year": "",
        "term": "",
        "ruleType": "",
        "period": "",
        "fromSrc": False,
        "srcCategory": "",
        "disclosureIndexList": [],
    }
    body = json.dumps(payload).encode("utf-8")
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(ENDPOINT, data=body, headers=HEADERS, method="POST")
            with urllib.request.urlopen(req, timeout=45) as r:
                return normalize_response(json.loads(r.read().decode("utf-8")))
        except Exception as e:
            last = e
            print(f"WARN KAP {from_date}..{to_date} attempt {attempt+1}: {e}", flush=True)
            time.sleep(2 ** attempt)
    raise last


def parse_publish(s):
    s = (s or "").strip()
    for fmt in ("%d.%m.%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def split_codes(s):
    if not s:
        return []
    return [x.strip().upper() for x in re.split(r"[,;/\s]+", str(s)) if x.strip()]


panel = extract_panel()
weeks = {}
for r in panel:
    weeks.setdefault(r["Week"], r)

all_events = []
by_week_ticker = {}
for week in sorted(weeks):
    r0 = weeks[week]
    freeze = datetime.fromisoformat(r0["Freeze"] + "T18:15:00")
    start = freeze - timedelta(days=7)
    rows = post_kap(start.date().isoformat(), freeze.date().isoformat())
    panel_tickers = {r["Ticker"] for r in panel if r["Week"] == week}
    kept = 0
    for e in rows:
        dt = parse_publish(e.get("publishDate"))
        if dt is None or not (start < dt <= freeze):
            continue
        codes = split_codes(e.get("stockCodes"))
        hits = sorted(panel_tickers.intersection(codes))
        if not hits:
            continue
        kept += 1
        event = {
            "Week": week,
            "DisclosureIndex": e.get("disclosureIndex"),
            "PublishDate": e.get("publishDate"),
            "StockCodes": e.get("stockCodes"),
            "Subject": e.get("subject"),
            "Summary": e.get("summary"),
            "DisclosureType": e.get("disclosureType"),
            "DisclosureClass": e.get("disclosureClass"),
            "IsLate": e.get("isLate"),
            "IsCorrective": e.get("isCorrective"),
        }
        all_events.append(event)
        for t in hits:
            by_week_ticker.setdefault((week, t), []).append(event)
    print(f"{week}: API {len(rows)} disclosures; {kept} panel-relevant events", flush=True)
    time.sleep(0.5)

out = []
for r in panel:
    evs = by_week_ticker.get((r["Week"], r["Ticker"]), [])
    out.append({
        "Week": r["Week"],
        "Freeze": r["Freeze"],
        "Ticker": r["Ticker"],
        "KAPCount7d": len(evs),
        "KAPAny7d": 1 if evs else 0,
        "KAPDisclosureIds": ";".join(str(e["DisclosureIndex"]) for e in evs if e.get("DisclosureIndex") is not None),
        "KAPSubjects": " | ".join(str(e.get("Subject") or "") for e in evs),
        "RowStatus": r["RowStatus"],
        "ExcessRet": r["ExcessRet"],
    })

with open(OUT_ROWS, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]))
    w.writeheader(); w.writerows(out)

fields = ["Week","DisclosureIndex","PublishDate","StockCodes","Subject","Summary","DisclosureType","DisclosureClass","IsLate","IsCorrective"]
with open(OUT_EVENTS, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader(); w.writerows(all_events)

print(f"DONE rows={len(out)} events={len(all_events)}", flush=True)
