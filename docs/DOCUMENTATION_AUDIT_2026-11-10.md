# Documentation audit — 2026-11-10

This is an independent consistency audit of the repository's prose, instructions, history notes and code docstrings.
Documentation is evidence about the project, not authority over the executable code.

## Current facts verified against code

- The active strategy registry is generated in `strategies/__init__.py`. Split modes are
  `value_area`, `auction`, `trendline_break`, `trendline_touch`, `bollinger_wm`,
  `bollinger_method3`, `bollinger_method1`, `pump_start`, `dump_start`, `pump_top`,
  `dump_bounce`, and `cascade`; old family names are compatibility aliases only.
- The complete-data universe is capped by `CONFIG.exchange.max_pairs` (70 in the current
  defaults). Older documents said 150 or 300; those statements were corrected where they
  described the current system.
- The current checkout intentionally contains no `tests/` directory. Operational instructions
  now use linting and `python -m compileall -q .`; historical test counts remain historical
  evidence only.
- Research scripts named in older handoffs are not all present in this checkout. A report that
  cites one is not a reproducible command until the file and its input data exist.
- `constraints.txt` currently pins `ccxt==4.5.90`; deployment documentation that named 4.5.85
  was stale and was corrected.

## Evidence limits

Many research notes contain exact sample sizes, p-values, live measurements and “verified” wording.
Those values cannot be independently reproduced from this checkout alone because the archive,
raw event log and several research scripts are external or absent. They must be treated as dated
observations, not guarantees about the current bot or future performance.

The strategy audit files now label their former regression tests as historical because those files
were removed. `docs/HISTORY.md`, `HANDOFF.md`, and related plan files are explicitly marked as
historical snapshots where they name old commands, aliases or dependency versions.

## External checks used

The runtime guidance was cross-checked with the [Python 3.14 virtual-environment documentation](https://docs.python.org/3.14/library/venv.html),
the [Binance WebSocket market-stream limits](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect),
and [BingX's TP/SL order documentation](https://bingx.com/en/support/articles/17917912060569). These sources confirm the
need to distinguish current executable behavior from historical claims and venue-specific trigger semantics.
