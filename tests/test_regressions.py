import pytest
import asyncio
import time
import ccxt
import polars as pl

from sqlsafe import identifier
from security import safe_urlopen
from strategies.base import validate_card_levels
from journal import EXTRA_COLUMNS, shrinkage_upper, wilson_upper
from depth import BookState, DepthBook
from extdata import okx_completed_bucket, okx_taker_rows
from levels import simulate
from executor import credentials, DemoExecutor
from fetcher import DataFetcher, MarketData, normalize_binance_liquidation
from scanner import Scanner
from flow import FlowStore, LIQ_SHORT, Sweep
from data_quality import QualityState
from extdata import ExternalData
from core.quant_gate import scenario_gate
from signal_book import SignalBook, TrackedSignal
import pumps
from iceberg import IcebergDetector
from history_coverage import coverage as candle_coverage
from history_coverage import TF_MS
from config import CONFIG


def test_candle_coverage_reports_gaps_and_conflicts_without_false_ready():
    step = 60_000
    start = 1_700_000_000_000 // step * step
    rows = [[start + i * step, 10, 11, 9, 10, 1] for i in range(5)]
    assert candle_coverage(rows, '1m', start + 6 * step, required=4)['state'] == 'READY'

    missing = rows[:2] + rows[3:]
    state = candle_coverage(missing, '1m', start + 6 * step, required=4)
    assert state['state'] == 'DATA_GAP'
    assert state['missing_bars'] == 1
    assert state['gaps'] == [{'start_ms': start + 2 * step,
                              'end_ms': start + 2 * step, 'missing_bars': 1}]

    conflicting = rows + [[start + 2 * step, 10, 12, 9, 10, 1]]
    state = candle_coverage(conflicting, '1m', start + 6 * step, required=4)
    assert state['state'] == 'INVALID'
    assert state['conflicting_bars'] == 1
    assert not state['ready']


def test_candle_coverage_rejects_bad_timestamp_and_does_not_require_prelisting_history():
    step = 3_600_000
    start = 1_700_000_000_000 // step * step
    rows = [[start + i * step, 10, 11, 9, 10, 1] for i in range(2)]
    rows.append([start + 2 * step + 1, 10, 11, 9, 10, 1])
    state = candle_coverage(rows, '1h', start + 4 * step, required=5, listed_ms=start)
    assert state['state'] == 'INVALID'
    assert state['invalid_bars'] == 1

    valid = rows[:2]
    state = candle_coverage(valid, '1h', start + 3 * step, required=5, listed_ms=start)
    assert state['state'] == 'LISTING_TOO_RECENT'


def test_minute_hole_detection_includes_missing_leading_bar_in_expected_window():
    step = 60_000
    end = 1_700_000_000_000 // step * step
    rows = [[end - (i * step), 10, 11, 9, 10, 1, 0, 1] for i in range(238, -1, -1)]
    holes = DataFetcher.minute_holes(rows, end, window=240)
    assert holes == [end - 239 * step]

    listed = end - 120 * step
    assert DataFetcher.minute_holes(rows, end, window=240, listed_ms=listed) == []


def test_binance_kline_page_validation_rejects_invalid_and_conflicting_rows():
    step = 60_000
    ts = 1_700_000_000_000 // step * step
    row = [ts, '10', '11', '9', '10', '3', ts + step - 1, '30', '5', '2', '20', '0']
    assert DataFetcher._validate_binance_klines([row], '1m', now_ms=ts + step + 5000) == [row]
    with pytest.raises(ValueError, match='impossible|nonfinite'):
        DataFetcher._validate_binance_klines([[*row[:5], 'nan', *row[6:]]], '1m', now_ms=ts + step + 5000)
    conflict = [*row]
    conflict[4] = '10.5'
    conflict[2] = '11'
    with pytest.raises(ValueError, match='conflicting duplicate'):
        DataFetcher._validate_binance_klines([row, conflict], '1m', now_ms=ts + step + 5000)
    misaligned = [*row]
    misaligned[0] += 1
    with pytest.raises(ValueError, match='misaligned'):
        DataFetcher._validate_binance_klines([misaligned], '1m', now_ms=ts + step + 5000)

    week = TF_MS['1w']
    weekly_ts = 4 * 86_400_000 + 270 * week
    weekly = [weekly_ts, '10', '11', '9', '10', '3', weekly_ts + week - 1, '30', '5', '2', '20', '0']
    assert DataFetcher._validate_binance_klines([weekly], '1w', now_ms=weekly_ts + week + 5000) == [weekly]


def test_websocket_candle_does_not_advance_quality_on_invalid_payload():
    md = MarketData(symbol='BTC/USDT:USDT')
    step = 60_000
    ts = int(time.time() * 1000) // step * step
    event = {'i': '1m', 't': ts, 'T': ts + step - 1, 'o': '10', 'h': '11', 'l': '9', 'c': '10',
             'v': '3', 'q': '30', 'V': '2', 'Q': '20', 'n': 5, 'x': False}
    invalid = dict(event, c='nan')
    md.apply_kline('futures', invalid, ts + 500, received_ms=ts + 1000)
    assert md.kline_events_invalid == 1
    assert md.kline_last_exchange_ms == 0
    assert not md.minute_klines

    md.apply_kline('futures', event, ts + 500, received_ms=ts + 1500)
    assert md.kline_events_valid == 1
    assert md.kline_last_exchange_ms == ts + 500
    assert md.kline_last_candle_open_ms == ts
    assert md.kline_last_candle_close_ms == ts + step - 1
    assert md.kline_last_receive_ms == ts + 1500
    assert md.kline_last_latency_ms == 1000
    assert md.kline_event == (ts, ts + 1500)
    assert md.minute_klines[-1][0] == ts


def test_websocket_kline_requires_exchange_event_timestamp():
    md = MarketData(symbol='BTC/USDT:USDT')
    ts = int(time.time() * 1000) // 60_000 * 60_000
    event = {'i': '1m', 't': ts, 'T': ts + 59_999, 'o': '10', 'h': '11', 'l': '9', 'c': '10',
             'v': '3', 'q': '30', 'V': '2', 'Q': '20', 'n': 5, 'x': False}
    md.apply_kline('futures', event, received_ms=ts + 1000)
    assert md.kline_events_invalid == 1
    assert md.kline_last_receive_ms == 0
    assert md.kline_last_candle_close_ms == 0


def test_candle_recovery_publishes_only_after_full_window_revalidation():
    timeframe = '4h'
    step = 14_400_000
    now_ms = int(time.time() * 1000)
    last_closed = now_ms // step * step - step
    start = last_closed - 29 * step
    rows = [[start + i * step, '10', '11', '9', '10', '3', start + i * step + step - 1,
             '30', '5', '2', '20', '0'] for i in range(30)]
    symbol = 'BTC/USDT:USDT'
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher.futures_exchange = type('Exchange', (), {'markets': {symbol: {'info': {'onboardDate': start}}}})()
    fetcher._history_status = {}
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0, 'failed': 0}
    fetcher.markets = {symbol: MarketData(symbol=symbol, baseline_ready=True, listed_ms=start)}

    async def page(*args, **kwargs):
        return rows

    fetcher._fetch_klines = page
    status = asyncio.run(fetcher._recover_history_window(symbol, fetcher.markets[symbol], timeframe))
    assert status['timeframes'][timeframe]['quality'] == 'VALID_COMPLETE'
    assert status['ready'] is False  # independent TF histories are still recovering
    assert fetcher.history_recovery_stats['recovered'] == 1


def test_frame_gap_recovery_fetches_and_reconciles_exact_missing_interval():
    timeframe = CONFIG.timeframe.rest_timeframe
    step = TF_MS[timeframe]
    now_ms = int(time.time() * 1000)
    last_closed = now_ms // step * step - step
    first, missing, last = last_closed - 2 * step, last_closed - step, last_closed

    def row(ts):
        return [ts, '10', '11', '9', '10', '3', ts + step - 1, '30', '5', '2', '20', '0']

    symbol = 'BTC/USDT:USDT'
    fetcher = DataFetcher.__new__(DataFetcher)

    class Exchange:
        markets = {symbol: {'id': 'BTCUSDT'}}

        def market(self, _symbol):
            return self.markets[_symbol]

    fetcher.futures_exchange = Exchange()
    fetcher.spot_exchange = Exchange()

    async def rest(exchange, method, params, **kwargs):
        assert method == 'fapiPublicGetKlines'
        assert params['startTime'] == missing
        assert params['endTime'] == missing + step - 1
        return [row(missing)]

    fetcher._rest_call = rest
    frame = fetcher._klines_to_df([row(first), row(last)])
    assert DataFetcher._frame_missing_ranges(frame, timeframe) == [(missing, missing, 1)]
    repaired, gaps = asyncio.run(fetcher._repair_frame_gap(symbol, 'futures', frame))
    assert gaps == []
    assert repaired['timestamp'].to_list() == [first, missing, last]


@pytest.mark.parametrize('failure', [
    TimeoutError('timeout'), ccxt.RequestTimeout('request timeout'),
    ccxt.RateLimitExceeded('rate limited'), ConnectionResetError('connection reset'),
])
def test_history_recovery_contains_network_and_rate_limit_failures(failure):
    fetcher = DataFetcher.__new__(DataFetcher)
    symbol, timeframe = 'BTC/USDT:USDT', '4h'
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    fetcher.futures_exchange = type('Exchange', (), {'markets': {symbol: {'id': 'BTCUSDT'}}})()
    fetcher._assess_history = lambda _s, _md, error=None: {'timeframes': {timeframe: {
        'state': 'STALE', 'quality': 'RECOVERING', 'gaps': [], 'missing_bars': 0}}, 'error': error}

    async def fail(*_args, **_kwargs):
        raise failure

    fetcher._fetch_klines = fail
    result = asyncio.run(fetcher._recover_history_window(symbol, MarketData(symbol=symbol, baseline_ready=True), timeframe))
    repair = fetcher._history_repair_state[(symbol, timeframe)]
    assert result['error'].startswith(type(failure).__name__)
    assert repair['attempts'] == 1
    assert repair['next_attempt'] > time.time()
    assert fetcher.history_recovery_stats['failed'] == 1


