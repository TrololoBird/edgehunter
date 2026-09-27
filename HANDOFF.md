# Handoff (2026-09-28)

State of the work when the session moved to the cloud. Delete this file once it is dealt with.

## Done in the last session (uncommitted until this commit)
- **Weekly trend context** (`trend_w`, `breadth_w`): weekly candles per coin (`DataFetcher._weekly_candles_loop`), `strategies.structure.weekly_ref` / `trend_w_of`, journal columns, P(edge) features × direction, `stats.py` splits, webui line, pretraining via REST weekly candles. Context only.
- **Structural stop (eng-6)**: continuation entries put the stop beyond the structural support zone (`zones.STRUCTURE_KINDS`) instead of the 5m trigger's low; the stop goes beyond the farthest of that edge and the deepest test wick, then a pool behind it, then `stop_buffer_atr` = 0.3 ATR (was 0.1) of the anchor's timeframe; 1 ATR floor kept. `logic_version` = `eng-6`.
- The journal was reset at the switch (old one kept locally as `signals.eng5.bak.db`, not in git); open cards were dropped from `scanner_state.json`.

## Evidence behind it (scripts were in the session scratchpad, not in the repo)
- Weekly / monthly EMA: touches, crosses, retests and the 10-80% moves after them behave like parallel lines EMA x 0.8..1.2 once volatility and the 7-day run-up are matched; the trend around the touch is what differs.
- Stops at 0.1 ATR beyond a 15m swing: 47% of the stopped trades then went +2 ATR the trade's way within 8h (27% at 1.5 ATR); 1h swings 18% -> 8%. Targets: no measurable 'repel' exactly at the swing level (continuation per 0.1 ATR flat at 92-97%).
- Sources: Osler NY Fed SR150 (stops cluster just beyond round numbers / obvious levels), Elder SafeZone, LeBeau chandelier, Kaminski & Lo (stops do not change expectancy under a random walk), Liu-Tsyvinski-Wu (crypto momentum 1-4 weeks).

## Open
1. Live check of eng-6 on the owner's machine: `sl_src` of new entries reads `beyond the zone (...)` / `beyond the test wick` / `beyond <pool>`; share of `low_rr` vetoes vs before; no errors in `scanner.log`. The last start hit a Binance NetworkError on the market list and retried; confirm it came up.
2. Proposed but not done: a history test of the stop in the bot's own scheme (zone on the anchor timeframe, entry on the trigger timeframe, stop beyond the zone vs the old trigger-low stop), measuring noise stop-outs, win rate, R and R:R vetoes.
3. After 2-3 weeks of eng-6 data: `stats.py` splits `coin weekly trend vs the signal` and `market weekly breadth vs the signal`; only a proven negative bucket may become a veto.
