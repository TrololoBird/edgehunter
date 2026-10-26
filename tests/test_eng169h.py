from signal_book import shadow_veto
from strategies import confirm


def test_raid_without_flow_or_absorption_blocks():
    c = {'flow': False, 'orderflow': False, 'spot': True}
    r = confirm.missing('sweep', c, 'SWEEP LOW')
    assert r == 'no_flow_absorb'
    assert shadow_veto({}, r) == 'no_flow_absorb'          # blocking, not a shadow filter


def test_raid_kept_by_delta_or_absorption_or_no_data():
    assert confirm.missing('sweep', {'flow': True, 'orderflow': False}) != 'no_flow_absorb'
    assert confirm.missing('po3', {'flow': False, 'orderflow': 'ABSORPTION'}) != 'no_flow_absorb'
    assert confirm.missing('wyckoff', {'flow': False, 'orderflow': 'divergence'}) != 'no_flow_absorb'
    assert confirm.missing('sweep', {'flow': None, 'orderflow': False}) != 'no_flow_absorb'


def test_pump_top_only_not_pump_start_or_others():
    c = {'flow': False, 'orderflow': False}
    assert confirm.missing('pump', c, 'PUMP TOP') == 'no_flow_absorb'
    assert confirm.missing('pump', c, 'PUMP START') != 'no_flow_absorb'
    assert confirm.missing('trendline', c, 'TL TOUCH DOWN') != 'no_flow_absorb'
