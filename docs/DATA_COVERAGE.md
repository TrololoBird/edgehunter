# Journal column coverage (signals.db, last 20k rows, checked 2026-10-16)

Null share per row kind and why. "By design" = the source does not exist for that coin / row, not a feed gap.

| column | setup | card | entry | anomaly | structured | rush | why |
|---|---|---|---|---|---|---|---|
| p_edge | 0.81 | 1.00 | 0.91 | 0.69 | 0.64 | 1.00 | written only on setup / anomaly / structured rows (`journal.py` ~571) and only once the online SuccessModel has learnt (`ml.predict`: n == 0 -> None); card / rush rows never carry it. By design; usable only on the rows that have it |
| hl_net_usd | 0.37 | 0.36 | 0.37 | 0.24 | 0.34 | 1.00 | None when the coin is not on Hyperliquid (`scanner.py` ~1224). By design |
| cb_premium | 0.31 | 0.31 | 0.32 | 0.17 | 0.31 | 1.00 | None without a Coinbase spot pair (`scanner.py` ~1227). By design |
| okx_book_imb | 0.52 | 0.57 | 0.58 | 0.31 | 0.47 | 1.00 | OKX / Bybit books are polled only for the hot coins (`extdata.books_loop` over `depth.active()`). By design |
| depth_imb | ~0.83 | | | | | | Binance books only for hot coins (books 60). By design |
| macro (vix, fng, etf_flow_*, tradfi) | ~0.93 | | | | | | added in eng-133 on 2026-10-15; etf_flow_* from the first Farside timer run 2026-10-16 07:30 UTC |

Rush rows are Tier-0 impulse events without the enrichment block: every enrichment column is null there.

Consequence: analyses that use these columns must condition on the coin having the source (HL listing, Coinbase pair,
hot book), else the "null" bucket is a coin-selection effect (hot / large coins), not the feature's effect.
