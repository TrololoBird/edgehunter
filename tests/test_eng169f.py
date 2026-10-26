"""eng-169f (the owner: the demo has no limits): no shadow-only setups, no crowd cap."""
from config import CONFIG
from signal_book import SHADOW_SETUPS, shadow_of


def test_no_setup_is_held_in_shadow():
    assert SHADOW_SETUPS == ()
    for g in ('OI BUILD LONG', 'BB3 LONG', 'RSI2 LONG', 'RSI2X SHORT', 'FLUSH REVERSAL', 'SQUEEZE REVERSAL'):
        assert shadow_of(g) is None


def test_no_crowd_cap():
    assert CONFIG.strategies.crowd_max == 0 and CONFIG.strategies.crowd_tag == 6
