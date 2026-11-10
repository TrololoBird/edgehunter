from pathlib import Path


def test_strategy_detectors_do_not_gate_behavior_on_release_labels():
    """Release labels identify provenance; they must not silently disable strategy rules."""
    root = Path(__file__).resolve().parents[1]
    for path in (root / 'strategies').glob('*.py'):
        text = path.read_text(encoding='utf-8')
        assert 'logic_version ==' not in text, path
        assert 'logic_version >=' not in text, path
        assert 'logic_version <=' not in text, path