def test_recovery_rest_gate_contains_local_transport_failure_and_keeps_retry_state():
    """Exercise recovery through _rest_call and a deterministic in-process transport gate."""
    fetcher = DataFetcher.__new__(DataFetcher)
    symbol, timeframe = 'BTC/USDT:USDT', '4h'
    exchange = type('Exchange', (), {'id': 'binanceusdm', 'markets': {symbol: {'id': 'BTCUSDT'}}})()
    fetcher.futures_exchange = exchange
    fetcher.spot_exchange = None
    fetcher.venue_exchanges = {}
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    fetcher.markets = {symbol: MarketData(symbol=symbol, baseline_ready=True)}
    fetcher.universe_symbols = {symbol}
    fetcher._assess_history = lambda _s, _md, error=None: {
        'timeframes': {timeframe: {'state': 'STALE', 'quality': 'RECOVERING',
                                   'gaps': [], 'missing_bars': 0}}, 'error': error}
    calls = []

    class ControlledTransport:
        async def call(self, _exchange, method, *_args, **_kwargs):
            calls.append(method)
            raise ccxt.RequestTimeout('controlled local timeout')

    fetcher.gates = {'futures': ControlledTransport()}
    fetcher.raw_log = type('RawLog', (), {'append_rest': lambda *_args, **_kwargs: None})()

    async def through_rest(*_args, **kwargs):
        return await fetcher._rest_call(exchange, 'fapiPublicGetKlines', {}, **kwargs)

    fetcher._fetch_klines = through_rest
    result = asyncio.run(fetcher._recover_history_window(symbol, fetcher.markets[symbol], timeframe))
    repair = fetcher._history_repair_state[(symbol, timeframe)]
    assert calls == ['fapiPublicGetKlines']
    assert result['error'].startswith('RequestTimeout')
    assert repair['attempts'] == 1 and repair['next_attempt'] > time.time()
    assert fetcher.history_recovery_stats['failed'] == 1


def test_history_recovery_rejects_malformed_rest_page_with_bounded_retry():
    fetcher = DataFetcher.__new__(DataFetcher)
    symbol, timeframe = 'BTC/USDT:USDT', '4h'
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    fetcher.futures_exchange = type('Exchange', (), {'markets': {symbol: {'id': 'BTCUSDT'}}})()
    fetcher._assess_history = lambda _s, _md, error=None: {'timeframes': {timeframe: {
        'state': 'INVALID', 'quality': 'RECOVERING', 'gaps': [], 'missing_bars': 0}}, 'error': error}

    async def malformed(*_args, **_kwargs):
        return [[1, 'not-a-kline']]

    fetcher._fetch_klines = malformed
    result = asyncio.run(fetcher._recover_history_window(symbol, MarketData(symbol=symbol, baseline_ready=True), timeframe))
    assert 'ValueError' in result['error']
    assert fetcher._history_repair_state[(symbol, timeframe)]['attempts'] == 1
    assert fetcher.history_recovery_stats['failed'] == 1


def test_recovery_jobs_are_isolated_when_one_parallel_job_raises():
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    seen = []

    async def recover(symbol, md, timeframe):
        seen.append(symbol)
        await asyncio.sleep(0)
        if symbol == 'bad':
            raise ccxt.NetworkError('one request failed')
        return {'recovered': symbol}

    fetcher._recover_history_window = recover
    candidates = [(0, 0, name, MarketData(symbol=name), '1h') for name in ('bad', 'good-1', 'good-2')]
    results = asyncio.run(fetcher._run_history_recovery_jobs(candidates))
    assert set(seen) == {'bad', 'good-1', 'good-2'}
    assert results[0] is None
    assert results[1:] == [{'recovered': 'good-1'}, {'recovered': 'good-2'}]
    assert fetcher.history_recovery_stats['job_unexpected'] == 1
    assert fetcher._history_repair_state[('bad', '1h')]['next_attempt'] > time.time()


def test_recovery_loop_continues_sibling_after_one_job_network_failure(monkeypatch):
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher._running = True
    symbols = ('bad', 'good')
    fetcher.markets = {s: MarketData(symbol=s, baseline_ready=True) for s in symbols}
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    fetcher.history_recovery_loop_backoff = 5.0
    fetcher._assess_history = lambda _s, _md: {'timeframes': {'1h': {'quality': 'RECOVERING',
                                                                       'state': 'DATA_GAP',
                                                                       'missing_bars': 1}}}
    completed = []

    async def recover(symbol, _md, _timeframe):
        if symbol == 'bad':
            raise ccxt.NetworkError('mock endpoint failure')
        completed.append(symbol)
        return True

    async def end_after_one_pass(_delay):
        fetcher._running = False
        raise asyncio.CancelledError

    fetcher._recover_history_window = recover
    monkeypatch.setattr(asyncio, 'sleep', end_after_one_pass)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(fetcher._history_recovery_loop())
    assert completed == ['good']
    assert fetcher.history_recovery_stats['failed'] == 1
    assert fetcher.history_recovery_stats['job_unexpected'] == 1


def test_unexpected_recovery_child_cancellation_is_isolated_from_siblings():
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    completed = []

    async def recover(symbol, md, timeframe):
        await asyncio.sleep(0)
        if symbol == 'cancel':
            raise asyncio.CancelledError
        completed.append(symbol)
        return True

    fetcher._recover_history_window = recover
    candidates = [(0, 0, name, MarketData(symbol=name), '1h') for name in ('cancel', 'sibling')]

    results = asyncio.run(fetcher._run_history_recovery_jobs(candidates))
    assert completed == ['sibling']
    assert results == [None, True]
    assert fetcher.history_recovery_stats['job_unexpected'] == 1


def test_parent_recovery_cancellation_still_propagates():
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    started = asyncio.Event()

    async def recover(_symbol, _md, _timeframe):
        started.set()
        await asyncio.Event().wait()

    fetcher._recover_history_window = recover
    candidates = [(0, 0, 'cancel', MarketData(symbol='cancel'), '1h')]

    async def run():
        task = asyncio.create_task(fetcher._run_history_recovery_jobs(candidates))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())


def test_history_recovery_retry_budget_pauses_then_starts_a_new_bounded_cycle():
    fetcher = DataFetcher.__new__(DataFetcher)
    symbol, timeframe = 'BTC/USDT:USDT', '4h'
    now = time.time()
    state = {'attempts': DataFetcher.HISTORY_RECOVERY_MAX_ATTEMPTS, 'error': 'timeout',
             'exhausted_at': now, 'next_attempt': now + DataFetcher.HISTORY_RECOVERY_COOLDOWN_SEC}
    fetcher._history_repair_state = {(symbol, timeframe): state}
    fetcher._assess_history = lambda _s, _md, error=None: {
        'state': 'UNAVAILABLE' if state['attempts'] >= DataFetcher.HISTORY_RECOVERY_MAX_ATTEMPTS else 'RECOVERING',
        'timeframes': {timeframe: {'state': 'STALE', 'quality': 'RECOVERING', 'gaps': [], 'missing_bars': 0}},
        'error': error}
    fetcher.history_recovery_stats = {'requests': 0, 'failed': 0, 'incomplete': 0,
                                      'recovered': 0, 'job_unexpected': 0}
    fetcher.history_recovery_last_error = None
    calls = []

    async def fetch(*_args, **_kwargs):
        calls.append(True)
        return []

    fetcher._fetch_klines = fetch
    md = MarketData(symbol=symbol)
    result = asyncio.run(fetcher._recover_history_window(symbol, md, timeframe))
    assert result['state'] == 'UNAVAILABLE'
    assert not calls
    assert state['attempts'] == DataFetcher.HISTORY_RECOVERY_MAX_ATTEMPTS

    state['exhausted_at'] = time.time() - DataFetcher.HISTORY_RECOVERY_COOLDOWN_SEC - 1
    result = asyncio.run(fetcher._recover_history_window(symbol, md, timeframe))
    assert result['state'] == 'RECOVERING'
    assert calls
    assert state['cycle'] == 1
    assert state['attempts'] == 1
    assert DataFetcher._history_retry_delay(1000) == 300


def test_base_frame_ready_state_maps_to_matching_quality_state():
    fetcher = DataFetcher.__new__(DataFetcher)
    symbol = 'BTC/USDT:USDT'
    md = MarketData(symbol=symbol)
    fetcher.markets = {symbol: md}
    fetcher._history_status = {}
    fetcher._history_repair_state = {}

    fetcher.update_base_frame_quality(symbol, {'timeframe': '15m', 'state': 'READY', 'ready': True,
                                               'missing_bars': 0, 'gaps': []})
    part = fetcher._history_status[symbol]['timeframes']['15m']
    assert part['state'] == 'READY'
    assert part['quality'] == 'VALID_COMPLETE'
    # Other required timeframes have not been assessed; the whole symbol must
    # remain recovering even though its scan frame is ready.
    assert fetcher._history_status[symbol]['state'] == 'RECOVERING'
    assert fetcher._history_status[symbol]['ready'] is False


def test_load_htf_requests_enough_rows_for_closed_720_hour_and_1152_five_minute():
    fetcher = DataFetcher.__new__(DataFetcher)
    symbol = 'BTC/USDT:USDT'
    md = MarketData(symbol=symbol)
    fetcher.markets = {symbol: md}
    fetcher.futures_exchange = object()
    requests = []

    async def fetch_klines(_market, _symbol, timeframe, limit, **_kwargs):
        requests.append((timeframe, limit))
        step = TF_MS[timeframe]
        current_open = int(time.time() * 1000) // step * step
        first = current_open - (limit - 1) * step
        rows = []
        for index in range(limit):
            ts = first + index * step
            rows.append([ts, '10', '11', '9', '10', '1', ts + step - 1, '10', '1', '0.5', '5', '0'])
        return rows

    async def oi_history(*_args, **_kwargs):
        return []

    fetcher._fetch_klines = fetch_klines
    fetcher._rest_call = oi_history
    assert asyncio.run(fetcher.load_htf(symbol)) is True
    assert ('1h', 721) in requests
    assert ('5m', 1153) in requests
    assert len(md.htf_1h_30d) == 720
    assert len(md.htf_5m) == 1152


def test_crashed_background_recovery_task_is_recorded():
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher._task_failures = {}
    fetcher.history_recovery_stats = {'loop_failures': 0}
    fetcher.history_recovery_last_error = None

    async def fail():
        raise RuntimeError('unexpected loop failure')

    async def run():
        task = asyncio.create_task(fail(), name='fetcher-history-recovery')
        with pytest.raises(RuntimeError):
            await task
        fetcher._loop_task_done(task)

    asyncio.run(run())
    assert fetcher.history_recovery_stats['loop_failures'] == 1
    assert 'RuntimeError' in fetcher.history_recovery_last_error


