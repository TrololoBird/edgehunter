# Connors RSI(2) on crypto daily (478 coins, 2021-10-01 .. 2026-09-30)

**Summary (cloud run 2026-10-04, 478 coins, 2021-10 .. 2026-09).** By the pre-registered rule (book variant 10/90, mean net > 0 in BOTH halves): **long KEPT** (+0.14% older, +0.57% newer; but the 90% month intervals include 0 in both halves: [-1.34..+1.61], [-1.27..+2.80] - a weak pass), **short NOT kept** (+0.09% older, -0.40% newer). The 5/95 variant (live since eng-58) is the same picture: long +0.64% / +1.20% (CI includes 0), short negative in both halves. The 3-ATR catastrophic stop lowers the long's mean (+0.10% vs +0.34%).

Rules: the docstring of `research_connors.py` (pre-registered). Net of 0.20% round trip.

| variant | side | half | trades | mean | 90% (by month) | win | avg days |
|---|---|---|---:|---:|---|---:|---:|
| book 10/90, SMA5 exit, no stop | long | older | 1937 | +0.14% | [-1.34%..+1.61%] | 59% | 4.4 |
| book 10/90, SMA5 exit, no stop | long | newer | 1673 | +0.57% | [-1.27%..+2.80%] | 59% | 4.5 |
| book 10/90, SMA5 exit, no stop | long | all | 3610 | +0.34% | [-0.84%..+1.69%] | 59% | 4.4 |
| book 10/90, SMA5 exit, no stop | short | older | 3116 | +0.09% | [-2.33%..+2.26%] | 70% | 4.0 |
| book 10/90, SMA5 exit, no stop | short | newer | 8449 | -0.40% | [-1.84%..+1.11%] | 63% | 4.1 |
| book 10/90, SMA5 exit, no stop | short | all | 11565 | -0.26% | [-1.53%..+0.92%] | 65% | 4.0 |
| 5/95 | long | older | 927 | +0.64% | [-0.96%..+2.36%] | 60% | 4.3 |
| 5/95 | long | newer | 875 | +1.20% | [-0.31%..+3.11%] | 60% | 4.3 |
| 5/95 | long | all | 1802 | +0.91% | [-0.23%..+2.14%] | 60% | 4.3 |
| 5/95 | short | older | 1516 | -0.92% | [-4.36%..+2.53%] | 66% | 4.4 |
| 5/95 | short | newer | 4795 | -0.46% | [-1.86%..+1.17%] | 62% | 4.2 |
| 5/95 | short | all | 6311 | -0.57% | [-1.91%..+0.83%] | 63% | 4.2 |
| 10/90 + day-10 cap | long | older | 1946 | +0.16% | [-1.23%..+1.65%] | 59% | 4.2 |
| 10/90 + day-10 cap | long | newer | 1688 | +0.57% | [-1.26%..+2.67%] | 59% | 4.4 |
| 10/90 + day-10 cap | long | all | 3634 | +0.35% | [-0.77%..+1.60%] | 59% | 4.3 |
| 10/90 + day-10 cap | short | older | 3171 | +0.13% | [-2.05%..+2.26%] | 69% | 3.8 |
| 10/90 + day-10 cap | short | newer | 8532 | -0.48% | [-2.08%..+1.06%] | 64% | 4.0 |
| 10/90 + day-10 cap | short | all | 11703 | -0.31% | [-1.64%..+0.99%] | 65% | 3.9 |
| 10/90 + 3 ATR stop (ours) | long | older | 1958 | -0.05% | [-1.55%..+1.57%] | 59% | 4.0 |
| 10/90 + 3 ATR stop (ours) | long | newer | 1736 | +0.28% | [-1.56%..+2.39%] | 57% | 4.1 |
| 10/90 + 3 ATR stop (ours) | long | all | 3694 | +0.10% | [-1.12%..+1.37%] | 58% | 4.1 |
| 10/90 + 3 ATR stop (ours) | short | older | 3354 | +0.25% | [-1.61%..+2.03%] | 68% | 3.3 |
| 10/90 + 3 ATR stop (ours) | short | newer | 8939 | -0.72% | [-2.25%..+0.77%] | 63% | 3.4 |
| 10/90 + 3 ATR stop (ours) | short | all | 12293 | -0.45% | [-1.60%..+0.78%] | 64% | 3.4 |
