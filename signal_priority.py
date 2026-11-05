"""Deterministic portfolio-slot ordering for signals observed in one scan."""

def score(sig: dict) -> float:
    return (float(sig.get('p_edge') or sig.get('ml_score') or 0.0)
            + 0.25 * float(sig.get('rr_blend') or sig.get('rr_trigger') or 0.0)
            + 0.10 * float(sig.get('conf_n') or 0.0)
            - 0.25 * float(sig.get('trigger_over_atr') or 0.0))


def rank(signals):
    return sorted(signals, key=lambda item: score(item[1]), reverse=True)
