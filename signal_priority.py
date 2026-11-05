"""Deterministic portfolio-slot ordering and a short aggregation window."""
import time

class SignalBatcher:
    def __init__(self, window_ms: int = 500):
        self.window = window_ms / 1000.0
        self.pending = []
        self.started = None

    def add(self, signals):
        if signals:
            self.pending.extend(signals)
            self.started = self.started or time.monotonic()
        if self.started is None or time.monotonic() - self.started < self.window:
            return []
        out, self.pending = self.pending, []
        self.started = None
        return rank(out)

def score(sig: dict) -> float:
    return (float(sig.get('p_edge') or sig.get('ml_score') or 0.0)
            + 0.25 * float(sig.get('rr_blend') or sig.get('rr_trigger') or 0.0)
            + 0.10 * float(sig.get('conf_n') or 0.0)
            - 0.25 * float(sig.get('trigger_over_atr') or 0.0))


def rank(signals):
    return sorted(signals, key=lambda item: score(item[1]), reverse=True)
