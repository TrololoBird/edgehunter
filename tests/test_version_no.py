import signal_book
import stats


def test_version_no_with_suffix():
    for f in (signal_book.version_no, stats.version_no):
        assert f('eng-169e') == 169 and f('eng-57') == 57 and f('pre-eng-144') == 0 and f(None) == 0 and f('x') == 0
