"""Signed-by-provenance metadata for offline model artifacts.

The model itself remains a legacy pickle for reproducibility, but production
loads it only when the adjacent manifest describes the exact artifact and the
feature/logic contract currently running.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from typing import Any, Dict

from core.provenance import fields as provenance_fields

FEATURE_SCHEMA_VERSION = "features-v1"


def _sha256(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _library_versions() -> Dict[str, str]:
    versions: Dict[str, str] = {}
    for name in ("numpy", "polars", "river", "scikit-learn", "lightgbm"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "unavailable"
    return versions


def manifest_path(model_path: str | os.PathLike[str]) -> str:
    return f"{model_path}.manifest.json"


def build_manifest(model_path: str, state: Dict[str, Any]) -> Dict[str, Any]:
    provenance = provenance_fields()
    return {
        "model_id": Path(model_path).name,
        "artifact_sha256": _sha256(model_path),
        "logic_version": state.get("logic_version"),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "training_period": {"start": state.get("start"), "end": state.get("end")},
        "source_commit": provenance["source_commit"],
        "implementation_hash": provenance["implementation_hash"],
        "source_dirty": provenance["source_dirty"],
        "library_versions": _library_versions(),
    }


def write_manifest(model_path: str, state: Dict[str, Any]) -> str:
    path = manifest_path(model_path)
    payload = build_manifest(model_path, state)
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return path


def validate_manifest(model_path: str, state: Dict[str, Any], *, require: bool = True) -> tuple[bool, str]:
    path = manifest_path(model_path)
    if not os.path.isfile(path):
        return (False, "manifest_missing") if require else (True, "manifest_optional")
    try:
        with open(path, encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, ValueError) as exc:
        return False, f"manifest_unreadable:{type(exc).__name__}"
    if manifest.get("model_id") != Path(model_path).name:
        return False, "model_id_mismatch"
    if manifest.get("artifact_sha256") != _sha256(model_path):
        return False, "artifact_hash_mismatch"
    if manifest.get("logic_version") != state.get("logic_version"):
        return False, "logic_version_mismatch"
    if manifest.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        return False, "feature_schema_mismatch"
    current = provenance_fields()
    if manifest.get("source_dirty"):
        return False, "trained_from_dirty_source"
    if current.get("source_dirty"):
        return False, "runtime_source_dirty"
    if manifest.get("source_commit") != current.get("source_commit"):
        return False, "source_commit_mismatch"
    if manifest.get("implementation_hash") != current.get("implementation_hash"):
        return False, "implementation_hash_mismatch"
    return True, "ok"