def test_exact_rest_gap_recovery_reconciles_history_coverage_end_to_end():
    fetcher = DataFetcher.__new__(DataFetcher)
    symbol, timeframe = 'BTC/USDT:USDT', '4h'
    step = TF_MS[timeframe]
    now_ms = int(time.time() * 1000)
    last_closed = now_ms // step * step - step
    first = last_closed - 29 * step
    missing = last_closed - 10 * step

    def row(ts):
        return [ts, '10', '11', '9', '10', '3', ts + step - 1, '30', '5', '2', '20', '0']

    rows = [row(first + i * step) for i in range(30) if first + i * step != missing]
    md = MarketData(symbol=symbol, baseline_ready=True, listed_ms=first)
    md.h4 = [[int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[7]),
               float(r[10]), float(r[5])] for r in rows]
    fetcher.markets = {symbol: md}
    fetcher.universe_symbols = {symbol}
    fetcher.futures_exchange = type('Exchange', (), {
        'markets': {symbol: {'id': 'BTCUSDT', 'info': {'onboardDate': first}}},
        'market': lambda self, _symbol: self.markets[_symbol],
    })()
    fetcher._history_status = {}
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    calls = []

    async def mock_rest(_exchange, method, params, **_kwargs):
        calls.append((method, params))
        assert method == 'fapiPublicGetKlines'
        assert params['startTime'] == missing
        assert params['endTime'] == missing + step - 1
        return [row(missing)]

    fetcher._rest_call = mock_rest
    initial = fetcher.history_status(symbol)
    assert initial['timeframes'][timeframe]['state'] == 'DATA_GAP'
    recovered = asyncio.run(fetcher._recover_history_window(symbol, md, timeframe))
    assert len(calls) == 1
    assert recovered['timeframes'][timeframe]['quality'] == 'VALID_COMPLETE'
    assert recovered['timeframes'][timeframe]['missing_bars'] == 0
    assert md.history_version == 1


def test_history_status_reuses_same_revision_for_bounded_interval(monkeypatch):
    import history_coverage

    symbol = 'BTC/USDT:USDT'
    fetcher = DataFetcher.__new__(DataFetcher)
    md = MarketData(symbol=symbol, baseline_ready=True)
    fetcher.markets = {symbol: md}
    fetcher.futures_exchange = type('Exchange', (), {'markets': {symbol: {'info': {}}}})()
    fetcher._history_status = {}
    fetcher._history_status_versions = {}
    fetcher._history_repair_state = {}
    calls = 0
    original = history_coverage.coverage

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(history_coverage, 'coverage', counted)
    first = fetcher._assess_history(symbol, md)
    first_calls = calls
    second = fetcher._assess_history(symbol, md)

    assert first_calls > 0
    assert calls == first_calls
    assert second['assessed_ms'] == first['assessed_ms']


def test_daily_history_window_covers_live_consumers_without_legacy_strategy_tail():
    # Current API, structure and scenario paths consume at most the latest 370
    # daily bars. The quarantined legacy strategy tail is not a live contract.
    required, retained = DataFetcher._history_requirements('1d')
    assert required == 200
    assert retained == 500


def test_base_frame_recovery_repairs_gap_before_publishing_snapshot():
    fetcher = DataFetcher.__new__(DataFetcher)
    symbol = 'BTC/USDT:USDT'
    timeframe = CONFIG.timeframe.rest_timeframe
    step = TF_MS[timeframe]
    now_ms = int(time.time() * 1000)
    last_closed = now_ms // step * step - step
    count = 502
    first = last_closed - (count - 1) * step
    missing = last_closed - 50 * step

    def row(ts):
        return [ts, '10', '11', '9', '10', '3', ts + step - 1, '30', '5', '2', '20', '0']

    rows = [row(first + i * step) for i in range(count) if first + i * step != missing]
    frame = fetcher._klines_to_df(rows)
    md = MarketData(symbol=symbol, baseline_ready=True, listed_ms=first)
    md.futures_df = frame
    md.finalized_until['futures'] = last_closed
    fetcher.markets = {symbol: md}
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher._backfill_semaphore = asyncio.Semaphore(1)
    fetcher.futures_exchange = type('Exchange', (), {
        'markets': {symbol: {'id': 'BTCUSDT', 'info': {'onboardDate': first}}},
        'market': lambda self, _symbol: self.markets[_symbol],
    })()
    async def load(_market, _symbol):
        return frame, last_closed

    async def mock_rest(_exchange, method, params, **_kwargs):
        assert method == 'fapiPublicGetKlines'
        assert params['startTime'] == missing
        assert params['endTime'] == missing + step - 1
        return [row(missing)]

    fetcher._load_frame = load
    fetcher._rest_call = mock_rest
    assert fetcher._baseline_frame_assessment(symbol, frame)['state'] == 'DATA_GAP'
    assert asyncio.run(fetcher._recover_base_frame(symbol, md)) is True
    assert fetcher._baseline_frame_assessment(symbol, md.futures_df)['state'] == 'READY'
    assert md.history_version == 1
    assert fetcher.history_recovery_stats['recovered'] == 1


def test_universe_replacement_with_same_size_never_reuses_old_health():
    fetcher = DataFetcher.__new__(DataFetcher)
    old, new = 'OLD/USDT:USDT', 'NEW/USDT:USDT'
    fetcher.markets = {old: MarketData(symbol=old, baseline_ready=True)}
    fetcher.universe_symbols = {old}
    fetcher._history_status = {old: {'state': 'VALID_COMPLETE', 'ready': True,
                                     'timeframes': {'1h': {'quality': 'VALID_COMPLETE'}}}}
    fetcher._history_repair_state = {}
    fetcher.futures_exchange = type('Exchange', (), {'markets': {new: {'id': 'NEWUSDT'}}})()
    fetcher.flow = type('Flow', (), {'register': lambda *_: None, 'unregister': lambda *_: None})()
    fetcher.symbol_map = type('Map', (), {'set_universe': lambda *_: None})()
    fetcher.depth = type('Depth', (), {'forget': lambda *_: None})()
    fetcher.footprint = type('Footprint', (), {'disable': lambda *_: None})()
    fetcher.whales = type('Whales', (), {'forget': lambda *_: None})()
    fetcher.rush = type('Rush', (), {'forget': lambda *_: None})()
    fetcher.venue_derivs = {}
    fetcher._new_market_data = lambda symbol: MarketData(symbol=symbol)
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    added, removed = fetcher.apply_universe([new])
    state = fetcher.history_diagnostics()
    assert (added, removed) == ([new], [old])
    assert state['symbols_expected'] == 1
    assert state['symbols_assessed'] == 0
    assert state['state'] == 'RECOVERING'
    assert state['states'] == {'RECOVERING': 1}
    assert state['stale_status_entries'] == 0
    assert state['unready'][0]['symbol'] == new


def test_restart_streams_rebases_health_universe_by_symbol_identity():
    fetcher = DataFetcher.__new__(DataFetcher)
    old, new = 'OLD/USDT:USDT', 'NEW/USDT:USDT'
    fetcher.markets = {old: MarketData(symbol=old), new: MarketData(symbol=new)}
    fetcher.universe_symbols = {old}
    fetcher._history_status = {
        old: {'state': 'VALID_COMPLETE', 'ready': True, 'timeframes': {}},
        new: {'state': 'VALID_COMPLETE', 'ready': True, 'timeframes': {}},
    }
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    fetcher._binance_streams = []
    fetcher.venue_streams = {}
    fetcher._binance_plans = lambda _symbols: []
    asyncio.run(fetcher.restart_streams([new]))
    status = fetcher.history_diagnostics()
    assert new not in fetcher._history_status
    assert status['symbols_expected'] == 1
    assert status['state'] == 'RECOVERING'
    assert status['states'] == {'RECOVERING': 1}
    assert status['stale_status_entries'] == 1


def test_create_market_data_clears_previous_universe_health_cache():
    fetcher = DataFetcher.__new__(DataFetcher)
    old, new = 'OLD/USDT:USDT', 'NEW/USDT:USDT'
    fetcher._new_market_data = lambda symbol: MarketData(symbol=symbol)
    fetcher.markets = {old: MarketData(symbol=old)}
    fetcher._history_status = {old: {'state': 'VALID_COMPLETE', 'ready': True, 'timeframes': {}}}
    fetcher._history_repair_state = {(old, '1h'): {'attempts': 0}}
    fetcher.flow = type('Flow', (), {'register': lambda *_: None})()
    fetcher.futures_exchange = type('Exchange', (), {'markets': {new: {'id': 'NEWUSDT'}}})()
    fetcher.symbol_map = type('Map', (), {'set_universe': lambda *_: None})()
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    fetcher.create_market_data([new])
    status = fetcher.history_diagnostics()
    assert set(fetcher.markets) == {new}
    assert fetcher.universe_symbols == {new}
    assert not fetcher._history_status
    assert not fetcher._history_repair_state
    assert status['state'] == 'RECOVERING'


def test_reactivated_kept_symbol_must_be_reassessed_before_health_is_ready():
    old, new = 'OLD/USDT:USDT', 'NEW/USDT:USDT'
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher._new_market_data = lambda symbol: MarketData(symbol=symbol)
    fetcher.markets = {old: MarketData(symbol=old), new: MarketData(symbol=new)}
    fetcher.universe_symbols = {old}
    fetcher._history_status = {
        old: {'state': 'VALID_COMPLETE', 'ready': True, 'timeframes': {}},
        new: {'state': 'VALID_COMPLETE', 'ready': True, 'timeframes': {}},
    }
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    fetcher.flow = type('Flow', (), {'register': lambda *_: None, 'unregister': lambda *_: None})()
    fetcher.depth = type('Depth', (), {'forget': lambda *_: None})()
    fetcher.footprint = type('Footprint', (), {'disable': lambda *_: None})()
    fetcher.whales = type('Whales', (), {'forget': lambda *_: None})()
    fetcher.rush = type('Rush', (), {'forget': lambda *_: None})()
    fetcher.venue_derivs = {}
    fetcher.futures_exchange = type('Exchange', (), {'markets': {old: {'id': 'OLDUSDT'}, new: {'id': 'NEWUSDT'}}})()
    fetcher.symbol_map = type('Map', (), {'set_universe': lambda *_: None})()
    fetcher.universe_symbols = {old}
    fetcher.apply_universe([new], keep=[old])
    assert fetcher._history_status.get(new) is None
    fetcher.apply_universe([old], keep=[new])
    assert old not in fetcher._history_status
    assert fetcher.history_diagnostics()['state'] == 'RECOVERING'


