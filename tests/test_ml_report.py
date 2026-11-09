import sqlite3

from tools.ml_report import evaluate


def test_ml_report_compares_tail_and_prediction_buckets(tmp_path):
    db = tmp_path / "signals.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE signals (ts_ms INTEGER, direction INTEGER, ret_4h REAL, tier0 INTEGER, ml_score REAL, p_edge REAL, regime TEXT, vetoed TEXT)")
    for i in range(100):
        c.execute("INSERT INTO signals VALUES (?,1,?,?,?,?,?,?)", (i, i % 2, 0.01 if i < 50 else -0.01,
                                                                     -float(i) / 100, i / 100, 'flat·normal', ''))
    c.commit()
    report = evaluate(str(db), min_rows=20)
    assert report['rows'] == 100
    assert report['anomaly']['tail_rows'] >= 1
    assert 'tail_mean_abs_ret_4h' in report['anomaly']
    assert 'tail_directional_hit_rate' in report['anomaly']
    assert len(report['p_edge']['quintiles']) == 5
    assert report['regime']['flat·normal']['rows'] == 100
