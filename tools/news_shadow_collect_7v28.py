#!/usr/bin/env python3
"""GPT BORSA v0.4 prereg-compliant Google News shadow backfill.

Uses the exact frozen PANEL_B64 embedded in news_shadow_collect.py, but scores
current 7 calendar days against the immediately preceding 28 calendar days by
daily rate, exactly as A0-09 preregisters.
"""
import ast, base64, csv, gzip, io, math, re, time
import urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

OLD_SOURCE = "tools/news_shadow_collect.py"
OUT_ROWS = "news_shadow_rows_7v28.csv"
OUT_WEEKLY = "news_shadow_weekly_7v28.csv"
USER_AGENT = "GPT-BORSA-Shadow/0.4 research-contact github.com/umitmit54"
ALIASES = {
    "ASELS": '("ASELSAN" OR ASELS)',
    "BIMAS": '("Bim Birlesik Magazalar" OR BIMAS)',
    "AKBNK": '(Akbank OR AKBNK)',
    "EREGL": '("Eregli Demir ve Celik" OR EREGL)',
    "GARAN": '("Garanti BBVA" OR GARAN)',
}


def extract_panel_b64():
    src = open(OLD_SOURCE, encoding="utf-8").read()
    m = re.search(r"^PANEL_B64=(.+)$", src, re.M)
    if not m:
        raise RuntimeError("PANEL_B64 not found in frozen collector")
    return ast.literal_eval(m.group(1))


def fetch(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def parse_pubdate(text):
    return datetime.strptime(text, "%a, %d %b %Y %H:%M:%S %Z").date()


def news_query(ticker):
    return ALIASES.get(ticker, f'"{ticker}" hisse')


def month_chunks(d0, d1):
    cur = date(d0.year, d0.month, 1)
    while cur <= d1:
        nxt = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
        yield cur, nxt
        cur = nxt


def rss_for_ticker(ticker, global_start, global_end):
    items, seen = [], set()
    for mstart, mnext in month_chunks(global_start, global_end):
        qs = max(global_start, mstart)
        qe = min(global_end + timedelta(days=1), mnext)
        if qs >= qe:
            continue
        q = f"{news_query(ticker)} after:{qs.isoformat()} before:{qe.isoformat()}"
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
            {"q": q, "hl": "tr", "gl": "TR", "ceid": "TR:tr"}
        )
        try:
            root = ET.fromstring(fetch(url))
            for it in root.findall(".//item"):
                title = (it.findtext("title") or "").strip()
                pub = (it.findtext("pubDate") or "").strip()
                src = it.find("source")
                source = (src.text or "").strip() if src is not None else ""
                if not title or not pub:
                    continue
                try:
                    d = parse_pubdate(pub)
                except Exception:
                    continue
                key = (title.lower(), source.lower(), d.isoformat())
                if key in seen:
                    continue
                seen.add(key)
                items.append({"date": d, "title": title, "source": source})
        except Exception as e:
            print(f"WARN RSS {ticker} {qs}..{qe}: {e}", flush=True)
        time.sleep(0.15)
    return items


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and xs[order[j]] == xs[order[i]]:
            j += 1
        avg = (i + 1 + j) / 2.0
        for k in range(i, j):
            out[order[k]] = avg
        i = j
    return out


def pearson(a, b):
    if len(a) < 3:
        return None
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    xa, xb = [x - ma for x in a], [x - mb for x in b]
    den = (sum(x*x for x in xa) * sum(y*y for y in xb)) ** 0.5
    return None if den == 0 else sum(x*y for x, y in zip(xa, xb)) / den


def spearman(a, b):
    return pearson(ranks(a), ranks(b))


def fnum(x):
    try:
        return float(x)
    except Exception:
        return None


panel_b64 = extract_panel_b64()
panel_text = gzip.decompress(base64.b64decode(panel_b64)).decode("utf-8")
rows = []
for r in csv.DictReader(io.StringIO(panel_text)):
    r["CurrStartD"] = date.fromisoformat(r["CurrStart"])
    r["CurrEndD"] = date.fromisoformat(r["CurrEnd"])
    rows.append(r)

valid = [r for r in rows if r["RowStatus"] == "VALID"]
global_start = min(r["CurrStartD"] - timedelta(days=28) for r in valid)
global_end = max(r["CurrEndD"] for r in valid) - timedelta(days=1)
tickers = sorted({r["Ticker"] for r in valid})
print(f"{len(valid)} valid rows, {len(tickers)} tickers, {global_start}..{global_end}", flush=True)

