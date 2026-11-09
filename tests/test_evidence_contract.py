import base64
import gzip
import json

from data_quality import QualityState, quality
from raw_event_log import RawEventLog


def test_quality_distinguishes_missing_degraded_and_stale():
    assert quality(100.0, None, 2.0, 10.0, 'book').state is QualityState.MISSING
    assert quality(100.0, 98.0, 2.0, 10.0, 'book').state is QualityState.FRESH
    assert quality(100.0, 98.0, 2.0, 10.0, 'book', coverage=0.5).state is QualityState.DEGRADED
    assert quality(100.0, 95.0, 2.0, 10.0, 'book').state is QualityState.STALE


def test_raw_event_log_preserves_payload_and_hash(tmp_path):
    log = RawEventLog(str(tmp_path), parser_version='test-v1')
    payload = b'{"u":42,"e":123}'
    event_id = log.append(source='websocket', venue='test', channel='depth',
                          connection_id='test:0', payload=payload,
                          exchange_event_time=123, sequence_start=42, sequence_end=42)
    assert event_id
    log.flush()
    files = list(tmp_path.rglob('*.jsonl.gz'))
    assert len(files) == 1
    with gzip.open(files[0], 'rt', encoding='utf-8') as fh:
        row = json.loads(fh.readline())
    assert row['event_id'] == event_id
    assert base64.b64decode(row['raw_payload_b64']) == payload
    assert row['payload_sha256']
    assert row['sequence_start'] == row['sequence_end'] == 42


def test_raw_event_log_is_disabled_without_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv('EDGEHUNTER_RAW_LOG_DIR', raising=False)
    log = RawEventLog()
    assert not log.enabled
    assert log.append(source='websocket', venue='test', channel='x',
                      connection_id='test:0', payload=b'{}') is None
    assert not list(tmp_path.iterdir())
