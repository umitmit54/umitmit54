from __future__ import annotations

import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

START = date(2021, 1, 1)
END = date(2026, 9, 4)
OUT = Path('uos_borsa_output')
OUT.mkdir(exist_ok=True)


def weekdays(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def fetch_one(d: date):
    ymd = d.strftime('%Y%m%d')
    url = f'https://borsaistanbul.com/data/thb/{d:%Y}/{d:%m}/thb{ymd}1.zip'
    try:
        r = requests.get(url, timeout=35, headers={'User-Agent': 'Mozilla/5.0 UOS-Borsa-Research/1.0'})
        if r.status_code != 200 or not r.content.startswith(b'PK'):
            return d, None, r.status_code
        return d, r.content, 200
    except Exception as exc:
        return d, None, f'ERR:{type(exc).__name__}'


def parse_bulletin(d: date, blob: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith('.csv')]
        if not names:
            raise ValueError('zip_has_no_csv')
        raw = zf.read(names[0])
    text = raw.decode('cp1254', errors='replace')
    lines = text.splitlines()
    if not lines:
        raise ValueError('empty_csv')
    skip = 1 if len(lines) > 1 and lines[0].startswith('TARIH;') and lines[1].startswith('TRADE DATE;') else 0
    df = pd.read_csv(io.StringIO(text), sep=';', skiprows=skip, low_memory=False)
    required = [
        'TRADE DATE', 'INSTRUMENT SERIES CODE', 'INSTRUMENT NAME', 'INSTRUMENT TYPE',
        'BIST 100 INDEX', 'OPENING PRICE', 'LOWEST PRICE', 'HIGHEST PRICE',
        'CLOSING PRICE', 'TOTAL TRADED VOLUME', 'TOTAL TRADED VALUE'
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError('missing_columns:' + ','.join(missing))
    eq = df[(df['INSTRUMENT TYPE'].astype(str).str.strip() == 'EQT') &
            (df['INSTRUMENT SERIES CODE'].astype(str).str.endswith('.E'))].copy()
    eq['symbol'] = eq['INSTRUMENT SERIES CODE'].astype(str).str.replace(r'\.E$', '', regex=True)
    out = pd.DataFrame({
        'date': pd.to_datetime(eq['TRADE DATE'], errors='coerce').dt.strftime('%Y-%m-%d'),
        'symbol': eq['symbol'],
        'name': eq['INSTRUMENT NAME'].astype(str).str.strip(),
        'open': pd.to_numeric(eq['OPENING PRICE'], errors='coerce'),
        'high': pd.to_numeric(eq['HIGHEST PRICE'], errors='coerce'),
        'low': pd.to_numeric(eq['LOWEST PRICE'], errors='coerce'),
        'close': pd.to_numeric(eq['CLOSING PRICE'], errors='coerce'),
        'volume': pd.to_numeric(eq['TOTAL TRADED VOLUME'], errors='coerce'),
        'turnover_try': pd.to_numeric(eq['TOTAL TRADED VALUE'], errors='coerce'),
        'bist100_pit': pd.to_numeric(eq['BIST 100 INDEX'], errors='coerce').fillna(0).astype('int8'),
        'source': f'BIST_thb_{d:%Y%m%d}1',
    })
    return out


def get_benchmark() -> pd.DataFrame:
    from tvDatafeed import TvDatafeed, Interval
    tv = TvDatafeed()
    df = tv.get_hist(symbol='XU100_CFNNTLTL', exchange='BIST', interval=Interval.in_daily, n_bars=3000)
    if df is None or df.empty:
        raise RuntimeError('benchmark_empty')
    x = df.reset_index().copy()
    dtcol = x.columns[0]
    x['date'] = pd.to_datetime(x[dtcol], errors='coerce').dt.strftime('%Y-%m-%d')
    x = x[(x['date'] >= START.isoformat()) & (x['date'] <= END.isoformat())]
    cols = ['date', 'open', 'high', 'low', 'close']
    if 'volume' in x.columns:
        cols.append('volume')
    x = x[cols].copy()
    x['symbol'] = 'XU100_CFNNTLTL'
    x['source'] = 'TradingView:BIST:XU100_CFNNTLTL'
    return x[['date', 'symbol'] + [c for c in ['open','high','low','close','volume'] if c in x.columns] + ['source']]


def main():
    dates = list(weekdays(START, END))
    fetched = {}
    statuses = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch_one, d): d for d in dates}
        for i, fut in enumerate(as_completed(futs), 1):
            d, blob, status = fut.result()
            statuses.append({'date': d.isoformat(), 'http_status': status, 'downloaded': blob is not None})
            if blob is not None:
                fetched[d] = blob
            if i % 100 == 0:
                print(f'downloaded-check {i}/{len(dates)} success={len(fetched)}', flush=True)

    frames = []
    parse_errors = []
    for i, d in enumerate(sorted(fetched), 1):
        try:
            frames.append(parse_bulletin(d, fetched[d]))
        except Exception as exc:
            parse_errors.append({'date': d.isoformat(), 'error': str(exc)})
        if i % 100 == 0:
            print(f'parsed {i}/{len(fetched)} errors={len(parse_errors)}', flush=True)

    if not frames:
        raise RuntimeError('no_bulletins_parsed')
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.dropna(subset=['date', 'symbol']).sort_values(['date', 'symbol'])
    panel = panel.drop_duplicates(['date', 'symbol'], keep='last')

    benchmark = get_benchmark().sort_values('date').drop_duplicates('date', keep='last')

    panel_dates = set(panel['date'].unique())
    bench_dates = set(benchmark['date'].unique())
    bench_missing_bulletin = sorted(bench_dates - panel_dates)
    bulletin_missing_bench = sorted(panel_dates - bench_dates)

    ohlc_bad = panel[(panel['high'] < panel[['open','close','low']].max(axis=1)) |
                     (panel['low'] > panel[['open','close','high']].min(axis=1))]
    b100_counts = panel[panel['bist100_pit'] == 1].groupby('date')['symbol'].nunique()

    panel.to_csv(OUT / 'BIST_EQUITY_OHLCV_2021-01-01_2026-09-04.csv.gz', index=False, compression='gzip')
    benchmark.to_csv(OUT / 'XU100_RETURN_OHLC_2021-01-01_2026-09-04.csv', index=False)
    pd.DataFrame(statuses).sort_values('date').to_csv(OUT / 'BULLETIN_DOWNLOAD_MANIFEST.csv', index=False)
    pd.DataFrame(parse_errors).to_csv(OUT / 'PARSE_ERRORS.csv', index=False)
    pd.DataFrame({'date': bench_missing_bulletin}).to_csv(OUT / 'TRUE_MISSING_BULLETIN_DATES.csv', index=False)
    pd.DataFrame({'date': bulletin_missing_bench}).to_csv(OUT / 'BENCHMARK_GAP_DATES.csv', index=False)

    report = {
        'period': [START.isoformat(), END.isoformat()],
        'official_bulletins_downloaded': len(fetched),
        'official_bulletins_parsed': len(panel_dates),
        'equity_rows': int(len(panel)),
        'unique_symbols': int(panel['symbol'].nunique()),
        'benchmark_rows': int(len(benchmark)),
        'benchmark_first_date': str(benchmark['date'].min()),
        'benchmark_last_date': str(benchmark['date'].max()),
        'benchmark_dates_without_bulletin': bench_missing_bulletin,
        'bulletin_dates_without_benchmark': bulletin_missing_bench,
        'parse_error_count': len(parse_errors),
        'ohlc_invariant_error_rows': int(len(ohlc_bad)),
        'duplicate_date_symbol_rows_after_dedup': int(panel.duplicated(['date','symbol']).sum()),
        'bist100_pit_daily_member_count_min': int(b100_counts.min()) if len(b100_counts) else None,
        'bist100_pit_daily_member_count_max': int(b100_counts.max()) if len(b100_counts) else None,
        'complete_gate': bool(len(parse_errors) == 0 and len(bench_missing_bulletin) == 0 and len(bulletin_missing_bench) == 0 and len(ohlc_bad) == 0),
        'sources': {
            'equity_ohlcv': 'https://borsaistanbul.com/data/thb/YYYY/MM/thbYYYYMMDD1.zip',
            'benchmark': 'TradingView BIST:XU100_CFNNTLTL',
        },
    }
    (OUT / 'QUALITY_REPORT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
