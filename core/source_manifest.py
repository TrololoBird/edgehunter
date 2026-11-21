"""Source manifests for the verified strategy and signal contracts.

The previous runtime registered a large collection of classes because their
names looked like published methods. A name is not evidence of a method. A
strategy is allowed into the working registry only when this manifest contains
an explicit primary source and the implementation version has been reviewed
against that source.

The initial v2 manifest is deliberately empty. This is a safety boundary, not
a claim that the old classes are correct. They remain importable for forensic
work, but they cannot create cards or orders.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Mapping, Optional


SOURCE_MANIFEST_VERSION = "sources-v2-empty"


@dataclass(frozen=True)
class SourceRecord:
    """A source-backed strategy contract with no heuristic escape hatch."""

    strategy_id: str
    decision: str
    primary_source: Optional[str] = None
    source_fragment: Optional[str] = None
    implementation_version: Optional[str] = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.decision not in {"KEEP", "FIX", "REMOVE"}:
            raise ValueError(f"invalid source decision: {self.decision}")
        if self.decision in {"KEEP", "FIX"} and not self.primary_source:
            raise ValueError(f"{self.strategy_id}: a retained strategy needs a primary source")


# Every legacy registration is explicitly quarantined until a source-backed v2
# implementation is reviewed. The URLs in the audit document are evidence for
# the decision, not an approval of the old implementation.
LEGACY_SOURCE_RECORDS: Mapping[str, SourceRecord] = {
    name: SourceRecord(name, "REMOVE", notes="Legacy AI-generated implementation is not admitted to v2")
    for name in (
        "continuation", "sweep", "silver_bullet", "wyckoff", "cascade", "breakout",
        "supply_demand", "value_area", "auction", "trendline_break", "trendline_touch",
        "bollinger_wm", "bollinger_method3", "bollinger_method1", "orb", "connors",
        "pump_start", "dump_start", "pump_top", "dump_bounce", "cup_handle", "po3", "oi_build",
    )
}

# New implementations are added only through a reviewed source record. The
# production registry intentionally starts empty.
VERIFIED_SOURCE_RECORDS: dict[str, SourceRecord] = {}


def source_manifest_payload() -> dict:
    return {
        "manifest_version": SOURCE_MANIFEST_VERSION,
        "verified": {k: asdict(v) for k, v in sorted(VERIFIED_SOURCE_RECORDS.items())},
        "legacy": {k: asdict(v) for k, v in sorted(LEGACY_SOURCE_RECORDS.items())},
    }


def source_manifest_hash() -> str:
    payload = json.dumps(source_manifest_payload(), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def verified_record(strategy_id: str) -> Optional[SourceRecord]:
    return VERIFIED_SOURCE_RECORDS.get(strategy_id)


def require_verified(strategy_id: str) -> SourceRecord:
    record = verified_record(strategy_id)
    if record is None:
        raise ValueError(f"strategy is not source-verified: {strategy_id}")
    return record

