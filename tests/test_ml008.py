import pytest
from scanner import Scanner
from journal import SignalJournal
from types import SimpleNamespace
import math

def test_missing_data_not_zero_and_journal_data_quality(tmp_path):
    # 1. Test Scanner _tier0_metrics handles missing flow snapshot (missing data vs zero)
    scanner = Scanner.__new__(Scanner)
    scanner.journal = None
    scanner.fetcher = SimpleNamespace(
        flow=SimpleNamespace(snapshot=lambda now: {}), # empty snapshot -> missing data
        whales=SimpleNamespace(net_units=lambda sym, w, now: 0.0, cluster=lambda sym, now: 0),
        rush=SimpleNamespace(stats=lambda sym, now: {}),
        depth=SimpleNamespace(sweep_vs_depth=lambda sym, usd, side, band: None),
        deriv_snapshot=lambda sym, now: {'agg_oi_change_5m': 0.0}
    )
    scanner.market_data = {
        "BTC/USDT:USDT": SimpleNamespace(
            season=None, ticker_samples=[], oi_samples=[], minute_klines=[],
            ret_std=0.01, oi_std=0.1, avg_minute_usd=1000.0, spot_minute_klines=[]
        )
    }
    
    metrics = scanner._tier0_metrics(1000000.0)
    btc_m = metrics["BTC/USDT:USDT"]
    
    # Verify data_quality_ok is False and missing metrics are NaN (not forced 0.0)
    assert btc_m.get('data_quality_ok') is False
    assert math.isnan(btc_m.get('agg_cvd_5m'))
    assert math.isnan(btc_m.get('top_venue_share'))

    # 2. Test SignalJournal _base_row sets data_quality_ok correctly based on signal flag
    db_path = str(tmp_path / "test_journal.db")
    journal = SignalJournal(db_path)
    
    sig_ok = {'long_score': 10, 'data_quality_ok': True}
    sig_bad = {'long_score': 5, 'data_quality_ok': False}
    
    row_ok = journal._base_row(1000, "BTC/USDT:USDT", "anomaly", "TEST", 1, 100.0, sig_ok)
    row_bad = journal._base_row(1000, "ETH/USDT:USDT", "anomaly", "TEST", 1, 100.0, sig_bad)
    
    assert row_ok['data_quality_ok'] == 1
    assert row_bad['data_quality_ok'] == 0
