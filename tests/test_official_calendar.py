"""eng-168t: official macro schedules (BLS iCalendar, ISM table, FOMC page) - parsing, merge, coverage."""
from datetime import datetime
from zoneinfo import ZoneInfo

import official_calendar as oc

NY = ZoneInfo('America/New_York')

BLS = """BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDTSTART;TZID=US-Eastern:20261110T083000\r\nSUMMARY:Consumer Price Index\r\nEND:VEVENT\r
BEGIN:VEVENT\r\nDTSTART;TZID=US-Eastern:20261106T083000\r\nSUMMARY:Employment Situation\r\nEND:VEVENT\r
BEGIN:VEVENT\r\nDTSTART;TZID=US-Eastern:20260320T100000\r\nSUMMARY:Employment Situation of Veterans\r\nEND:VEVENT\r
BEGIN:VEVENT\r\nDTSTART;TZID=US-Eastern:20261113T083000\r\nSUMMARY:Producer Price Index\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"""
ISM = ("<p>2026 ISM PMI Reports Release Dates</p><table><tr><td>January 2026</td><td>5</td><td>7</td></tr>"
       "<tr><td>July 2026</td><td>1</td><td>6 **</td></tr></table>")
FED = ('<h4>2026 FOMC Meetings</h4><div class="fomc-meeting__month"><strong>October</strong></div>'
       '<div class="fomc-meeting__date">27-28</div>'
       '<div class="fomc-meeting__month"><strong>Apr/May</strong></div><div class="fomc-meeting__date">30-1</div>'
       '<div class="fomc-meeting__month"><strong>August</strong></div>'
       '<div class="fomc-meeting__date">22 (notation vote)</div>')


def _ms(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=NY).timestamp() * 1000)


def test_bls_keeps_cpi_nfp_ppi_in_new_york_time():
    ev = {e['type']: e for e in oc.parse_bls(BLS)}
    assert set(ev) == {'CPI', 'NFP', 'PPI'}                  # 'Employment Situation of Veterans' is not NFP
    assert ev['CPI']['t'] == _ms(2026, 11, 10, 8, 30)        # EST date (after the DST change) handled by zoneinfo


def test_ism_table_rows_with_holiday_marks():
    ev = {e['id']: e for e in oc.parse_ism(ISM)}
    assert ev['ISM:ISM_M:202601']['t'] == _ms(2026, 1, 5, 10, 0)
    assert ev['ISM:ISM_S:202607']['t'] == _ms(2026, 7, 6, 10, 0)


def test_fomc_statement_and_press_conference_on_the_last_day():
    ev = {e['id']: e for e in oc.parse_fed(FED)}
    assert ev['FED:FOMC:20261028']['t'] == _ms(2026, 10, 28, 14, 0)
    assert ev['FED:FOMC_PC:20261028']['t'] == _ms(2026, 10, 28, 14, 30)
    assert 'FED:FOMC:20260501' in ev                         # Apr/May 30-1 -> May 1
    assert not any('0822' in k for k in ev)                   # notation vote skipped


def test_an_event_missing_from_a_new_fetch_stays_unconfirmed():
    old = [{'id': 'BLS:CPI:20261110', 'type': 'CPI', 'source': 'BLS', 't': 10_000, 'title': 'CPI', 'status': 'scheduled'}]
    new = [{'id': 'BLS:NFP:20261106', 'type': 'NFP', 'source': 'BLS', 't': 9_000, 'title': 'NFP', 'status': 'scheduled'}]
    merged = oc.merge(old, new, 'BLS', now_ms=1_000)
    st = {e['id']: e['status'] for e in merged}
    assert st == {'BLS:NFP:20261106': 'scheduled', 'BLS:CPI:20261110': 'unconfirmed'}


def test_coverage_needs_freshness_and_a_schedule_reaching_ahead(monkeypatch):
    now = 1_800_000_000_000
    day = 86_400_000
    src = {'BLS': {'fetched_at': now / 1000, 'cover_end': now + 30 * day},
           'FED': {'fetched_at': now / 1000, 'cover_end': now + 30 * day},
           'ISM': {'fetched_at': now / 1000, 'cover_end': now + 2 * day}}       # the year's table ends soon
    monkeypatch.setattr(oc, 'STATE', {'events': [], 'sources': src})
    assert oc.uncovered(now) == ['ISM_M', 'ISM_S']
    src['BLS']['fetched_at'] = now / 1000 - oc.OFFICIAL_MAX_AGE_SEC - 1
    assert 'CPI' in oc.uncovered(now)


def test_refresh_keeps_a_failed_source_and_records_the_error(monkeypatch, tmp_path):
    monkeypatch.setattr(oc, 'CACHE', str(tmp_path / 'c.json'))
    pages = {oc.URLS['BLS']: BLS, oc.URLS['ISM']: ISM}

    def fetch(url):
        if url not in pages:
            raise OSError('down')
        return pages[url]
    st = oc.refresh(now=1_790_000_000, fetch=fetch)
    assert st['sources']['BLS']['n'] == 3 and st['sources']['FED']['error'].startswith('OSError')