def test_recovery_loop_never_schedules_kept_but_inactive_symbols(monkeypatch):
    old, active = 'OLD/USDT:USDT', 'ACTIVE/USDT:USDT'
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher._running = True
    fetcher.markets = {old: MarketData(symbol=old, baseline_ready=True),
                       active: MarketData(symbol=active, baseline_ready=True)}
    fetcher.universe_symbols = {active}
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    fetcher.history_recovery_loop_backoff = 5.0
    assessed = []

    def assess(symbol, _md):
        assessed.append(symbol)
        return {'timeframes': {}}

    async def stop(_delay):
        fetcher._running = False
        raise asyncio.CancelledError

    fetcher._assess_history = assess
    monkeypatch.setattr(asyncio, 'sleep', stop)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(fetcher._history_recovery_loop())
    assert assessed == [active]


def test_recovery_result_is_discarded_if_symbol_leaves_universe_during_rest():
    symbol, timeframe = 'BTC/USDT:USDT', '4h'
    fetcher = DataFetcher.__new__(DataFetcher)
    md = MarketData(symbol=symbol, baseline_ready=True)
    fetcher.markets = {symbol: md}
    fetcher.universe_symbols = {symbol}
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    fetcher.futures_exchange = type('Exchange', (), {'markets': {symbol: {'id': 'BTCUSDT'}}})()
    step = TF_MS[timeframe]
    now_ms = int(time.time() * 1000)
    last_closed = now_ms // step * step - step
    first = last_closed - 29 * step
    rows = [[first + i * step, '10', '11', '9', '10', '3', first + i * step + step - 1,
             '30', '5', '2', '20', '0'] for i in range(30)]

    def assess(_symbol, _md, error=None):
        return {'timeframes': {timeframe: {'state': 'DATA_GAP', 'quality': 'RECOVERING',
                                           'gaps': [], 'missing_bars': 1}}, 'error': error}

    async def fetch(*_args, **_kwargs):
        fetcher.universe_symbols.clear()
        return rows

    fetcher._assess_history = assess
    fetcher._fetch_klines = fetch
    before = list(md.h4)
    result = asyncio.run(fetcher._recover_history_window(symbol, md, timeframe))
    assert result['state'] == 'UNAVAILABLE'
    assert result['error'] == 'symbol_left_active_universe'
    assert md.h4 == before
    assert fetcher.history_recovery_stats['recovered'] == 0


def test_failed_initial_baseline_remains_unready_for_recovery():
    fetcher = DataFetcher.__new__(DataFetcher)
    md = MarketData(symbol='BTC/USDT:USDT')

    async def fail(*_args, **_kwargs):
        raise ccxt.RequestTimeout('mock timeout')

    fetcher._load_frame = fail
    loaded = asyncio.run(fetcher._load_initial_baseline(md.symbol, md))
    assert loaded is False
    assert md.baseline_attempted is True
    assert md.baseline_loading is False
    assert md.baseline_loaded is False
    assert md.baseline_ready is False
    assert md.baseline_validated is False
    assert 'RequestTimeout' in md.baseline_error


def _valid_recent_frame_15m():
    step = 900_000
    last = int(time.time() * 1000) // step * step - step
    start = last - 501 * step
    return pl.DataFrame({
        'timestamp': [start + i * step for i in range(502)],
        'open': [10.0] * 502, 'high': [11.0] * 502, 'low': [9.0] * 502,
        'close': [10.0] * 502, 'volume': [1.0] * 502,
    })


def _history_quality_fixture(**overrides):
    qualities = {'15m': 'VALID_COMPLETE', '1h': 'VALID_COMPLETE', '4h': 'VALID_COMPLETE',
                 '1d': 'VALID_COMPLETE', '1w': 'VALID_COMPLETE', '5m': 'VALID_COMPLETE'}
    qualities.update(overrides)
    return {'state': 'VALID_COMPLETE', 'ready': True,
            'timeframes': {tf: {'quality': quality, 'latest_closed_ms': 1_700_000_000_000}
                           for tf, quality in qualities.items()}}


def test_level_inputs_gate_bad_1h_and_label_derived_optional_timeframes():
    symbol = 'BTC/USDT:USDT'
    scanner = Scanner.__new__(Scanner)
    md = MarketData(symbol=symbol)
    scanner.market_data = {symbol: md}
    scanner._frame_parts = {symbol: _valid_recent_frame_15m()}
    quality = _history_quality_fixture(**{'1h': 'DATA_GAP'})
    scanner.fetcher = type('Fetcher', (), {
        'history_status': lambda _self, _symbol: quality,
        '_history_requirements': staticmethod(DataFetcher._history_requirements),
    })()
    assert not scanner._level_history_ready(symbol)

    quality = _history_quality_fixture(**{'4h': 'DATA_GAP', '1d': 'INVALID', '5m': 'RECOVERING'})
    assert scanner._level_history_ready(symbol)
    details = scanner._level_quality(symbol)
    assert details['state'] == 'VALID_PARTIAL'
    assert details['four_hour_source'] == 'derived_from_validated_1h'
    assert details['volume_profile_source'] == '1h_approximation'
    assert set(details['missing_optional_timeframes']) == {'4h', '1d', '5m'}


def test_structured_scorer_receives_no_internally_gapped_base_frame():
    fetcher = DataFetcher.__new__(DataFetcher)
    symbol = 'BTC/USDT:USDT'
    frame = _valid_recent_frame_15m()
    missing_ts = frame['timestamp'][250]
    frame = frame.filter(pl.col('timestamp') != missing_ts)
    md = MarketData(symbol=symbol, baseline_ready=True)
    md.futures_df = frame
    md.finalized_until['futures'] = int(frame['timestamp'][-1])
    fetcher.markets = {symbol: md}
    fetcher.universe_symbols = {symbol}
    fetcher._history_status = {}
    fetcher._history_repair_state = {}
    fetcher.history_recovery_stats = {'checks': 0, 'requests': 0, 'recovered': 0, 'incomplete': 0,
                                      'failed': 0, 'job_unexpected': 0, 'loop_failures': 0}
    fetcher.history_recovery_last_error = None
    fetcher._task_failures = {}
    scanner = Scanner.__new__(Scanner)
    scanner.market_data = {symbol: md}
    scanner.fetcher = fetcher
    result = asyncio.run(scanner._merge_rows())
    futures_frames = result[1]
    assert symbol not in futures_frames
    assert md.baseline_validated is False
    diagnostics = fetcher.history_diagnostics()
    assert diagnostics['ok'] is False
    assert diagnostics['states'] == {'RECOVERING': 1}


def test_corrupted_daily_history_is_omitted_from_scenario_context():
    symbol = 'BTC/USDT:USDT'
    scanner = Scanner.__new__(Scanner)
    md = MarketData(symbol=symbol)
    scanner.market_data = {symbol: md}
    scanner._scenario_history_ready = lambda _symbol: True
    step_day = 86_400_000
    last_day = int(time.time() * 1000) // step_day * step_day - step_day
    daily = [[last_day - i * step_day, 10, 11, 9, 10, 100] for i in range(20)]
    daily.pop(9)  # an internal missing day makes the supplied daily context unusable
    md.htf_1d = daily
    md.d1 = []
    md.htf_1h_30d = []
    context = scanner._scenario_context_inputs(symbol)
    assert context['ready'] is True
    assert context['daily'] is None
    assert context['hourly_30d'] is None
    assert context['state'] == 'VALID_PARTIAL'
    assert set(context['missing_optional_timeframes']) == {'1d', '30d_1h'}


def test_scenario_is_blocked_when_required_hourly_history_is_invalid():
    scanner = Scanner.__new__(Scanner)
    symbol = 'BTC/USDT:USDT'
    scanner.market_data = {symbol: MarketData(symbol=symbol)}
    scanner.fetcher = type('Fetcher', (), {
        'history_status': lambda _self, _symbol: {'timeframes': {'1h': {'quality': 'RECOVERING'}}}
    })()
    assert scanner._scenario_history_ready(symbol) is False


def test_scenario_result_is_discarded_if_history_changes_during_worker(monkeypatch):
    symbol = 'BTC/USDT:USDT'
    scanner = Scanner.__new__(Scanner)
    md = MarketData(symbol=symbol)
    scanner.market_data = {symbol: md}
    scanner._scenario_history_ready = lambda _symbol: True

    async def mutate_during_worker(func, *args, **kwargs):
        md.history_version += 1
        return {'scenario': 'built_from_old_snapshot'}

    monkeypatch.setattr(asyncio, 'to_thread', mutate_during_worker)
    result = asyncio.run(scanner._build_scenario_if_history_stable(symbol, (), None, 0))
    assert result is None


def test_scenario_builder_forwards_symbol_without_binding_guard_twice(monkeypatch):
    symbol = 'BTC/USDT:USDT'
    scanner = Scanner.__new__(Scanner)
    md = MarketData(symbol=symbol)
    scanner.market_data = {symbol: md}
    scanner._scenario_history_ready = lambda _symbol: True
    seen = {}

    async def run_worker(func, *args, **kwargs):
        seen.update(kwargs)
        return {'scenario': 'built'}

    monkeypatch.setattr(asyncio, 'to_thread', run_worker)
    result = asyncio.run(scanner._build_scenario_if_history_stable(
        symbol, (), None, 0, symbol=symbol))

    assert result == {'scenario': 'built'}
    assert seen['symbol'] == symbol


def test_open_interest_uses_exchange_timestamp_and_rejects_invalid_values(monkeypatch):
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher._ccxt_to_binance_symbol = lambda symbol: 'BTCUSDT'
    fetcher.futures_exchange = object()
    fetcher.quality_state = {}
    fetcher.oi_last_updated = {}
    event_ms = int(time.time() * 1000) - 1000
    response = {'openInterest': '12.5', 'time': event_ms}

    async def rest(*args, **kwargs):
        return response

    fetcher._rest_call = rest
    value, measured_ms = asyncio.run(fetcher.fetch_open_interest('BTC/USDT:USDT'))
    assert (value, measured_ms) == (12.5, event_ms)
    assert fetcher.oi_last_updated['BTC/USDT:USDT'] == event_ms / 1000
    assert fetcher.oi_received_at['BTC/USDT:USDT'] >= event_ms / 1000
    assert fetcher.quality_state[('oi', 'BTC/USDT:USDT')].fetched_at == event_ms / 1000

    for invalid in ({'openInterest': '0', 'time': event_ms + 1},
                    {'openInterest': '-1', 'time': event_ms + 2},
                    {'openInterest': 'nan', 'time': event_ms + 3},
                    {'openInterest': '12', 'time': None}):
        response.update(invalid)
        assert asyncio.run(fetcher.fetch_open_interest('BTC/USDT:USDT')) is None
        state = fetcher.quality_state[('oi', 'BTC/USDT:USDT')]
        assert state.state is QualityState.INVALID
        assert state.fetched_at == event_ms / 1000


