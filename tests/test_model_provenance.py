import json

import core.model_provenance as provenance


def test_model_manifest_detects_tampering(tmp_path, monkeypatch):
    model = tmp_path / "pretrained.pkl"
    model.write_bytes(b"model-v1")
    state = {"logic_version": "logic-test", "start": "2026-01-01", "end": "2026-01-02"}
    monkeypatch.setattr(provenance, "provenance_fields", lambda: {
        "source_commit": "test-commit", "implementation_hash": "test-implementation", "source_dirty": 0})
    provenance.write_manifest(str(model), state)
    assert provenance.validate_manifest(str(model), state) == (True, "ok")
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
