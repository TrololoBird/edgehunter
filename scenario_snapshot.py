"""Immutable publication snapshot shared by briefing and outcome consumers."""
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ScenarioSnapshot:
    publication_id: str
    run_id: str
    build_id: str
    schema_v: int
    rules_v: str
    symbol: str
    slot: str
    created_ts: float
    asof_ts: float
    price: Optional[float]
    bias: Any
    state: Dict[str, Any]
    zones: Any
    scenario: Any
    validity: str = 'valid'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