def test_cross_venue_gross_activity_survives_zero_net_flow():
    store = FlowStore(capacity=2)
    store.register(['BTC/USDT:USDT'])
    store.trade('binance', 'BTC/USDT:USDT', 1_000_000, 50, 1, 1_000_000)
    store.trade('binance', 'BTC/USDT:USDT', 1_000_000, 50, -1, 1_000_000)
    row = store.snapshot(now_sec=1_000)['BTC/USDT:USDT']
    assert row['net_flow_5m'] == 0
    assert row['gross_flow_5m'] == 100
    assert row['venues_flow_active'] == 1
    assert row['net_venues_active'] == 0
    assert row['top_gross_venue'] == 'binance'
    assert row['top_gross_venue_share'] == 1


def test_cross_venue_aggregate_quality_is_separate_from_legacy_binance_gate():
    store = FlowStore(capacity=2)
    store.register(['BTC/USDT:USDT'])
    for sec in range(600, 901, 30):
        store.trade('binance', 'BTC/USDT:USDT', sec * 1000, 10, 1, sec * 1000)
    quality = store.quality('BTC/USDT:USDT', now_sec=900, window_sec=300)
    assert quality['ok'] is True  # legacy minimum gate remains API-compatible
    assert quality['binance_ok'] is True
    assert quality['aggregate_ok'] is False
    assert 'binance' in quality['configured_venues']
    assert quality['venues'] == ['binance']
    assert quality['coverage'] < 1

    from webui import context_parts
    assert 'неполное покрытие межбиржевого потока' in context_parts({
        'flow_aggregate_quality_ok': 0.0,
    })


def test_rest_minute_seed_stays_out_of_event_flow_ring():
    store = FlowStore(capacity=2)
    store.register(['BTC/USDT:USDT'])
    store.seed_minute('binance', 'BTC/USDT:USDT', 1_000_000, 75, 25, 8)
    metrics = store.snapshot(now_sec=1_000)['BTC/USDT:USDT']
    assert metrics['cvd_5m'] == 0
    assert metrics['venues_flow_active'] == 0
    assert store.venues['binance'].messages == 0
    assert store.seed_observations[('binance', 'BTC/USDT:USDT')][0] == (
        1_000_000, 75.0, 25.0, 8, 'rest_ohlcv_aggregate')


def test_liquidation_attribution_can_be_limited_to_matching_venue():
    store = FlowStore(capacity=2)
    store.register(['BTC/USDT:USDT'])
    store.liquidation('binance', 'BTC/USDT:USDT', 1_000_000, 100, -1, 1_000_000)
    store.liquidation('bybit', 'BTC/USDT:USDT', 1_000_000, 10, -1, 1_000_000)
    assert store.symbol_range('BTC/USDT:USDT', LIQ_SHORT, 999, 1001, 1000,
                              venues=('binance',)) == 100
    assert store.symbol_range('BTC/USDT:USDT', LIQ_SHORT, 999, 1001, 1000,
                              venues=('bybit',)) == 10


def test_other_venue_liquidations_do_not_suppress_sweep():
    class Whales:
        def __init__(self):
            self.added = []

        def thresholds(self, symbol):
            return 1, 1

        def add(self, sweep):
            self.added.append(sweep)

    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher.flow = FlowStore(capacity=2)
    fetcher.flow.register(['BTC/USDT:USDT'])
    fetcher.flow.liquidation('binance', 'BTC/USDT:USDT', 1_000_000, 100, -1, 1_000_000)
    fetcher.whales = Whales()
    sweep = Sweep('bybit', 'BTC/USDT:USDT', 1_000_000, 1_000_000, 1, 100, 100, 100, 1, 1)
    fetcher._on_sweep(sweep)
    assert fetcher.whales.added == [sweep]


def test_binance_liquidation_uses_filled_executed_quantity():
    event = {'X': 'FILLED', 'T': 1_700_000_000_000, 'ap': '100', 'z': '2', 'q': '20', 'S': 'SELL'}
    assert normalize_binance_liquidation(event) == (1_700_000_000_000, 100.0, 200.0, 1)
    assert normalize_binance_liquidation({**event, 'X': 'NEW'}) is None
    assert normalize_binance_liquidation({k: v for k, v in event.items() if k != 'X'}) is None
    assert normalize_binance_liquidation({**event, 'z': '0'}) is None


def test_rest_book_validation_rejects_bad_structure_values_and_crossed_book():
    valid_bids, valid_asks = [['100', '2']], [['101', '3']]
    assert ExternalData._valid_snapshot(valid_bids, valid_asks)
    assert not ExternalData._valid_snapshot([], valid_asks)
    assert not ExternalData._valid_snapshot([['nan', '1']], valid_asks)
    assert not ExternalData._valid_snapshot([['100', '0']], valid_asks)
    assert not ExternalData._valid_snapshot([['102', '1']], valid_asks)
    assert ExternalData._bybit_book({'retCode': 10001, 'result': {'b': valid_bids, 'a': valid_asks}}) is None
    assert ExternalData._okx_book({'code': '51000', 'data': [{'bids': valid_bids, 'asks': valid_asks}]}) is None
    assert ExternalData._bybit_book({'retCode': 0, 'result': {'b': valid_bids, 'a': valid_asks}})
    assert ExternalData._okx_book({'code': '0', 'data': [{'bids': valid_bids, 'asks': valid_asks}]})


def test_rest_book_status_separates_stages_and_expires_freshness():
    from data_quality import quality
    import extdata

    ext = ExternalData.__new__(ExternalData)
    ext.book_status = {
        ('BTC/USDT:USDT', 'okx'): {'transport_success': True, 'api_success': True,
                                   'valid_market_data': True, 'received_at': 100.0},
        ('ETH/USDT:USDT', 'bybit'): {'transport_success': True, 'api_success': False,
                                     'valid_market_data': False, 'received_at': 100.0},
    }
    view = ext.rest_book_status(now=160.0)
    assert view[('BTC/USDT:USDT', 'okx')]['fresh'] is True  # normal 60s polling interval + margin
    assert view[('BTC/USDT:USDT', 'okx')]['age_sec'] == 60
    view = ext.rest_book_status(now=176.0)
    assert view[('BTC/USDT:USDT', 'okx')]['fresh'] is False
    assert view[('BTC/USDT:USDT', 'okx')]['age_sec'] == 76
    assert view[('ETH/USDT:USDT', 'bybit')]['fresh'] is False
    assert quality(160.0, 100.0, extdata.REST_BOOK_FRESH_TTL_SEC,
                   extdata.REST_BOOK_MAX_AGE_SEC, 'cross_venue_books').usable_for_entry
    assert not quality(176.0, 100.0, extdata.REST_BOOK_FRESH_TTL_SEC,
                       extdata.REST_BOOK_MAX_AGE_SEC, 'cross_venue_books').usable_for_entry


def test_rest_book_failure_isolated_between_okx_and_bybit(monkeypatch):
    from types import SimpleNamespace
    import extdata

    key = 'BTC/USDT:USDT'
    markets = {
        'okx': SimpleNamespace(venue='okx', native='BTC-USDT-SWAP'),
        'bybit': SimpleNamespace(venue='bybit', native='BTCUSDT'),
    }
    external = ExternalData.__new__(ExternalData)
    external.fetcher = SimpleNamespace(
        depth=SimpleNamespace(active=lambda: [key]),
        symbol_map=SimpleNamespace(by_key={key: markets}),
    )
    external.book_status = {}
    external.quality_state = {}
    external.coin = {}

    async def fetch(url):
        if 'okx.com' in url:
            raise OSError('test transport failure')
        return {'retCode': 0, 'result': {'b': [['99', '2']], 'a': [['101', '3']]}}

    async def no_sleep(_):
        return None

    external._json = fetch
    monkeypatch.setattr(extdata.asyncio, 'sleep', no_sleep)
    checks = iter((True, False))
    asyncio.run(external.books_loop(lambda: next(checks)))

    assert external.book_status[(key, 'okx')]['transport_success'] is False
    assert external.book_status[(key, 'okx')]['error'] == 'OSError'
    assert external.book_status[(key, 'bybit')]['valid_market_data'] is True
    assert external.book_status[(key, 'bybit')]['fresh'] is True
    assert 'bybit_book_imb' in external.coin[key]


def test_missing_websocket_connection_information_is_unknown():
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher.flow = FlowStore(venues=['bybit'])
    fetcher.venue_streams = {'bybit': type('Stream', (), {'bytes': 0})()}
    fetcher._binance_streams = []
    fetcher._depth_streams = []
    assert fetcher.venue_status()['bybit']['health_state'] == 'UNKNOWN'


def test_configured_websocket_with_zero_connections_is_disconnected():
    fetcher = DataFetcher.__new__(DataFetcher)
    fetcher.flow = FlowStore(venues=['bybit'])
    fetcher.venue_streams = {'bybit': type('Stream', (), {'connected': 0, 'bytes': 0})()}
    fetcher._binance_streams = []
    fetcher._depth_streams = []
    status = fetcher.venue_status()['bybit']
    assert status['connected'] == 0
    assert status['health_state'] == 'DISCONNECTED'

    fetcher.flow = FlowStore(venues=['binance'])
    fetcher.venue_streams = {}
    fetcher._binance_streams = [type('Stream', (), {'connected': 0, 'bytes': 0})(),
                                type('Stream', (), {'connected': 0, 'bytes': 0})()]
    status = fetcher.venue_status()['binance']
    assert status['connected'] == 0
    assert status['health_state'] == 'DISCONNECTED'


