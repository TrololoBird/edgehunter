import asyncio
import os
import sqlite3
import time

import pytest

import config as config_mod
from config import CONFIG, AppConfig, apply_overrides, load_overrides


def test_overrides_apply_and_validate(tmp_path):
    cfg = apply_overrides(AppConfig(), {'tier0': {'rvol_1m_threshold': 6}, 'venues': {'enabled': ['bybit']},
                                        'notify': {'enabled': True}})
    assert cfg.tier0.rvol_1m_threshold == 6.0 and cfg.venues.enabled == ('bybit',) and cfg.notify.enabled
    for bad in ({'nope': {}}, {'tier0': {'nope': 1}}, {'tier0': {'rvol_1m_threshold': 'x'}},
                {'notify': {'enabled': 1}}, {'journal': {'cooldown_sec': 1.5}}):
        with pytest.raises(ValueError):
            apply_overrides(AppConfig(), bad)
    path = tmp_path / 'config.local.toml'
    path.write_text('[tier0]\nrvol_1m_threshold = 7.5\n', encoding='utf-8')
    assert load_overrides(AppConfig(), str(path)).tier0.rvol_1m_threshold == 7.5
    assert load_overrides(AppConfig(), str(tmp_path / 'missing.toml')).tier0.rvol_1m_threshold == 5.0


class FakeExchange:
    def __init__(self, used_header=None, fail_times=0, exc=None):
        self.last_response_headers = {}
        self.used_header = used_header
        self.fail_times = fail_times
        self.exc = exc
        self.calls = 0

    async def ping(self):
        self.calls += 1
        if self.fail_times:
            self.fail_times -= 1
            raise self.exc
        if self.used_header is not None:
            self.last_response_headers = {'x-mbx-used-weight-1m': str(self.used_header)}
        return 'pong'


