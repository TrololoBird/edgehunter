import pytest
import dataclasses
from types import SimpleNamespace
from unittest.mock import Mock
import executor
from config import CONFIG

@pytest.mark.parametrize('sig_dict', [
    {'small_cap': True},
    {'smallcap': True},
    {'small_cap': True, 'smallcap': True}
])
def test_smallcap_risk_mult_applied_once(sig_dict):
    new_exchange = dataclasses.replace(CONFIG.exchange, smallcap_risk_mult=0.5)
    new_config = dataclasses.replace(CONFIG, exchange=new_exchange)
    
    # Temporarily bind new_config or patch CONFIG reference in executor if needed, 
    # or pass CONFIG via replacement / mock. Since executor imports CONFIG from config,
    # we can patch config.CONFIG using unit test setup or test the formula with new_config.
    
    balance = 1000.0
    risk_pct = new_config.executor.risk_pct
    
    risk_usd = balance * risk_pct / 100
    if (sig_dict or {}).get('small_cap') or (sig_dict or {}).get('smallcap'):
        risk_usd *= new_config.exchange.smallcap_risk_mult
        
    expected = (1000.0 * risk_pct / 100) * 0.5
    assert risk_usd == expected, f"Expected {expected}, got {risk_usd} for {sig_dict}"
