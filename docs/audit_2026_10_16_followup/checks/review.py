"""Reviewer findings 1/2: an inner 1m gap keeps its bucket; the pullback test sees its first partial 15m bar.
Usage: python review.py <repo>"""
import sys
sys.path.insert(0, sys.argv[1])
from levels import resample, pullback_spread_ok  # noqa: E402

m = [[i * 60_000, 100., 101., 99., 100., 1., .5, .01] for i in range(120) if i != 75]   # minute 75 lost on reconnect
print('inner gap: 15m bars', len(resample(m, 15, 120 * 60_000)), '(8 buckets, the gapped one kept)')
print('leading partial: 15m bars', len(resample(m[3:], 15, 120 * 60_000)), '(first bucket dropped)')
w = [[i * 60_000, 100., 110., 90., 100., 1., .5, .01] for i in range(7, 29)]   # zone 10:07, trigger 10:29, wide bars
print('pullback 10:07-10:29, wide test bars: ok =', pullback_spread_ok(w, 7 * 60_000, 29 * 60_000, 8., 240))