cache = {}
for i, ticker in enumerate(tickers, 1):
    cache[ticker] = rss_for_ticker(ticker, global_start, global_end)
    print(f"{i}/{len(tickers)} {ticker}: {len(cache[ticker])} unique RSS items", flush=True)

relay_terms = ("kap", "kamuyu aydınlatma", "kamuyu aydinlatma")
out = []
for r in rows:
    items = cache.get(r["Ticker"], [])
    curr_start, curr_end = r["CurrStartD"], r["CurrEndD"]
    base_start = curr_start - timedelta(days=28)
    curr = [x for x in items if curr_start <= x["date"] < curr_end]
    base = [x for x in items if base_start <= x["date"] < curr_start]
    curr_ind = len(curr) - sum(any(z in x["title"].lower() for z in relay_terms) for x in curr)
    base_ind = len(base) - sum(any(z in x["title"].lower() for z in relay_terms) for x in base)
    curr_rate, base_rate = len(curr) / 7.0, len(base) / 28.0
    curr_ind_rate, base_ind_rate = curr_ind / 7.0, base_ind / 28.0
    d = {k: r[k] for k in ["Week", "Freeze", "Ticker", "ExcessRet", "CAFlag", "RowStatus", "CurrStart", "CurrEnd"]}
    d.update({
        "NewsQuery": news_query(r["Ticker"]),
        "Baseline28Start": base_start.isoformat(),
        "NewsCurr7": len(curr),
        "NewsBase28": len(base),
        "NewsCurrDailyRate": curr_rate,
        "NewsBaseDailyRate": base_rate,
        "NewsShock7v28": math.log1p(curr_rate) - math.log1p(base_rate),
        "NewsCurrSources": len({x["source"] for x in curr if x["source"]}),
        "NewsBaseSources": len({x["source"] for x in base if x["source"]}),
        "NewsCurrIndependent": curr_ind,
        "NewsBaseIndependent": base_ind,
        "NewsIndependentShock7v28": math.log1p(curr_ind_rate) - math.log1p(base_ind_rate),
    })
    out.append(d)

with open(OUT_ROWS, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]))
    w.writeheader(); w.writerows(out)

weekly = []
for week in sorted({r["Week"] for r in out}):
    wr = [r for r in out if r["Week"] == week and r["RowStatus"] == "VALID" and fnum(r["ExcessRet"]) is not None]
    ys = [float(r["ExcessRet"]) for r in wr]
    xs = [float(r["NewsShock7v28"]) for r in wr]
    ixs = [float(r["NewsIndependentShock7v28"]) for r in wr]
    top = sorted(wr, key=lambda r: float(r["NewsShock7v28"]), reverse=True)[:10]
    itop = sorted(wr, key=lambda r: float(r["NewsIndependentShock7v28"]), reverse=True)[:10]
    weekly.append({
        "Week": week,
        "N": len(wr),
        "NewsRankIC": spearman(xs, ys),
        "NewsTop10Excess": sum(float(r["ExcessRet"]) for r in top) / len(top),
        "IndependentNewsRankIC": spearman(ixs, ys),
        "IndependentNewsTop10Excess": sum(float(r["ExcessRet"]) for r in itop) / len(itop),
        "TotalCurr7News": sum(int(r["NewsCurr7"]) for r in wr),
        "TotalBase28News": sum(int(r["NewsBase28"]) for r in wr),
    })

base_weekly = list(weekly)
weekly.append({
    "Week": "OVERALL_MEAN",
    "N": sum(r["N"] for r in base_weekly),
    "NewsRankIC": sum(r["NewsRankIC"] for r in base_weekly if r["NewsRankIC"] is not None) / len([r for r in base_weekly if r["NewsRankIC"] is not None]),
    "NewsTop10Excess": sum(r["NewsTop10Excess"] for r in base_weekly) / len(base_weekly),
    "IndependentNewsRankIC": sum(r["IndependentNewsRankIC"] for r in base_weekly if r["IndependentNewsRankIC"] is not None) / len([r for r in base_weekly if r["IndependentNewsRankIC"] is not None]),
    "IndependentNewsTop10Excess": sum(r["IndependentNewsTop10Excess"] for r in base_weekly) / len(base_weekly),
    "TotalCurr7News": sum(r["TotalCurr7News"] for r in base_weekly),
    "TotalBase28News": sum(r["TotalBase28News"] for r in base_weekly),
})

with open(OUT_WEEKLY, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(weekly[0]))
    w.writeheader(); w.writerows(weekly)

for r in weekly:
    print(r, flush=True)
