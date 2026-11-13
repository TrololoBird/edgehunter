import json

import core.model_provenance as provenance
from tools.model_audit import audit
import scenarios


def test_model_manifest_detects_tampering(tmp_path, monkeypatch):
    model = tmp_path / "pretrained.pkl"
    model.write_bytes(b"model-v1")
    state = {"logic_version": "logic-test", "start": "2026-01-01", "end": "2026-01-02"}
    monkeypatch.setattr(provenance, "provenance_fields", lambda: {
        "source_commit": "test-commit", "implementation_hash": "test-implementation", "source_dirty": 0})
    provenance.write_manifest(str(model), state)
    assert provenance.validate_manifest(str(model), state) == (True, "ok")
    monkeypatch.setattr(provenance, "provenance_fields", lambda: {
        "source_commit": "other-commit", "implementation_hash": "test-implementation", "source_dirty": 0})
    assert provenance.validate_manifest(str(model), state) == (False, "source_commit_mismatch")
    monkeypatch.setattr(provenance, "provenance_fields", lambda: {
        "source_commit": "test-commit", "implementation_hash": "test-implementation", "source_dirty": 0})
    model.write_bytes(b"tampered")
    assert provenance.validate_manifest(str(model), state) == (False, "artifact_hash_mismatch")


def test_model_manifest_rejects_missing_or_wrong_schema(tmp_path, monkeypatch):
    model = tmp_path / "pretrained.pkl"
    model.write_bytes(b"model-v1")
    state = {"logic_version": "logic-test"}
    monkeypatch.setattr(provenance, "provenance_fields", lambda: {
        "source_commit": "test-commit", "implementation_hash": "test-implementation", "source_dirty": 0})
    assert provenance.validate_manifest(str(model), state) == (False, "manifest_missing")
    provenance.write_manifest(str(model), state)
    path = provenance.manifest_path(str(model))
    payload = json.loads(open(path, encoding="utf-8").read())
    payload["feature_schema_version"] = "future-schema"
    open(path, "w", encoding="utf-8").write(json.dumps(payload))
    assert provenance.validate_manifest(str(model), state) == (False, "feature_schema_mismatch")


def test_model_audit_does_not_load_legacy_pickles(tmp_path):
    (tmp_path / 'models').mkdir()
    (tmp_path / 'models' / 'legacy.pkl').write_bytes(b'not-a-pickle')
    result = audit(str(tmp_path))
    assert result['status'] == 'attention_required'
    assert result['legacy_unverified'] == ['models/legacy.pkl']


def test_scenario_model_requires_manifest(tmp_path):
    path = tmp_path / 'scenario_prob.pkl'
    path.write_bytes(b'not-loaded')
    scenarios._model_cache.clear()
    assert scenarios.load_model(str(path)) is None
    assert scenarios.SCENARIO_MODEL_STATUS['reason'] == 'manifest_missing'


def test_scenario_quarantine_is_rejected_before_pickle_load(tmp_path):
    import hashlib
    import json
    path = tmp_path / 'scenario_prob.pkl'
    payload = b'not-loaded'
    path.write_bytes(payload)
    (tmp_path / 'scenario_prob.pkl.manifest.json').write_text(json.dumps({
        'model_id': path.name, 'artifact_sha256': hashlib.sha256(payload).hexdigest(),
        'quarantine': True}), encoding='utf-8')
    scenarios._model_cache.clear()
    assert scenarios.load_model(str(path)) is None
    assert scenarios.SCENARIO_MODEL_STATUS['reason'] == 'legacy_quarantine'