def test_rest_gate_budget_by_priority_and_headers():
    from ratelimit import RestGate
    gate = RestGate('test', 100, used_weight_header='X-MBX-USED-WEIGHT-1M')
    # budget_share 0.7: priority 0 may use 70, priority 2 only 0.55 of that
    assert gate.budget(0) == pytest.approx(70) and gate.budget(2) == pytest.approx(38.5)
    ex = FakeExchange(used_header=60)
    assert asyncio.run(gate.call(ex, 'ping', priority=0)) == 'pong'
    assert gate.used >= 60                               # synced from the exchange's own counter

    async def low_priority_waits():
        return await asyncio.wait_for(gate.call(ex, 'ping', priority=2), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(low_priority_waits())               # 60 >= 38.5: waits for the next minute


def test_rest_gate_pauses_on_ban():
    from ccxt import DDoSProtection
    from ratelimit import RestGate
    gate = RestGate('test', 1000)
    ban_end_ms = int((time.time() + 1.2) * 1000)
    ex = FakeExchange(fail_times=1, exc=DDoSProtection(f'IP banned until {ban_end_ms}'))
    started = time.time()
    assert asyncio.run(gate.call(ex, 'ping')) == 'pong'
    assert time.time() - started >= 1.0 and ex.calls == 2


# ---------------------------------------------------------------------- journal / stats

def _sig(**kw):
    base = dict(is_structured=False, alert_type='ANOMALY', rvol_1m=4.0, whale_net_5m=0.0, price_change_5m=0.0,
                oi_change_5m=0.0)
    base.update(kw)
    return base


def test_classification_and_families():
    from journal import classify, veto_reason
    assert classify(_sig(price_change_5m=-0.03))[1] == 'IMPULSE UNCONFIRMED'
    assert classify(_sig(price_change_5m=-0.03, oi_change_5m=0.01, futures_cvd_5m=-2e5))[1:] == ('IMPULSE DOWN', -1)
    assert classify(_sig(price_change_5m=0.03, oi_change_5m=0.001, futures_cvd_5m=2e5))[1] == 'IMPULSE UNCONFIRMED'
    assert classify(_sig(price_change_5m=0.03, oi_change_5m=-0.01))[1] == 'SHORT SQUEEZE'
    # observed liquidations decide squeeze / flush even when OI did not fall
    assert classify(_sig(price_change_5m=0.03, oi_change_5m=0.01, liq_cascade=True, liq_short_5m=9e4, liq_long_5m=1e3,
                         futures_cvd_5m=1e5))[1] == 'SHORT SQUEEZE'
    assert classify(_sig(liq_cascade=True, liq_long_5m=9e4))[1] == 'LIQ CASCADE'
    assert classify(_sig(cluster=1))[1:] == ('ALGO BUY', 1)
    assert classify(_sig(venues_active=3, top_venue_share=0.9, top_venue_net=4e5))[1] == 'ONE-VENUE'
    # a 1.5% move on a coin whose typical 5m move is 0.2% is an impulse; the same move with z 2 is not
    assert classify(_sig(price_change_5m=0.015, price_z=8, oi_change_5m=0.01, futures_cvd_5m=1e5))[1] == 'IMPULSE UP'
    assert classify(_sig(price_change_5m=0.015, price_z=2))[1] != 'IMPULSE UP'
    up = _sig(price_change_5m=0.03, oi_change_5m=0.01, futures_cvd_5m=1e5, has_spot=True)
    assert veto_reason('IMPULSE UP', dict(up, spot_cvd_5m=-1e4)) == 'perp_led'
    assert veto_reason('IMPULSE UP', dict(up, spot_cvd_5m=5e4)) is None
    assert veto_reason('BEAR D', {'has_spot': True, 'perp_led_short': True}) == 'perp_led'


def test_journal_record_entry_veto_and_universe(tmp_path):
    from journal import SignalJournal
    j = SignalJournal(str(tmp_path / 'j.db'))
    assert j.conn.execute("PRAGMA journal_mode").fetchone()[0] == 'wal'
    unc = _sig(price_change_5m=0.03, futures_cvd_5m=1e5)
    sq = _sig(price_change_5m=0.03, oi_change_5m=-0.01)
    conf = _sig(price_change_5m=0.03, oi_change_5m=0.01, futures_cvd_5m=1e5, has_spot=True, spot_cvd_5m=-1e4)
    assert j.record([('F', unc)], {'F': 1.0}) == 1
    assert j.record([('F', sq)], {'F': 1.0}) == 0            # same event relabelled
    assert asyncio.run(j.arecord([('F', conf)], {'F': 1.0})) == 1   # stronger reading, from a worker thread
    row = j.conn.execute("SELECT group_key, vetoed, logic_version FROM signals ORDER BY id DESC").fetchone()
    assert row == ('IMPULSE UP', 'perp_led', CONFIG.journal.logic_version)
    assert j.snapshot_universe({'A': 1.0, 'B': 2.0, 'C': None}) == 2
    assert j.snapshot_universe({'A': 1.0}) == 0              # at most once per universe_snapshot_sec
    j.close()
    j2 = SignalJournal(str(tmp_path / 'j.db'))               # restart keeps family cooldowns
    assert j2.record([('F', sq)], {'F': 1.0}) == 0
    j2.close()


def test_journal_outcomes_manual_fill_and_retry(tmp_path):
    from journal import SignalJournal
    j = SignalJournal(str(tmp_path / 'o.db'))
    t_old = int((time.time() - 9 * 3600) * 1000)      # every horizon due, 8h (the entry replay) included
    j.conn.execute("INSERT INTO signals (ts_ms, symbol, kind, group_key, direction, price, entry, sl, tp1, tp2, tp3, "
                   "logic_version) VALUES (?, 'E', 'entry', 'ENTRY IMPULSE UP', 1, 100, 100, 98, 104, 106, 108, 'mtf-4')",
                   (t_old,))
    for i in range(80):
        j.conn.execute("INSERT INTO signals (ts_ms, symbol, kind, group_key, direction, price, logic_version) "
                       "VALUES (?, 'E', 'anomaly', 'VOLUME SPIKE', 0, 1.0, 'mtf-4')", (t_old + 1 + i,))
    j.conn.commit()
    calls = []

    class Fetcher:
        async def fetch_minute_klines(self, symbol, start, count):
            calls.append(count)
            return [[0, 100, 104.5, 99.5, 104]] + [[0, 104, 104.2, 103.9, 104]] * (count - 1)

    asyncio.run(j._evaluate_pass(Fetcher()))
    entry = j.conn.execute("SELECT outcome, entry_fill, r_tp1, filled FROM signals WHERE kind='entry'").fetchone()
    assert entry[0] == 'TP1' and entry[1] > 100 and entry[3] == 1 and 0 < entry[2] < 2
    assert set(calls) == {480}
    row = j._pending(10)
    j.close()


def test_stats_universe_baseline_bootstrap_and_fees(tmp_path):
    import stats
    from journal import SignalJournal
    db = str(tmp_path / 's.db')
    j = SignalJournal(db)
    t0 = 3_600_000 * 400_000
    # the whole universe fell 1% over 4h; our short fell 1% too -> zero edge
    for k, factor in ((0, 1.0), (16, 0.99)):
        j.conn.executemany("INSERT INTO universe VALUES (?, ?, ?)",
                           [(t0 + k * 900_000, f'S{i}', 10.0 * factor) for i in range(30)])
    j.conn.execute("INSERT INTO signals (ts_ms, symbol, kind, group_key, direction, price, ret_4h, logic_version) "
                   "VALUES (?, 'X', 'anomaly', 'IMPULSE DOWN', -1, 1.0, -0.01, 'mtf-4')", (t0 + 1000,))
    j.conn.commit()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM signals").fetchall()
    base = stats.Baseline(rows, stats.UniverseBaseline(conn))
    assert base.universe and base.of(rows[0], '4h') == pytest.approx(-0.01)
    g = stats.group_stats(rows, base)
    assert g['avg_4h'] > 0 and abs(g['edge_4h']) < 1e-12
    lo, hi = stats.bootstrap_ci([0.01, 0.02, 0.015, 0.012, 0.018, 0.011])
    assert 0 < lo <= hi
    assert stats.bootstrap_ci([1.0, 2.0]) is None
    fake = {'r_tp1': 2.0, 'entry_fill': 100.0, 'entry': 100.0, 'sl': 98.0}

    class Row(dict):
        def keys(self):
            return super().keys()
    assert stats.net_r(Row(fake), 'r_tp1') == pytest.approx(2.0 - 0.001 * 100 / 2)
    conn.close()
    j.close()


def test_main_ctrl_c_and_logging_setup():
    import logging
    import main as main_mod
    # (pytest's own logging plugin installs a FileHandler of its own: look for ours by file name)
    assert not any(str(getattr(h, 'baseFilename', '')).endswith('scanner.log') for h in logging.getLogger().handlers), \
        "importing main must not open scanner.log"
    loop = asyncio.new_event_loop()
    ge = main_mod.GracefulExit(loop)
    ge(2)
    ge(2)                                  # second press within 3s: ignored, no exit
    loop.run_until_complete(asyncio.sleep(0.01))
    assert ge.shutdown_event.is_set()
    loop.close()
