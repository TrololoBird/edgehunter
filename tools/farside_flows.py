"""
Daily job OUTSIDE the bot (systemd timer / cron, ~08:30 UTC): spot-ETF net flows from Farside and the NYSE calendar.

- etf_flows.json  {"YYYY-MM-DD": total net flow of all US spot BTC ETFs, USD m} - the extdata macro_loop reads it and
  shows a day D only from D+1 08:00 UTC (no look-ahead). Farside answers 403 to plain HTTP clients (Cloudflare TLS
  fingerprint); curl_cffi with a Chrome fingerprint gets the page. One request a day, the last 5 rows are re-read from
  the table every run (issuers revise the latest days).
- us_calendar.json  {"closed": [weekday holidays], "early": [13:00 ET closes]} for the next 400 days, from
  exchange_calendars (XNYS): the bot gets the NYSE session flag without importing pandas.

    python tools/farside_flows.py [--out-dir /opt/pump] [--html saved_page.html]   # --html: parse a local file (no network)
"""
import argparse
import json
import os
import sys
from html.parser import HTMLParser
from datetime import date, datetime, timedelta

FARSIDE = 'https://farside.co.uk/btc/'                 # the latest ~2 weeks
FARSIDE_ALL = 'https://farside.co.uk/bitcoin-etf-flow-all-data/'     # since the launch (2024-01-11): --history once


def num(cell):
    """Farside cells: '123.4', '(45.6)' = outflow, '-' = no data (the issuer has not reported yet), '0.0'."""
    t = str(cell).strip().replace(',', '')
    if t in ('', '-', 'nan', 'None'):
        return None
    neg = t.startswith('(') and t.endswith(')')
    t = t.strip('()')
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self._row, self._cell, self._in = [], None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.tables.append([])
        elif tag == 'tr' and self.tables:
            self._row = []
        elif tag in ('td', 'th') and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self._cell is not None and self._row is not None:
            self._row.append(''.join(self._cell).strip())
            self._cell = None
        elif tag == 'tr' and self._row is not None:
            if self._row:
                self.tables[-1].append(self._row)
            self._row = None


def parse_flows(html: str) -> dict:
    """{'YYYY-MM-DD': total net flow USD m} from Farside's HTML table; a day with no total yet is left out."""
    p = _Tables()
    p.feed(html)
    best = {}
    for rows in p.tables:                                 # the header holds fund logos, not text: the LAST column is the total
        out = {}
        for r in rows:
            if len(r) < 3:
                continue
            try:
                d = datetime.strptime(r[0].strip(), '%d %b %Y').strftime('%Y-%m-%d')
            except ValueError:
                continue                                  # header, Total / Average / Maximum / Minimum rows
            cells = [num(c) for c in r[1:-1]]
            tot = num(r[-1])
            if tot is not None and any(c is not None for c in cells):
                out[d] = tot
        if len(out) > len(best):
            best = out
    return best


def write_json(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def calendar_days(days=400):
    import exchange_calendars as xcals
    import pandas as pd
    cal = xcals.get_calendar('XNYS')
    a, b = date.today() - timedelta(days=30), min(date.today() + timedelta(days=days), cal.last_session.date())
    sessions = {s.strftime('%Y-%m-%d') for s in cal.sessions_in_range(pd.Timestamp(a), pd.Timestamp(b))}
    closed, d = [], a
    while d <= b:
        if d.weekday() < 5 and d.isoformat() not in sessions:
            closed.append(d.isoformat())
        d += timedelta(days=1)
    early = [e.strftime('%Y-%m-%d') for e in cal.early_closes if a <= e.date() <= b]
    return {'closed': closed, 'early': early}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    ap.add_argument('--history', action='store_true', help='read the all-data page (first run / backtest)')
    ap.add_argument('--html', default=None, help='parse a saved page instead of fetching')
    args = ap.parse_args()
    path = os.path.join(args.out_dir, 'etf_flows.json')
    try:
        write_json(os.path.join(args.out_dir, 'us_calendar.json'), calendar_days())
    except Exception as e:                                # the bot falls back to weekday + hours
        print(f"us_calendar.json not written: {e!r}")
    if args.html:
        with open(args.html, encoding='utf-8') as f:
            html = f.read()
    else:
        from curl_cffi import requests
        r = requests.get(FARSIDE_ALL if args.history else FARSIDE, impersonate='chrome', timeout=30)
        if r.status_code != 200:
            sys.exit(f"farside: HTTP {r.status_code}")
        html = r.text
    new = parse_flows(html)
    if not new:
        sys.exit('farside: no flow rows parsed (page layout changed?)')
    old = {}
    try:
        with open(path, encoding='utf-8') as f:
            old = json.load(f)
    except (OSError, ValueError):
        pass
    old.update(new)                                       # the whole table is re-read: the revised days overwrite
    write_json(path, dict(sorted(old.items())))
    print(f"etf_flows.json: {len(old)} days, last {max(old)} = {old[max(old)]}")


if __name__ == '__main__':
    main()