def test_debug_log_filter_redacts_credentials():
    import logging
    from main import SecretRedactionFilter

    record = logging.LogRecord(
        'test', logging.DEBUG, __file__, 1,
        'request failed BINGX_API_KEY=%s signed=https://api.test/?signature=not-a-real-signature '
        'url=https://api.telegram.org/bot123456:Abcdefghijklmnopqrstuvwxyz0123456789/sendMessage',
        ('not-a-real-secret',), None,
    )
    assert SecretRedactionFilter().filter(record)
    message = record.getMessage()
    assert 'not-a-real-secret' not in message
    assert 'not-a-real-signature' not in message
    assert '123456:Abcdef' not in message
    assert message.count('[REDACTED]') == 3


def test_data_only_mode_disables_orders_strategies_and_notifications(monkeypatch):
    from config import CONFIG
    from main import apply_data_only_mode

    original = (CONFIG.executor, CONFIG.strategies, CONFIG.notify, CONFIG.briefing)
    monkeypatch.setenv('EDGEHUNTER_DATA_ONLY', '1')
    try:
        assert apply_data_only_mode() is True
        assert CONFIG.executor.enabled is False
        assert CONFIG.strategies.enabled == ()
        assert CONFIG.notify.enabled is False
        assert CONFIG.briefing.enabled is False
    finally:
        for name, value in zip(('executor', 'strategies', 'notify', 'briefing'), original):
            object.__setattr__(CONFIG, name, value)


def test_websocket_diagnostics_separate_transport_parse_and_handler_counts():
    from venues import VenueStream

    class DiagnosticStream:
        _on_text = VenueStream._on_text
        diagnostics = VenueStream.diagnostics

        def __init__(self):
            self.name = 'fixture-stream'
            self.messages = self.bytes = self.errors = self.decode_errors = 0
            self.handler_completed = self.connection_attempts = self.connection_opens = self.reconnects = 0
            self.connected = 1
            self.last_receive_ms = self.last_handler_ms = 0.0
            self._conn_subs = {0: ['sub']}
            self._dynamic_wanted = set()

        def handle(self, payload, recv_ms):
            self.last_payload = payload

    stream = DiagnosticStream()
    stream._on_text(b'{')
    stream._on_text(b'{"event":"trade"}')
    result = stream.diagnostics()
    assert result['frames_received'] == 2
    assert result['decode_errors'] == 1
    assert result['handler_completed'] == 1
    assert result['subscriptions'] == 1
    assert result['last_receive_ms'] is not None


def test_unobserved_venue_mark_is_none_not_zero():
    from fetcher import VenueDeriv

    state = VenueDeriv()
    assert state.mark is None


def test_swing_pierce_level_timestamp_is_extreme_candle_time():
    from zones import swings

    base = 1_800_000_000_000
    candles = [
        [base + 0 * 60_000, 8.5, 9.0, 8.0, 8.5],
        [base + 1 * 60_000, 9.0, 10.0, 8.5, 9.2],
        [base + 2 * 60_000, 9.2, 9.5, 8.7, 9.0],
        [base + 3 * 60_000, 9.0, 11.0, 8.8, 9.4],
        [base + 4 * 60_000, 9.4, 10.5, 8.9, 9.2],
        [base + 5 * 60_000, 9.2, 9.5, 8.7, 9.0],
    ]

    found = [x for x in swings(candles, width=1, kind='swing_15m', tf='15m')
             if x.label == '15m high (pierce)' and x.price == 11.0]
    assert len(found) == 1
    assert found[0].ts == base + 3 * 60_000


def test_zone_center_uses_the_same_deduplicated_event_weights_as_strength(monkeypatch):
    import pierce
    from zones import RawLevel, merge

    monkeypatch.setattr(pierce, 'model', lambda: None)
    levels = [
        RawLevel(10.0, 'swing_15m', '15m swing', +1),
        RawLevel(10.0, 'swing_1h', '1h swing', +1),  # same price event, a second label
        RawLevel(10.2, 'swing_15m', '15m swing B', +1),
    ]

    zones = merge(levels, atr=1.0)
    assert len(zones) == 1
    assert zones[0].strength == pytest.approx(2.0)
    assert zones[0].price == pytest.approx(10.1)


def test_zone_merge_preserves_source_timeframes_through_public_view(monkeypatch):
    import pierce
    from zones import RawLevel, merge

    monkeypatch.setattr(pierce, 'model', lambda: None)
    levels = [
        RawLevel(10.0, 'swing_1h', '1h high', +1, ts=1_000),
        RawLevel(10.1, 'ob_4h', '4h bullish OB', -1, ts=2_000),
    ]

    zone, = merge(levels, atr=1.0)
    view = zone.as_dict()
    assert {'swing_1h', 'ob_4h'} <= set(view['kinds'])
    assert '1h high' in view['label'] and '4h bullish OB' in view['label']
    assert {part[0] for part in zone.parts} == {'swing_1h', 'ob_4h'}


def test_tier0_nan_metrics_remain_unknown_and_cannot_trigger_flags():
    import polars as pl
    from indicators import TIER0_COLUMNS
    from scorer import PhaseScorer, _tier0_frame

    values = {name: [None] for name in TIER0_COLUMNS}
    for name in ('liq_long_5m', 'liq_short_5m', 'venues_active', 'top_venue_share',
                 'top_venue_net', 'cluster'):
        values[name] = [float('nan')]
    frame = pl.DataFrame(values, schema={name: pl.Float64 for name in TIER0_COLUMNS})
    flagged = PhaseScorer().flag_tier_0_anomaly(frame)
    assert flagged['is_tier_0_anomaly'][0] is False
    assert flagged['t0_liq'][0] is False
    assert flagged['t0_venue'][0] is False
    assert flagged['t0_cluster'][0] is False
    assert flagged['venues_active'][0] is None
    assert _tier0_frame({'BTC/USDT:USDT': {'venues_active': float('nan')}})['venues_active'][0] is None


def test_sql_identifier_requires_allowlist():
    assert identifier("logic_version", {"logic_version"}) == "logic_version"


@pytest.mark.parametrize("value", ["x; DROP TABLE signals", "1column", "name with spaces"])
def test_sql_identifier_rejects_injection_shapes(value):
    with pytest.raises(ValueError):
        identifier(value, {value})


def test_sql_identifier_rejects_unknown_names():
    with pytest.raises(ValueError):
        identifier("secret", {"public"})


def test_url_helper_rejects_non_https():
    with pytest.raises(ValueError):
        safe_urlopen("http://example.test", timeout=1)


@pytest.mark.parametrize(
    "direction,levels,valid",
    [
        (1, {'entry': 100, 'sl': 95, 'tp1': 105, 'tp2': 110, 'tp3': 115}, True),
        (-1, {'entry': 100, 'sl': 105, 'tp1': 95, 'tp2': 90, 'tp3': 85}, True),
        (1, {'entry': 100, 'sl': 95, 'tp1': 105, 'tp2': 103, 'tp3': 115}, False),
        (-1, {'entry': 100, 'sl': 105, 'tp1': 95, 'tp2': 97, 'tp3': 85}, False),
        (1, {'entry': 100, 'sl': 95, 'tp1': None, 'tp2': None, 'tp3': None}, True),
    ],
)
def test_card_geometry_is_side_aware(direction, levels, valid):
    assert validate_card_levels(levels, direction) is valid


def test_runtime_feature_contract_is_persisted():
    assert {'agg_oi_change_1h', 'oi_venues', 'iceberg_reason', 'feature_schema_version'} <= set(EXTRA_COLUMNS)


def test_depth_pruning_bounds_changed_levels():
    book = BookState()
    book.bids = {90.0: 1.0, 99.0: 1.0, 100.0: 1.0}
    book.asks = {100.0: 1.0, 101.0: 1.0, 110.0: 1.0}
    DepthBook._prune(book, 100.0)
    assert set(book.bids) == {99.0, 100.0}
    assert set(book.asks) == {100.0, 101.0}


def test_okx_taker_rows_normalize_timestamp_and_reject_bad_rows():
    rows = okx_taker_rows({'code': '0', 'data': [['1700000000', '2.5', '4'], ['bad', 1, 2], ['x']]})
    assert rows == [(1700000000000, 2.5, 4.0)]
    assert okx_completed_bucket(1_700_000_000_000, 1_700_000_600_000) == 1_700_000_000_000
    assert okx_completed_bucket(1_700_000_600_000, 1_700_000_600_000) == 1_700_000_300_000
    assert okx_completed_bucket(1_700_000_900_000, 1_700_000_600_000) is None


@pytest.mark.parametrize(
    "direction,levels,candle",
    [
        (1, {'entry': 100, 'sl': 95, 'tp1': 105, 'tp2': 110, 'tp3': 115}, [0, 100, 106, 94, 100, 0]),
        (-1, {'entry': 100, 'sl': 105, 'tp1': 95, 'tp2': 90, 'tp3': 85}, [0, 100, 106, 94, 100, 0]),
    ],
)
def test_replay_resolves_intrabar_stop_before_target(direction, levels, candle):
    result = simulate(levels, direction, [candle], use_fill=False)
    assert result['outcome'] == 'SL'


def test_executor_credentials_fail_closed_without_environment(monkeypatch):
    monkeypatch.delenv('BINGX_API_KEY', raising=False)
    monkeypatch.delenv('BINGX_API_SECRET', raising=False)
    assert credentials() == ('', '')


def test_executor_requires_explicit_vst_gate_and_rejects_live_host(monkeypatch):
    class FakeExchange:
        def __init__(self, origin):
            self.urls = {'api': {'swap': origin}}
            self.options = {'sandboxMode': True}

        @staticmethod
        def implode_hostname(url):
            return url

    monkeypatch.delenv('EDGEHUNTER_BINGX_DEMO_EXECUTION', raising=False)
    monkeypatch.delenv('EDGEHUNTER_BINGX_KILL_SWITCH', raising=False)
    DemoExecutor._assert_vst_endpoint(FakeExchange('https://open-api-vst.bingx.com'))
    with pytest.raises(RuntimeError, match='gate is closed'):
        DemoExecutor._assert_vst_endpoint(FakeExchange('https://open-api-vst.bingx.com'), require_gate=True)

    monkeypatch.setenv('EDGEHUNTER_BINGX_DEMO_EXECUTION', '1')
    monkeypatch.setenv('EDGEHUNTER_BINGX_KILL_SWITCH', '0')
    with pytest.raises(RuntimeError, match='only open-api-vst'):
        DemoExecutor._assert_vst_endpoint(FakeExchange('https://open-api.bingx.com'), require_gate=True)
    with pytest.raises(RuntimeError, match='sandbox mode'):
        ex = FakeExchange('https://open-api-vst.bingx.com')
        ex.options['sandboxMode'] = False
        DemoExecutor._assert_vst_endpoint(ex, require_gate=True)


