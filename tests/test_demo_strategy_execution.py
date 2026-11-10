from executor import DemoExecutor


def test_demo_does_not_disable_oi_build_by_default():
    # The demo account is the experiment harness; strategy quality is measured
    # from fills rather than hidden by a permanent setup blacklist.
    from config import CONFIG
    assert 'OI BUILD LONG' not in CONFIG.executor.demo_off_setups
    assert 'OI BUILD SHORT' not in CONFIG.executor.demo_off_setups


def test_validate_levels_accepts_valid_long_and_short():
    assert DemoExecutor.validate_levels({'entry': 100, 'sl': 98, 'tp1': 104, 'tp2': 108, 'tp3': 112}, 1) is None
    assert DemoExecutor.validate_levels({'entry': 100, 'sl': 102, 'tp1': 96, 'tp2': 92, 'tp3': 88}, -1) is None


def test_validate_levels_rejects_inverted_protection_and_targets():
    assert DemoExecutor.validate_levels({'entry': 100, 'sl': 101, 'tp1': 104}, 1).startswith('DATA_ERROR')
    assert DemoExecutor.validate_levels({'entry': 100, 'sl': 98, 'tp1': 99}, 1).startswith('DATA_ERROR')
    assert DemoExecutor.validate_levels({'entry': 100, 'sl': 98, 'tp1': 104, 'tp2': 103}, 1).startswith('DATA_ERROR')

