"""eng-169e: no demo entry when BingX's price is off Binance's by more than executor.max_entry_basis (0.6%)."""
from executor import basis_reject


def test_basis_filter():
    assert basis_reject(0.0) is None and basis_reject(0.0059) is None and basis_reject(-0.0059) is None
    assert 'basis' in basis_reject(0.0115) and 'basis' in basis_reject(-0.0189)    # LAB -1.15%, PONS -1.89% at entry