def test_executor_write_checks_vst_balance_immediately_before_order(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv('EDGEHUNTER_BINGX_DEMO_EXECUTION', '1')
    monkeypatch.setenv('EDGEHUNTER_BINGX_KILL_SWITCH', '0')
    ex = SimpleNamespace(urls={'api': {'swap': 'https://open-api-vst.bingx.com'}},
                         options={'sandboxMode': True}, implode_hostname=lambda url: url,
                         fetch_balance=None, create_order=None)
    calls = []

    async def fetch_balance():
        calls.append('balance')
        return {'total': {'VST': 1000.0}}

    async def create_order(*args, **kwargs):
        calls.append(('order', args, kwargs))
        return {'status': 'accepted'}

    ex.fetch_balance = fetch_balance
    ex.create_order = create_order
    executor = DemoExecutor(':memory:')
    order = asyncio.run(executor._demo_create_order(ex, 'BTC/USDT:USDT', 'market', 'buy', 0.0001))
    assert order['status'] == 'accepted'
    assert calls[0] == 'balance'
    assert calls[1][0] == 'order'

    calls.clear()

    async def empty_balance():
        calls.append('balance')
        return {'total': {}}

    ex.fetch_balance = empty_balance
    with pytest.raises(RuntimeError, match='balance is unavailable'):
        asyncio.run(executor._demo_create_order(ex, 'BTC/USDT:USDT', 'market', 'buy', 0.0001))
    assert calls == ['balance']


def test_executor_entry_intent_is_idempotent(tmp_path):
    demo = DemoExecutor(str(tmp_path / 'demo.sqlite'))
    assert demo._claim_execution('card-1', 'ENTRY') is True
    assert demo._claim_execution('card-1', 'ENTRY') is False
    assert demo._claim_execution('card-1', 'STOP') is True
    assert demo._protection_state({'direction': 1, 'entry_fill': 100, 'sl': 95, 'no_stop': 0}) == 'PROTECTED'
    assert demo._protection_state({'direction': -1, 'entry_fill': 100, 'sl': 95, 'no_stop': 0}) == 'INVALID_GEOMETRY'
    assert demo._protection_state({'strategy': 'connors', 'no_stop': 1}) == 'NO_STOP_ALLOWED'


def _market_signal(direction=-1, group_key='OI BUILD SHORT'):
    return TrackedSignal(
        symbol='TEST/USDT:USDT', group_key=group_key, direction=direction, mode='oi_build',
        created=0.0, price_at_signal=100.0, sig={}, last_price=100.0,
    )


@pytest.mark.parametrize(
    'btc_1d,mkt_1d,expected',
    [
        (0.01, 0.02, True),    # both positive: veto the short
        (0.01, 0.0, False),    # boundary: neutral is allowed
        (0.0, 0.02, False),    # boundary: neutral is allowed
        (-0.01, -0.02, False), # falling market: short is allowed by this veto
        (0.01, -0.02, False),  # mixed regime: no joint-bull veto
    ],
)
def test_oi_short_market_up_is_a_blocking_veto(btc_1d, mkt_1d, expected):
    book = SignalBook()
    book.market_state_of = lambda: {'btc_1d': btc_1d, 'mkt_1d': mkt_1d}
    assert book._market_up_veto(_market_signal()) is expected


@pytest.mark.parametrize(
    'btc_1d,mkt_1d,expected',
    [
        (-0.01, -0.02, True),  # both negative: veto the long
        (-0.01, 0.0, False),   # boundary: neutral is allowed
        (0.01, 0.02, False),   # rising market: long is allowed by this veto
        (-0.01, 0.02, False),  # mixed regime: no joint-bear veto
    ],
)
def test_market_down_remains_the_long_side_mirror(btc_1d, mkt_1d, expected):
    book = SignalBook()
    book.market_state_of = lambda: {'btc_1d': btc_1d, 'mkt_1d': mkt_1d}
    assert book._market_down(_market_signal(direction=1, group_key='OI BUILD LONG')) is expected


def _stored_trade(demo):
    trade = {
        'card_id': 'TEST|OI BUILD SHORT|c1', 'symbol': 'BTC/USDT:USDT', 'setup': 'OI BUILD SHORT',
        'strategy': 'oi_build', 'direction': -1, 'opened_ms': 1, 'entry_plan': 100.0,
        'entry_fill': 100.0, 'qty': 1.0, 'sl': 105.0, 'tp1': 95.0, 'tp2': 90.0, 'tp3': 85.0,
    }
    trade['id'] = demo._insert(trade)
    return trade


@pytest.mark.parametrize(
    'breach,close_reason,field,value',
    [
        ('wrong_stop_side', 'INVALID_FILL_GEOMETRY', 'geometry_error', 'wrong_stop_side'),
        ('low_rr: actual TP1 R:R 0.32 < 1', 'SLIPPAGE_ABORT', 'risk_gate_reason', 'low_rr'),
    ],
)
def test_post_fill_contract_breach_is_flattened_with_reason(tmp_path, breach, close_reason, field, value):
    demo = DemoExecutor(str(tmp_path / 'post_fill.sqlite'))
    trade = _stored_trade(demo)
    closed = []

    async def close_stub(item, reason, journal_r, passive=False):
        closed.append((reason, journal_r))

    demo._close = close_stub
    demo.alert = lambda message: None
    asyncio.run(demo._close_invalid_fill(trade, breach))
    assert closed == [(close_reason, None)]
    assert trade[field] == value


def test_virtual_tp_parts_are_bounded_and_deterministic():
    class Exchange:
        @staticmethod
        def amount_to_precision(symbol, amount):
            return f'{amount:.8f}'

    assert DemoExecutor.tp_parts(Exchange(), 'BTC', 9, trail=False, no_tp=False) == [(1, 3.0), (2, 3.0), (3, 3.0)]
    assert DemoExecutor.tp_parts(Exchange(), 'BTC', 9, trail=True, no_tp=False) == [(1, 4.5)]
    assert DemoExecutor.tp_parts(Exchange(), 'BTC', 9, trail=False, no_tp=True) == []


def test_shrinkage_gate_is_explicit_and_conservative_for_small_samples():
    assert 0.5 < shrinkage_upper(1, 1) < 1.0
    assert shrinkage_upper(1, 1) >= shrinkage_upper(0, 1)
    assert wilson_upper(1, 1) > 0.9


def test_minute_backfill_counts_only_after_gap_is_verified(monkeypatch):
    class MD:
        minute_klines = [[0, 1, 1, 1, 1, 1, 1, 1],
                         [60_000, 1, 1, 1, 1, 1, 1, 1],
                         [180_000, 1, 1, 1, 1, 1, 1, 1]]
        minute_closed_until = 180_000

        def seed_minutes(self, market, rows, now_ms):
            self.minute_klines.extend(rows)
            self.minute_klines.sort(key=lambda row: row[0])

    fetcher = object.__new__(DataFetcher)
    fetcher.backfill_stats = {'requested': 0, 'attempted': 0, 'applied': 0, 'verified': 0,
                              'failed': 0, 'deferred': 0}

    async def rows(*args):
        return [[120_000, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0]]

    monkeypatch.setattr(fetcher, 'fetch_minute_klines', rows)
    md = MD()
    import asyncio
    assert asyncio.run(fetcher.patch_minute_holes('BTC', md, 200_000)) == 0
    assert fetcher.backfill_stats['applied'] == 1
    assert fetcher.backfill_stats['verified'] == 1


def test_briefing_quant_gate_rejects_non_positive_net_ev():
    rejected = scenario_gate(0.5, reward=1.0, risk=1.0, cost=0.01)
    accepted = scenario_gate(0.7, reward=2.0, risk=1.0, cost=0.01)
    assert rejected['trade_gate'] is False
    assert rejected['ev_net'] < 0
    assert accepted['trade_gate'] is True
    assert accepted['p_base'] >= accepted['p_breakeven']


def test_pump_monitor_is_explicitly_informational():
    assert pumps.STATS['pump']['verdict'].startswith('НЕ подтверждено')
    assert pumps.PUMP == 0.15 and pumps.WIN == 6


def test_iceberg_is_unknown_without_fresh_l2_coverage():
    detector = IcebergDetector()
    assert detector.features('BTC', now_ms=1000)['iceberg_net_5m'] is None
    detector.on_book('BTC', [[100, 2]], [[101, 2]], 1000)
    assert detector.features('BTC', now_ms=2000)['iceberg_reason'] == 'ok'
    assert detector.features('BTC', now_ms=1000 + 61_000)['iceberg_reason'] == 'stale_l2_coverage'
    detector.invalidate('BTC')
    assert detector.features('BTC', now_ms=2000)['iceberg_reason'] == 'sequence_resync_or_no_book'


def test_depth_records_sequence_gaps_and_buffer_drops():
    from depth import DepthBook
    book = DepthBook()
    book.start('BTC')
    for i in range(2001):
        book.on_diff('BTC', {'u': i + 1, 'U': i + 1, 'pu': 0, 'E': i})
    assert book.books['BTC'].buffer_drops == 1000
    book.books['BTC'].synced = True
    book.books['BTC'].last_u = 10
    book.on_diff('BTC', {'u': 12, 'U': 12, 'pu': 11, 'E': 1})
    assert book.books['BTC'].sequence_gaps == 1
    diag = book.diagnostics()
    assert diag['sequence_gaps'] == 1 and diag['buffer_drops'] == 1000


def _flat_candle(ts, high=102.0, low=98.0, close=100.0):
    return [ts, close, high, low, close, 100.0, 50.0, 1.0]


def test_balanced_ranges_require_contiguous_ordered_timestamp_runs():
    from zones import balanced_ranges

    candles = [_flat_candle(i * 3_600_000) for i in range(12)]
    candles[0] = _flat_candle(0, high=100, low=95, close=98)
    candles[2] = _flat_candle(2 * 3_600_000, high=115, low=110, close=112)
    candles[3] = _flat_candle(3 * 3_600_000, high=116, low=112, close=113)
    candles[5] = _flat_candle(5 * 3_600_000, high=105, low=100, close=102)

    # Continuous 3-candle FVGs overlap and remain unmitigated.
    assert any(level.kind == 'bpr_1h' for level in balanced_ranges(candles, '1h'))
    four_hour = [row.copy() for row in candles]
    for i, row in enumerate(four_hour):
        row[0] = i * 4 * 3_600_000
    assert any(level.kind == 'bpr_4h' for level in balanced_ranges(four_hour, '4h'))

    # The first pattern crosses a missing interval; the old code still paired
    # it with the bearish pattern later in the array.
    with_gap = [row.copy() for row in candles]
    for row in with_gap[3:]:
        row[0] += 3_600_000
    assert balanced_ranges(with_gap, '1h') == []

    duplicated = [row.copy() for row in candles]
    duplicated[6][0] = duplicated[5][0]
    assert balanced_ranges(duplicated, '1h') == []
    unordered = [row.copy() for row in candles]
    unordered[6], unordered[7] = unordered[7], unordered[6]
    assert balanced_ranges(unordered, '1h') == []
    missing_timestamp = [row.copy() for row in candles]
    missing_timestamp[4][0] = None
    assert balanced_ranges(missing_timestamp, '1h') == []


def test_estimated_liquidations_reset_oi_baseline_after_gap(monkeypatch):
    import zones

    monkeypatch.setattr(zones, 'leverage_mix', lambda: [(10.0, 1.0)])
    monkeypatch.setattr(zones, 'maintenance_of', lambda _symbol: (0.0, None))
    candles = [_flat_candle(i * 3_600_000) for i in range(12)]
    # OI timestamps are the period end; hour 2 is missing. A 390-unit jump
    # between hours 1 and 3 must not be attributed to hour 3's price.
    oi = [(i * 3_600_000 + 3_600_000, v) for i, v in
          ((0, 100), (1, 110), (3, 500), (4, 501), (5, 502), (6, 503),
           (7, 504), (8, 505), (9, 506), (10, 507), (11, 508))]
    levels = zones.estimated_liquidations(candles, oi, atr=10.0, symbol='BTC/USDT:USDT')
    assert levels
    assert all(level.kind == 'liq_est' for level in levels)
    # The 8-unit contiguous increase after hour 3 is applied to the two model
    # sides; the 390-unit multi-hour jump and pre-gap cluster are discarded.
    assert sum(level.size for level in levels) <= 16.02 * candles[-1][4]


def test_prior_period_levels_require_complete_hour_or_daily_coverage():
    from zones import DAY_MS, HOUR_MS, day_levels

    now = 1_767_888_000_000  # 2026-01-08 12:00 UTC
    today = now // DAY_MS * DAY_MS
    week = (now - 4 * DAY_MS) // (7 * DAY_MS) * (7 * DAY_MS) + 4 * DAY_MS
    previous_week = week - 7 * DAY_MS
    previous_day = today - DAY_MS

    # Full previous-week plus previous-day hourly coverage.
    hourly = [_flat_candle(ts) for ts in range(previous_week, today, HOUR_MS)]
    labels = {level.label for level in day_levels(hourly, now)}
    assert {'PDH', 'PDL', 'PWH', 'PWL'} <= labels

    # Start coverage alone is not enough: one missing hour suppresses both
    # affected complete-period labels when no daily fallback is available.
    gapped = [c for c in hourly if c[0] not in
              (previous_day + 5 * HOUR_MS, previous_week + 5 * HOUR_MS)]
    labels = {level.label for level in day_levels(gapped, now)}
    assert not {'PDH', 'PDL'} & labels

    # Daily fallback requires exact UTC dates, not a row count that can include
    # duplicates. Complete daily candles cover the previous day/week despite
    # an hourly gap; removing a date invalidates that fallback.
    daily = [_flat_candle(ts) for ts in range(previous_week, today, DAY_MS)]
    labels = {level.label for level in day_levels(gapped, now, candles_1d=daily)}
    assert {'PDH', 'PDL', 'PWH', 'PWL'} <= labels
    duplicate_daily = daily.copy()
    duplicate_daily[1] = duplicate_daily[0].copy()
    labels = {level.label for level in day_levels(gapped, now, candles_1d=duplicate_daily)}
    assert not {'PWH', 'PWL'} <= labels
    malformed_daily = daily.copy()
    malformed_daily[1][0] = None
    labels = {level.label for level in day_levels(gapped, now, candles_1d=malformed_daily)}
    assert not {'PWH', 'PWL'} <= labels


def test_scenario_4h_features_are_utc_aligned_and_unknown_without_coverage():
    from scenarios import features

    def trend_candle(ts, close):
        return [ts, close, close + 1, close - 1, close, 1]

    rows = [trend_candle(i * 3_600_000, 100 + i * 0.1) for i in range(201)]
    lad = {'above': [{'lo': 110.0, 'strength': 1.0}],
           'below': [{'hi': 90.0, 'strength': 1.0}]}
    kwargs = dict(lad=lad, price=100.0, atr=10.0,
                  closes_1h=[row[4] for row in rows[-200:]],
                  btc_closes_1h=[row[4] for row in rows[-200:]])
    first = features(**kwargs, candles_1h=rows[:200], btc_candles_1h=rows[:200])
    # Slide the same rolling window by one hour. Shared complete UTC 4h bars
    # produce exactly the same last-window trend.
    second = features(**kwargs, candles_1h=rows[1:201], btc_candles_1h=rows[1:201])
    assert first['trend_4h'] == second['trend_4h']
    assert first['btc_trend_4h'] == second['btc_trend_4h']

    incomplete = rows[:100]
    incomplete.pop(97)  # makes the final UTC 4h bucket partial: 24 complete bars remain
    short_kwargs = dict(lad=lad, price=100.0, atr=10.0,
                        closes_1h=[row[4] for row in incomplete],
                        btc_closes_1h=[row[4] for row in incomplete])
    out = features(**short_kwargs, candles_1h=incomplete, btc_candles_1h=incomplete)
    assert out['trend_4h'] is None and out['btc_trend_4h'] is None


def test_scenario_model_falls_back_when_required_utc_feature_is_missing():
    from scenarios import probability

    class MustNotPredict:
        def predict_proba(self, _x):
            raise AssertionError('model must not receive missing feature')

    result = probability({'p_geo': 0.4, 'trend_4h': None},
                         {'features': ['trend_4h'], 'clf': MustNotPredict(), 'calibrator': None})
    assert result['p_up'] == 0.4
    assert 'недостаточно признаков' in result['source']


def test_optional_raw_event_log_reports_queue_drops_and_writer_errors(tmp_path):
    from queue import Full
    from raw_event_log import RawEventLog

    class FullQueue:
        maxsize = 1

        def qsize(self):
            return 1

        def put_nowait(self, _item):
            raise Full

    log = RawEventLog(str(tmp_path / 'raw'))
    log._queue = FullQueue()
    log._start_writer = lambda: None
    assert log.append(source='websocket', venue='test', channel='trades', connection_id='c1', payload=b'{}') is None
    diag = log.diagnostics()
    assert diag['dropped_queue_full'] == 1 and diag['queued'] == 1

    blocked_parent = tmp_path / 'not-a-directory'
    blocked_parent.write_text('x', encoding='utf-8')

    class OneItemQueue:
        maxsize = 1

        def __init__(self):
            self.items = [(blocked_parent / 'events.jsonl.gz', b'{}\n')]

        def get(self):
            if self.items:
                return self.items.pop()
            raise StopIteration

        def task_done(self):
            pass

        def qsize(self):
            return len(self.items)

    log._queue = OneItemQueue()
    try:
        log._writer()
    except StopIteration:
        pass
    assert log.diagnostics()['write_errors'] == 1


@pytest.mark.parametrize('market', ['spot', 'futures'])
def test_closed_minute_stream_publishes_only_complete_buckets(market):
    from fetcher import TIMEFRAME_MS
    md = MarketData(symbol='BTC/USDT:USDT')
    start = 1_800_000_000_000 // TIMEFRAME_MS * TIMEFRAME_MS
    count = TIMEFRAME_MS // 60_000

    def send(ts, closed=True, close='10'):
        event = ts + 60_000
        md.apply_kline(market, {'i': '1m', 't': ts, 'T': event - 1,
                                'o': '10', 'h': '11', 'l': '9', 'c': close,
                                'v': '3', 'q': '30', 'V': '2', 'Q': '20',
                                'n': 5, 'x': closed}, event, received_ms=event + 50)

    for i in range(1, count):
        send(start + i * 60_000)
    assert md.drain_kline_rows(market, include_live=False) == []
    assert md.incomplete[market] == {start}
    assert md.backfill_wanted[market] == start
    assert md.finalized_until[market] < start
    send(start)
    assert not md.incomplete[market]
    assert md.drain_kline_rows(market, include_live=False)[0]['timestamp'] == start

    for bucket in (start + TIMEFRAME_MS, start + 2 * TIMEFRAME_MS):
        for i in range(count):
            ts = bucket + i * 60_000
            send(ts)
            send(ts, closed=False, close='11')
        rows = md.drain_kline_rows(market, include_live=False)
        assert len(rows) == 1
        assert rows[0]['timestamp'] == bucket
        assert rows[0]['volume'] == 3 * count
        assert rows[0]['close'] == 10
        assert md.finalized_until[market] == bucket
    assert md.kline_events_invalid == 0
    assert md.kline_buckets_published == 3
    assert md.kline_buckets_incomplete == 1


def test_buffered_structured_signal_is_dropped_on_history_gap():
    structured = {'is_structured': True}
    independent = {'is_structured': False}
    queued = [('GAPPED', structured), ('READY', structured), ('GAPPED', independent)]
    assert Scanner._filter_candle_signals(queued, {'READY': object()}) == [
        ('READY', structured), ('GAPPED', independent),
    ]


def test_closed_range_breakout_requires_latest_closed_contiguous_window():
    step, start = 900_000, 1_800_000_000_000
    bars = pl.DataFrame({'timestamp': [start + step*i for i in range(21)],
                         'high': [11.] * 20 + [13.], 'low': [9.] * 21,
                         'close': [10.] * 20 + [12.]})
    now = start + 21*step
    out = Scanner._closed_range_breakout(bars, now)
    assert out['range_breakout'] == 'RANGE BREAK UP' and out['range_boundary'] == 11
    assert Scanner._closed_range_breakout(bars, now - 1) is None
    assert Scanner._closed_range_breakout(bars, now + step) is None
    assert Scanner._closed_range_breakout(bars.filter(pl.col('timestamp') != start + step), now) is None
