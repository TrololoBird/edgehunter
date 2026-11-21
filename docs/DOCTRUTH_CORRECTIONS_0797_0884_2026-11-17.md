# DOCTRUTH: исправления докстрингов №797–884

Дата формирования: 2026-11-17 UTC.

Область: только записи DOCTRUTH №797–884. Поле docstring в реестре сохранено без изменений; исправленный текст находится в corrected_docstring. В рамках v2 master task эти corrected_docstring применены к соответствующим Python docstring-узлам; тела функций не менялись этой операцией.

Политика: неподтверждённые атрибуции, параметры, owner/eng/audit/quote claims и заявления об экспериментах удалены. Нейтральное описание локального вычисления оставлено только как описание операции; оно не объявляет новую методику и не заявляет торговую эффективность.

## Проверенные URL

- https://arxiv.org/abs/1011.6402
- https://arxiv.org/abs/1412.5558
- https://bollingerbands.us/help-methods.php
- https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial
- https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2
- https://get.investors.com/wp-content/uploads/2024/08/IBDD-How-to-buy-Stocks-infographic.pdf
- https://github.com/binance/binance-public-data
- https://mebfaber.com/2007/09/17/tony-crabel-and-the-secret-orb/
- https://numpy.org/doc/stable/reference/generated/numpy.std.html
- https://oxfordstrat.com/coasdfASD32/uploads/2016/01/turtle-rules.pdf
- https://ta-lib.org/functions/ema.html
- https://ta-lib.org/functions/rma.html
- https://vikingtradinggroup.com/wp-content/uploads/2023/01/Peter_Steidlmayer_Steven_Hawkins-Steidlmayer_on_Markets-EN.pdf
- https://www.binance.com/en/fee/trading
- https://www.cmegroup.com/education/courses/introduction-to-futures/open-interest.html
- https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/PSAR
- https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI
- https://www.thepatternsite.com/cup.html

## Исправления по записям

### DOC-0797 — strategies/cascade.py:50 — _cascade_cap_for_rr

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    Cascade zone cap for its own 1R first-retracement rule.

Исправленный докстринг:

    Configured cap for the cascade entry's first-retracement risk/reward calculation.
    No published-strategy attribution or performance claim is made.

Причина: Removed the phrase 'its own 1R first-retracement rule'; no external source establishes that rule.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- The origin and validation of the configured cascade cap are not documented.

### DOC-0798 — strategies/cascade.py:61 — cascade_leg

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    The cascade as a leg; its end follows new extremes of the final 1m candles.

Исправленный докстринг:

    Represents a cascade leg using the available final one-minute extrema.
    The description is operational and does not establish a validated cascade pattern.

Причина: Reduced the claim to the observed input transformation; no source defines this exact leg rule.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://github.com/binance/binance-public-data

Утверждения без найденного первоисточника:
- No external source was found for the exact one-minute cascade-leg definition.

### DOC-0799 — strategies/cascade.py:78 — CascadeTracker

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    Loop-side detector state: a running cascade per coin, fired once its leg is big enough.

Исправленный докстринг:

    State for a per-coin cascade detector. It fires only after the configured leg-size condition;
    no claim is made that this condition identifies a causal liquidation cascade.

Причина: Removed the implied event identity and kept only the state-machine description.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://github.com/binance/binance-public-data

Утверждения без найденного первоисточника:
- No external validation was found for the configured cascade detector.

### DOC-0800 — strategies/cascade.py:149 — entry_levels

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    Cascade contract: climax extreme stop and retracement/mean targets.

Исправленный докстринг:

    Builds cascade entry levels from the configured extreme, retracement and target rules.
    These are model conventions, not an externally established strategy.

Причина: Removed the unqualified 'cascade contract' wording and the implied strategy status.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- The retracement, mean-target and stop rules have no identified external primary source.

### DOC-0801 — strategies/classic.py:1 — <module>

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    
    Classic published methods added as their authors define them (eng-29), on the session instruments only
    (CONFIG.strategies.orb_bases: the majors, gold, silver, oil):
    
    - value_area  Dalton's 80% rule by SESSION (eng-95; Dalton "Mind Over Markets"): the session (Asia / London / New York,
                  weekdays) opens outside the previous same session's TPO value area (70% of time at price, eng-58),
                  closes two consecutive 30-minute periods back inside it -> entry at the second period's close, target
                  the far edge, out at the session's close (session_va_event, VA80). Beside it the failed auction
                  (eng-127, failed_auction_event, AUCTION LONG / SHORT). Both run in the maps worker at 15m closes.
    - orb         Toby Crabel's opening range breakout ("Playing the Opening Range Breakout", Stocks & Commodities): the
                  range of a session's first 5 minutes, stop orders the Stretch (10-day SMA of min(High - Open,
                  Open - Low)) beyond its high / low; the first level traded through is the entry (ON THE TOUCH, a stop
                  order), the other level the stop; out at the session's close (eng-146; eng-145's 15m
                  Parabolic SAR exit reverted). Checked
                  loop-side on every final minute (session_orb via strategies.loopside.LoopDetectors).
    - connors     Larry Connors' RSI(2) on DAILY candles, with the trend (close above / below the 200-day SMA): RSI2X = his
                  original rule (a close with RSI(2) < 5, buy on the close; the mirrored short is shadow), RSI2 = the
                  cross-back (eng-84: RSI(2) comes back out of the extreme, the close still beyond the SMA5). Out on the
                  first daily close beyond the current SMA5. He uses no stop: the R unit is 1 daily ATR, position at 1x,
                  and the executor keeps a catastrophe stop 3 R units away (eng-144, our deviation). Checked loop-side
                  after each daily close (strategies.loopside.LoopDetectors._connors_daily).
    

Исправленный докстринг:

    Session-based strategy components represented in this module: profile re-entry, opening-range
    conditions and daily RSI(2) conditions. Thresholds, timeframes, exits and fills are configured
    rules. This text makes no claim to reproduce a published strategy or to have validated performance.

Причина: Removed claims that the module implements published methods as their authors define them and removed owner/engineering provenance.

Удалённые атрибуции/провенанс: Dalton/Market Profile, Crabel, Connors, eng-29, owner/engineering provenance

Внешние URL проверки:
- https://vikingtradinggroup.com/wp-content/uploads/2023/01/Peter_Steidlmayer_Steven_Hawkins-Steidlmayer_on_Markets-EN.pdf
- https://mebfaber.com/2007/09/17/tony-crabel-and-the-secret-orb/
- https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2

Утверждения без найденного первоисточника:
- No primary source was found for the combined local session, fill, stop and exit rules.

### DOC-0802 — strategies/classic.py:37 — value_area

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    (VAL, POC, VAH) of the candles' volume spread evenly over each candle's range, else None. tpo: Market Profile's
        TPO value area (Dalton - eng-58): the candles are merged into 30-minute brackets and every price row a bracket
        visited gets ONE mark (audit C03: a wide candle's single unit was spread thinly over its rows, so a few narrow
        bars at one price made a 70% 'profile' there).

Исправленный докстринг:

    Computes VAL/POC/VAH from the selected candle-volume or time-bracket representation.
    The profile is a project-defined calculation; no published Market Profile or 80% rule is claimed.

Причина: The source describes a local volume/TPO approximation, not the full published profile methodology.

Удалённые атрибуции/провенанс: Dalton, Market Profile TPO value area

Внешние URL проверки:
- https://vikingtradinggroup.com/wp-content/uploads/2023/01/Peter_Steidlmayer_Steven_Hawkins-Steidlmayer_on_Markets-EN.pdf

Утверждения без найденного первоисточника:
- The exact local volume-spread and 30-minute TPO parameters are not established by the cited source.

### DOC-0803 — strategies/classic.py:115 — _complete_quarters

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    Exact session-relative 15m grid, including sessions opening off the UTC quarter.
    
        The old ``start % 15m`` guard silently disabled the COMEX 08:20 ET XAU/XAG session.  Callers use
        ``_session_quarters`` to align the available closed 15m bars to the session origin before this strict check.
        

Исправленный докстринг:

    Checks that a session-relative 15-minute grid is complete, including sessions whose origin is not
    on a UTC quarter.

Причина: Kept the calendar-grid operation and removed historical engineering/audit narrative.

Удалённые атрибуции/провенанс: eng-29/audit narrative

Внешние URL проверки:
- https://github.com/binance/binance-public-data

Утверждения без найденного первоисточника:
- The local completeness check is a policy choice, not an externally validated rule.

### DOC-0804 — strategies/classic.py:124 — _session_quarters

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    Aggregate closed 15m rows into a session-relative grid.
    
        Binance's standard 15m candles are UTC aligned, while COMEX opens at :20.  A bar's midpoint identifies the
        session-relative bucket; every bucket must have a source bar, otherwise the result is rejected as incomplete.
        This preserves a deterministic partial-edge convention without inventing candles across a data gap.
        

Исправленный докстринг:

    Aggregates closed 15-minute rows into a session-relative grid and rejects incomplete buckets.

Причина: Kept the data transformation and removed the unsupported exchange-comparison justification.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://github.com/binance/binance-public-data

Утверждения без найденного первоисточника:
- The session-relative midpoint-bucket convention has no identified external primary source.

### DOC-0805 — strategies/classic.py:154 — value_area_event

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    Dalton's 80% rule at the close of a 30-minute period (`cut` = close time of the last 15m candle).

Исправленный докстринг:

    Evaluates the configured session value-area re-entry condition at a 30-minute cut.
    This is a local condition; no external 80% rule is claimed.

Причина: Removed the Dalton label because the exact close-time condition is not established by the checked source.

Удалённые атрибуции/провенанс: Dalton's 80% rule

Внешние URL проверки:
- https://vikingtradinggroup.com/wp-content/uploads/2023/01/Peter_Steidlmayer_Steven_Hawkins-Steidlmayer_on_Markets-EN.pdf

Утверждения без найденного первоисточника:
- The exact 30-minute re-entry condition and threshold are not found in the source.

### DOC-0806 — strategies/classic.py:195 — stretch

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    Crabel's Stretch: the SMA of the last `days` closed days' min(High - Open, Open - Low).

Исправленный докстринг:

    Computes the configured stretch as the moving average of min(High−Open, Open−Low) over closed days.
    No author attribution or performance claim is made.

Причина: The local formula and window are not verified as the cited published method.

Удалённые атрибуции/провенанс: Crabel's Stretch

Внешние URL проверки:
- https://mebfaber.com/2007/09/17/tony-crabel-and-the-secret-orb/

Утверждения без найденного первоисточника:
- The exact formula, window and market application are not verified from a primary Crabel source.

### DOC-0807 — strategies/classic.py:202 — narrow_range

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    Crabel's NR-n: the last closed day's range the smallest of the last n days (None without the history).

Исправленный докстринг:

    Checks whether the last closed day has the smallest range in the configured lookback.
    This is a local narrow-range condition.

Причина: Removed the Crabel name because the exact local NR-n rule and use are not source-verified.

Удалённые атрибуции/провенанс: Crabel's NR-n

Внешние URL проверки:
- https://mebfaber.com/2007/09/17/tony-crabel-and-the-secret-orb/

Утверждения без найденного первоисточника:
- The exact lookback and crypto application are not established by a primary source.

### DOC-0808 — strategies/classic.py:222 — orb_sessions

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    (name, open_ms, close_ms) of the sessions running at now_ms for the coin (weekdays only).

Исправленный докстринг:

    Returns the configured weekday sessions active at the supplied timestamp.

Причина: Removed strategy attribution; this record is a session-calendar lookup.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://github.com/binance/binance-public-data

Утверждения без найденного первоисточника:
- No external source was found for the project's session tuple configuration.

### DOC-0809 — strategies/classic.py:247 — previous_session

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    (open_ms, close_ms) of the same session on the previous weekday (local calendar).

Исправленный докстринг:

    Returns the previous weekday interval for the selected session under the configured local calendar.

Причина: Removed strategy attribution and retained the calendar operation.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://github.com/binance/binance-public-data

Утверждения без найденного первоисточника:
- The local holiday and weekday handling is not externally specified in the record.

### DOC-0810 — strategies/classic.py:265 — session_va_event

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    
        eng-95, Dalton's 80% rule by session (as on a stock exchange: yesterday's regular session's value area, today's
        open of the same session): the session opened outside the previous same session's TPO value area and closed two
        consecutive 30-minute periods (counted from the session's open) back inside it -> the far edge; out at the close.
        

Исправленный докстринг:

    Evaluates whether a session re-enters the prior session's configured value area and returns the
    configured target/exit description. This is a local rule, not a published 80% rule.

Причина: Removed the Dalton/engineering claim; the exact session, TPO and re-entry contract is not in the source.

Удалённые атрибуции/провенанс: Dalton's 80% rule, eng-95

Внешние URL проверки:
- https://vikingtradinggroup.com/wp-content/uploads/2023/01/Peter_Steidlmayer_Steven_Hawkins-Steidlmayer_on_Markets-EN.pdf

Утверждения без найденного первоисточника:
- No primary source was found for the exact session-open, two-period and far-edge conditions.

### DOC-0811 — strategies/classic.py:309 — failed_auction_event

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    
        eng-127, the failed auction (Steidlmayer / Dalton, auction market theory): the session OPENED INSIDE the previous
        same session's TPO value area, probed beyond one edge and did not find acceptance there - acceptance = two
        consecutive 30-minute periods closing beyond (the TPO convention of the 80% rule) - then a 30-minute period closed
        back inside: "price re-enters a previously accepted value range ... the market will auction to the opposite end"
        -> the far edge; the stop beyond the probe's extreme; out at the session's close. (The opening outside value is
        the 80% rule, session_va_event.)
        

Исправленный докстринг:

    Evaluates a configured failed-auction candidate: a probe outside the prior value area followed by
    the configured re-entry condition. The former quotation and named external attribution are removed.

Причина: A local failed-auction predicate cannot be presented as the cited auction-market method without a source for every condition.

Удалённые атрибуции/провенанс: Steidlmayer, Dalton, eng-127

Внешние URL проверки:
- https://vikingtradinggroup.com/wp-content/uploads/2023/01/Peter_Steidlmayer_Steven_Hawkins-Steidlmayer_on_Markets-EN.pdf

Утверждения без найденного первоисточника:
- The exact open-location, probe, close and target conditions are not found in a primary source.

### DOC-0812 — strategies/classic.py:360 — session_orb

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    Crabel's ORB on a running session. audit: Crabel, "Playing the Opening Range Breakout" Part 8 (Stocks &
        Commodities, p. 36) - the opening range of the first minutes (30 seconds to 5 minutes; 5 here), a buy stop the
        Stretch (the 10-day SMA of min(High - Open, Open - Low)) above its high and a sell stop the Stretch below its low;
        the first level TRADED through is the entry (a stop order fills on the touch, at the level or a gap's open), the
        other one the stop. Was: the session's open +- Stretch and a 5m CLOSE beyond (eng-105), another reference and
        moment. `minutes`: final 1m candles; the break is read on them (a minute late at most, the level is the price).
        audit E08: the contract is the CLOSED minute - price_hi / price_lo (the live tick) are accepted for the caller's
        signature and deliberately not read: a stop-entry detected on a candle that closed is a minute late, not instant.

Исправленный докстринг:

    Evaluates the configured session opening-range condition from final one-minute candles.
    The entry, stop and exit are model conventions; this is not a verified reproduction of a published
    opening-range breakout strategy.

Причина: Removed the Crabel/article/page attribution and the implied historical implementation claim.

Удалённые атрибуции/провенанс: Crabel, Playing the Opening Range Breakout, audit/engineering provenance

Внешние URL проверки:
- https://mebfaber.com/2007/09/17/tony-crabel-and-the-secret-orb/

Утверждения без найденного первоисточника:
- No primary source was found for the exact first-minutes, stop-order, touch-fill and session-close rules.

### DOC-0813 — strategies/classic.py:406 — rsi

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    Wilder's RSI of the last close.

Исправленный докстринг:

    Computes the configured RSI value from the latest close. No author attribution is asserted.

Причина: The indicator name alone does not establish fidelity to the named author's complete method.

Удалённые атрибуции/провенанс: Wilder

Внешние URL проверки:
- https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI

Утверждения без найденного первоисточника:
- The smoothing and seed details for this RSI implementation are not documented by an external source here.

### DOC-0814 — strategies/classic.py:423 — connors_event

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    
        Connors on DAILY candles (his system; the 1h version of eng-29's first draft was another system): the day that
        closed with RSI(2) in the extreme (`first=True`: not already there the day before; `first='orig'`: the original
        close-in rule - he is in until the SMA5 exit, and a run of oversold days is one trade).
        

Исправленный докстринг:

    Evaluates the configured daily RSI(2) extreme and moving-average exit conditions.
    This is not described as an original published system.

Причина: The checked RSI(2) source describes a broader rule set; it does not support this exact daily trigger and exit contract.

Удалённые атрибуции/провенанс: Connors, eng-29

Внешние URL проверки:
- https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2

Утверждения без найденного первоисточника:
- The exact trigger, first-event handling and moving-average exit are not established by the source.

### DOC-0815 — strategies/classic_strategies.py:1 — <module>

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    
    Cards of the classic methods in strategies/classic.py: each enters at its signal's close (as its author does), with
    its own stop and target where the method defines one; the lifecycle, R:R rule and journal are shared.
    

Исправленный докстринг:

    Cards for the profile, opening-range and RSI-based strategy components in strategies/classic.py.
    Each uses its configured entry/stop/target contract and shared lifecycle; no published-strategy
    fidelity is claimed.

Причина: Removed the statement that each card enters and exits as its named author does.

Удалённые атрибуции/провенанс: Dalton, Crabel, Connors, author-fidelity claim

Внешние URL проверки:
- https://vikingtradinggroup.com/wp-content/uploads/2023/01/Peter_Steidlmayer_Steven_Hawkins-Steidlmayer_on_Markets-EN.pdf
- https://mebfaber.com/2007/09/17/tony-crabel-and-the-secret-orb/
- https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2

Утверждения без найденного первоисточника:
- No external source establishes the shared lifecycle or configured execution conventions.

### DOC-0816 — strategies/classic_strategies.py:15 — ValueAreaStrategy

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    Dalton's 80% rule: target the value area's far edge, stop beyond the edge price re-entered through.

Исправленный докстринг:

    Uses the configured value-area re-entry target and stop placement.
    This is a local contract, not a source-certified 80% rule.

Причина: Removed Dalton attribution because the exact target and stop rule are not supported by the source.

Удалённые атрибуции/провенанс: Dalton's 80% rule

Внешние URL проверки:
- https://vikingtradinggroup.com/wp-content/uploads/2023/01/Peter_Steidlmayer_Steven_Hawkins-Steidlmayer_on_Markets-EN.pdf

Утверждения без найденного первоисточника:
- The far-edge target and stop-beyond-edge rule are not verified as an original method.

### DOC-0817 — strategies/classic_strategies.py:75 — OrbStrategy

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    eng-93: the session opening range breakout (strategies.classic.session_orb) on the majors, gold, silver and
        oil: the first break of the Asia / London / New York session's first 30 minutes, the stop at the range's middle,
        TP1 the range's width projected, out at that session's close (was Crabel's open +- Stretch on the UTC day).

Исправленный докстринг:

    Uses the configured session opening-range signal, stop, target and session exit.
    This is not presented as an original published opening-range strategy.

Причина: Removed the Crabel/engineering label and retained only the configured contract.

Удалённые атрибуции/провенанс: Crabel, eng-93

Внешние URL проверки:
- https://mebfaber.com/2007/09/17/tony-crabel-and-the-secret-orb/

Утверждения без найденного первоисточника:
- The exact session list, first-break interval, midpoint stop and range-width target lack a primary source.

### DOC-0818 — strategies/classic_strategies.py:152 — ConnorsStrategy

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    Connors' RSI(2): out at the SMA5 with an explicit 2 daily-ATR catastrophe stop.

Исправленный докстринг:

    Uses the configured daily RSI(2), moving-average exit and catastrophe-stop parameters.
    No original-system attribution or optimality claim is made.

Причина: The checked RSI(2) source does not establish this exit and catastrophe-stop combination.

Удалённые атрибуции/провенанс: Connors

Внешние URL проверки:
- https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2

Утверждения без найденного первоисточника:
- The explicit daily ATR stop and SMA5 exit are not found in the source.

### DOC-0819 — strategies/classic_strategies.py:86 — entry_levels

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    Crabel ORB contract: opposite range level is the stop; session close is the exit.

Исправленный докстринг:

    Returns the configured opening-range entry levels, opposite-side stop and session exit.

Причина: Removed the Crabel contract label; level and exit choices are local configuration.

Удалённые атрибуции/провенанс: Crabel ORB contract

Внешние URL проверки:
- https://mebfaber.com/2007/09/17/tony-crabel-and-the-secret-orb/

Утверждения без найденного первоисточника:
- No primary source was found for the opposite-range stop and session-close exit.

### DOC-0820 — strategies/classic_strategies.py:162 — entry_levels

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    Connors contract: the SMA5 is the method exit and the 2 daily-ATR stop is real protection.

Исправленный докстринг:

    Returns the configured RSI(2) exit and protection levels.

Причина: Removed the Connors contract label; the exact exit/protection combination is not source-verified.

Удалённые атрибуции/провенанс: Connors contract

Внешние URL проверки:
- https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2

Утверждения без найденного первоисточника:
- The SMA5 exit and daily ATR stop combination is not established by the source.

### DOC-0821 — strategies/confirm.py:1 — <module>

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    
    Entry confirmations: independent evidence, measured at the entry, that the market backs the trade. The trigger itself
    (a structure shift with agreeing taker flow, an accepted breakout, a confirmed phase) is the entry; these are the
    readings order-flow traders check before taking it, each recorded for every entry (journal `confirms`):
    
    - flow       futures taker delta since the extreme (at most the last hour) agrees with the trade;
    - spot       spot taker delta over the same window agrees: real buying / selling of the coin, not only leverage
                 (spot-led moves hold, perp-led ones get squeezed); 'n/a' for a coin without a spot pair;
    - oi         open interest over the last hour (OI-weighted across venues when >= 2 report, else Binance): RISING for
                 continuations (trend, momentum, breakout: new positions back the move - price and OI together), FALLING
                 for sweeps and cascade exhaustion (the stops / liquidations were flushed); 'n/a' for Wyckoff (its phases
                 score OI themselves) and absorption (absorbed market orders open positions on both sides);
    - orderflow  at the extreme: stacked footprint imbalances, absorption (a heavy 1m delta against the trade that barely
                 moved price), a finished auction (the footprint's extreme price traded only by the side that was pushing:
                 nobody left to trade there, ATAS / Market Profile) or, for reversals, a CVD divergence (price made a new
                 extreme beyond the previous swing, cumulative delta did not: the aggressive side is exhausted); False
                 when none of them happened;
    - vsa        Volume Spread Analysis on the 5m bars since the extreme (strategies/vsa.py, Tom Williams): no supply /
                 stopping volume / reverse upthrust for longs, no demand / buying climax / upthrust for shorts.
    
    Keys starting with '_' are metadata ('_window' = [since, until, extreme] ms, set by fetcher.confirmations), not readings.
    Values: True / False, the order-flow kind (a string = present), NA ('n/a') where the reading cannot exist for this
    coin / strategy. The inputs (1m candles of futures and spot, OI) are seeded from REST at start-up, so a reading is
    never missing after a restart; if one still is (a REST failure), it is None and never vetoes.
    Which confirmations an entry needs: CONFIG.orderflow.required_confirmations (by rule: a breakout needs rising OI,
    like the D / F phases and directional impulses) plus those PROMOTED by the journal once entries without them show a
    negative Edge (journal.refresh_confirm_stats). The rest are recorded and shown until stats.py proves them.
    

Исправленный докстринг:

    Records configured entry-confirmation readings (flow, spot, OI, order-flow and volume/spread
    conditions). The readings are not assumed independent, and their predictive value, source
    fidelity and promotion rules are not established by this docstring.

Причина: Removed claims of independent evidence, causal spot/perpetual behavior and automatic journal validation.

Удалённые атрибуции/провенанс: independent evidence, Tom Williams/VSA, owner/audit promotion claims, Wyckoff phase attribution

Внешние URL проверки:
- https://arxiv.org/abs/1011.6402
- https://www.cmegroup.com/education/courses/introduction-to-futures/open-interest.html
- https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial

Утверждения без найденного первоисточника:
- No external experiment was found that validates the combined confirmation set or its promotion rule.

### DOC-0822 — strategies/confirm.py:53 — positive

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    A confirmation that is present (True or an order-flow kind), not 'n/a' / False / None.

Исправленный докстринг:

    Returns whether a confirmation value is present under the configured missing/NA convention.

Причина: Kept the boolean presence operation and removed the claim that presence is evidence of trade validity.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1011.6402

Утверждения без найденного первоисточника:
- The predictive value of a present confirmation is not established.

### DOC-0823 — strategies/confirm.py:58 — required

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    Confirmations an entry of `strategy` needs.

Исправленный докстринг:

    Returns the confirmation names configured for a strategy.

Причина: Kept configuration lookup; no claim that the selected confirmations are statistically required.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1011.6402

Утверждения без найденного первоисточника:
- No external source establishes the required confirmation set.

### DOC-0824 — strategies/confirm.py:68 — required_names

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    Every confirmation name some strategy may require (configured, order flow, journal-promoted).

Исправленный докстринг:

    Returns the union of configured and promoted confirmation names.
    Promotion is a project rule; no statistical proof is claimed.

Причина: Removed unsupported journal-promotion justification.

Удалённые атрибуции/провенанс: audit/promoted confirmation provenance

Внешние URL проверки:
- https://arxiv.org/abs/1011.6402

Утверждения без найденного первоисточника:
- No primary experiment was found for promotion thresholds or incremental predictive value.

### DOC-0825 — strategies/confirm.py:90 — missing

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    The veto reason of the first required confirmation that is negative ('no_<name>').

Исправленный докстринг:

    Returns the first missing required confirmation reason under the configured veto convention.

Причина: Kept the veto reason and removed any implication that a missing confirmation proves a negative trade.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1011.6402

Утверждения без найденного первоисточника:
- No external source establishes the veto's trading benefit.

### DOC-0826 — strategies/confirm.py:113 — delta

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    Taker delta (buy - sell quote) of the 1m candles opened in [since_ms, until_ms); 0 without trades.

Исправленный докстринг:

    Computes taker buy-minus-sell quote delta for the supplied minute window.

Причина: Kept the observable aggregation and removed any interpretation as net participant intent.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1011.6402

Утверждения без найденного первоисточника:
- Trade delta alone does not identify passive liquidity or participant direction.

### DOC-0827 — strategies/confirm.py:118 — covered_delta

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    eng-169d (audit P2: missing data is not a negative reading): the taker delta of [since_ms, until_ms) when the 1m
        candles cover it - at least one candle in the window and the last one opened at most 3 minutes before until_ms
        (the oi_change rule); None otherwise. delta() of a stalled / empty stream was 0 -> 'flow' / 'spot' False, journaled
        as an absent confirmation, counted by the promotion of required confirmations and by min_confirmations.

Исправленный докстринг:

    Returns delta only when the supplied minute window is covered by recent data; otherwise returns
    no reading. Missing data are not recoded as a negative confirmation.

Причина: Removed the audit identifier; the missing-data behavior is stated directly.

Удалённые атрибуции/провенанс: eng-169d, audit P2

Внешние URL проверки:
- https://arxiv.org/abs/1011.6402

Утверждения без найденного первоисточника:
- No external source was found for the project's coverage threshold.

### DOC-0828 — strategies/confirm.py:129 — oi_change

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    
        Relative OI change from the first sample at / after since_ms to the last at / before until_ms (a listing younger
        than the window: over its available history, at least 5 minutes). None without two such samples.
        

Исправленный докстринг:

    Computes relative OI change between the first and last available samples in the supplied window;
    no directional position inference is claimed.

Причина: Kept the calculation and removed the implication that OI change identifies new longs, shorts or stops.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://www.cmegroup.com/education/courses/introduction-to-futures/open-interest.html

Утверждения без найденного первоисточника:
- The lookback, minimum-history and missing-listing rules are project parameters without an external source.

### DOC-0829 — strategies/confirm.py:141 — cvd_divergence

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    
        Price made its extreme beyond the previous swing of the lookback while cumulative delta did not (long: a lower
        low on a higher CVD low). The previous swing = the most extreme candle closing at least 5 minutes before the
        extreme's candle. False when there is no such swing (nothing to diverge from).
        

Исправленный докстринг:

    Flags a configured price/CVD divergence condition. It is a descriptive pattern, not proof of
    exhaustion or participant intent.

Причина: Separated the observed price/CVD relation from unsupported causal interpretation.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1011.6402

Утверждения без найденного первоисточника:
- No external source was found for the exact swing lookback and divergence thresholds.

### DOC-0830 — strategies/confirm.py:164 — evaluate

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    
        All confirmations of one entry (see the module docstring). `spot_minutes` None = the coin has no spot pair;
        `oi` = the relative OI change over the last hour.
        

Исправленный докстринг:

    Evaluates the configured confirmation set for one entry.

Причина: Removed module-level claims that the set is independent or validated.

Удалённые атрибуции/провенанс: independent evidence, validated confirmation claim

Внешние URL проверки:
- https://arxiv.org/abs/1011.6402
- https://www.cmegroup.com/education/courses/introduction-to-futures/open-interest.html

Утверждения без найденного первоисточника:
- No independent out-of-sample validation of the combined set was found.

### DOC-0831 — strategies/cup_handle.py:1 — <module>

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    
    Cup with handle (William O'Neil, "How to Make Money in Stocks"; statistics: Thomas Bulkowski, "Encyclopedia of Chart
    Patterns"), on DAILY candles at the UTC day's close (eng-58; was 1h / 4h):
    
    - a prior advance of >= 30% into the left rim (the lowest low of the 2x cup-length before it to the rim);
    - the cup: 12-33% deep (O'Neil; eng-58, was up to 50%), 49..420 daily candles (7 .. 60 calendar weeks in the retained 898-bar window);
    - the handle after the right rim: 7 .. 56 calendar days, drifting in the cup's UPPER half and no deeper than 12% of the
      rim, on lower volume than the cup's;
    - the entry: the first close above the handle's high (the pivot) on >= 1.4x the average volume (O'Neil: +40-50%).
    - stop below the handle's low; TP1 the pivot + 61% of the depth, TP2 + the full depth (Bulkowski's measure rule); O'Neil's own rule
      (cut losses at 7-8%, take 20-25%) is an exit rule, not an entry filter: the stop is the nearer of the handle's low
      and 8% below the entry, the minimum R:R to the measured target is 1.
    

Исправленный докстринг:

    Daily cup-and-handle candidate detector with configured depth, duration, volume, breakout, stop
    and target conditions. The numerical thresholds are project parameters; no published-pattern fidelity, scientific basis or performance is claimed.

Причина: Broad cup-and-handle descriptions do not establish exact local thresholds or execution contract.

Удалённые атрибуции/провенанс: William O'Neil, Thomas Bulkowski, eng-58, research/statistics claim

Внешние URL проверки:
- https://www.thepatternsite.com/cup.html
- https://get.investors.com/wp-content/uploads/2024/08/IBDD-How-to-buy-Stocks-infographic.pdf

Утверждения без найденного первоисточника:
- No primary source was found for the exact depth, duration, volume, stop and measured-target thresholds.

### DOC-0832 — strategies/cup_handle.py:31 — cup_handle

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    The breakout of a cup with handle on the candle that just closed ([ts, o, h, l, c, quote_vol]), else None.

Исправленный докстринг:

    Returns a cup-and-handle breakout candidate on the just-closed candle when the configured
    conditions are met.

Причина: Removed pattern attribution from the operational detector; it does not prove the published pattern definition.

Удалённые атрибуции/провенанс: cup-and-handle source fidelity

Внешние URL проверки:
- https://www.thepatternsite.com/cup.html
- https://get.investors.com/wp-content/uploads/2024/08/IBDD-How-to-buy-Stocks-infographic.pdf

Утверждения без найденного первоисточника:
- The exact local breakout and candle conditions are not source-verified.

### DOC-0833 — strategies/cup_handle.py:107 — CupHandleStrategy

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    O'Neil's cup with handle: entry at the breakout close, stop below the handle, target the measured move.

Исправленный докстринг:

    Represents the configured cup-and-handle candidate contract: breakout reference, stop and
    measured target. It is not described as an original published strategy.

Причина: The local entry/stop/target contract is not the same as a source-defined strategy.

Удалённые атрибуции/провенанс: O'Neil's cup with handle

Внешние URL проверки:
- https://www.thepatternsite.com/cup.html
- https://get.investors.com/wp-content/uploads/2024/08/IBDD-How-to-buy-Stocks-infographic.pdf

Утверждения без найденного первоисточника:
- No primary source was found for the local stop and measured-target implementation.

### DOC-0834 — strategies/cup_handle.py:115 — entry_levels

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    O'Neil/Bulkowski contract: 8%/handle stop and measured cup targets.

Исправленный докстринг:

    Returns the configured cup/handle entry, stop and target levels.
    No external contract or parameter provenance is claimed.

Причина: Removed O'Neil/Bulkowski contract label and unsupported 8%/measured-target provenance.

Удалённые атрибуции/провенанс: O'Neil, Bulkowski

Внешние URL проверки:
- https://www.thepatternsite.com/cup.html
- https://get.investors.com/wp-content/uploads/2024/08/IBDD-How-to-buy-Stocks-infographic.pdf

Утверждения без найденного первоисточника:
- The 8% stop and exact measured-target rules are not established by the checked sources.

### DOC-0835 — strategies/detect.py:1 — <module>

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    
    Loop-side detection of the event strategies. The coins' contexts (structure.Context) arrive from the maps worker
    after each 15m close carrying that candle's events (sweeps, accepted breakouts); every scan this class
    - releases those events once (a context rebuilt for the same candle does not fire it again),
    - checks absorption on each new final 1m candle at the coin's significant levels,
    - follows liquidation cascades until their leg is big enough (cascade.CascadeTracker).
    It returns setup dicts that the scanner turns into signals (the coin's live Tier-0 metrics + the setup's anchor).
    

Исправленный докстринг:

    Coordinates loop-side event detectors and returns setup records for the scanner. Event names are
    project labels; no claim of validated liquidation, absorption or sweep detection is made.

Причина: Removed the implication that named event labels are independently detected market facts.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1011.6402
- https://github.com/binance/binance-public-data

Утверждения без найденного первоисточника:
- No external validation was found for the combined event detector.

### DOC-0836 — strategies/detect.py:40 — state

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    Fired close events [(symbol, setup, event_ts, fired_at)] of the last day (kept across restarts).

Исправленный докстринг:

    Stores fired close events for the configured retention window.

Причина: Kept persistence behavior and removed any implication that the stored event is a proven market event.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://github.com/binance/binance-public-data

Утверждения без найденного первоисточника:
- The retention window is a local storage choice.

### DOC-0837 — strategies/detect.py:55 — wants

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    Anything to look at this scan: pending close events, a new final minute, a running / new cascade.

Исправленный докстринг:

    Returns objects eligible for inspection on the current scan.

Причина: Replaced broad event interpretation with the local selection operation.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://github.com/binance/binance-public-data

Утверждения без найденного первоисточника:
- No external source establishes the eligibility policy.

### DOC-0838 — strategies/detect.py:66 — scan

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    `minutes`: FINAL 1m futures candles [open_time, o, h, l, c, quote_vol, taker_buy_quote].

Исправленный докстринг:

    Accepts final one-minute futures candles for event processing.

Причина: Kept the input contract and removed any claim that minute candles reconstruct order-flow events.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://github.com/binance/binance-public-data

Утверждения без найденного первоисточника:
- Historical microstructure and queue information are not supplied by this input alone.

### DOC-0839 — strategies/geometry.py:1 — <module>

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    
    Geometry shared by every strategy: the stop floor, the stop pushed beyond a stop pool, targets picked from the coin's
    level map by the strategy's INTENT, the entry levels and R:R, and the R:R cap of a waiting zone.
    
    Target intents (the strategy says what it trades toward; Fibonacci only where a real leg exists):
    - 'extension'          continuation: strong zones beyond the leg's end, the leg's extensions fill empty slots;
    - 'opposite_liquidity' a sweep: the nearest resting-stop pools on the other side first;
    - 'mean'               absorption / exhaustion / climaxes: VWAP, POC, value area, volume nodes first;
    - 'range'              a trading range's far side first;
    - 'measured'           a breakout: strong zones beyond the edge, measured moves of the range fill empty slots.
    A target is always >= zones.min_target_atr beyond its reference (and beyond the previous target); slots still empty are
    1-ATR steps ('ATR step'), never copies of one level.
    

Исправленный докстринг:

    Shared entry/stop/target geometry for strategy plans. Intent labels and fallback ATR steps are
    configured calculations, not published trading methodologies or evidence of edge.

Причина: Removed the claim that shared geometry is a proven strategy layer and kept its calculation scope.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No external source establishes intent labels, target selection or ATR fallback parameters.

### DOC-0840 — strategies/geometry.py:24 — cost_of

Статус: REMOVED_UNSUPPORTED_PARAMETERS

Исходный докстринг:

    
        (volume_24h: the coin's; the slippage then grows as liquidity falls, levels.slippage_bps - the same model the
        journal's replay fills with, so an entry that passes R:R here is not a loser there by construction)
        Execution cost of a round trip in price units: the taker fees (0.05% a side at Binance VIP0) plus the slippage of
        a market entry and of a stop exit (levels.slippage_bps each). Fees alone made a 1-ATR stop on a quiet coin look
        ~0.3R cheaper than it trades.
        

Исправленный докстринг:

    Computes configured round-trip execution cost from fees and slippage inputs. The value is a model
    assumption, not a guarantee of realized venue cost.

Причина: Removed the unverified Binance VIP0 and liquidity-performance claim.

Удалённые атрибуции/провенанс: Binance VIP0 cost claim

Внешние URL проверки:
- https://www.binance.com/en/fee/trading

Утверждения без найденного первоисточника:
- The exact fee tier, slippage curve and realized-cost equivalence are not established for every trade.

### DOC-0841 — strategies/geometry.py:39 — stop_pierce

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    
        eng-124: no source names the pierce quantile of a stop's buffer (p50 / p80 / p90) - the stop's level kind and its
        three measured quantiles (% of price) are journaled with each entry; with the row's sl / mae_4h / mfe_4h they show
        which buffer the stopped trades would have survived, to choose the quantile on live trades.
        

Исправленный докстринг:

    Records configured or observed stop-buffer measurements when available. No source-defined pierce
    quantile or optimal live quantile is claimed.

Причина: Removed eng-124, audit statement and implied p50/p80/p90 decision rule.

Удалённые атрибуции/провенанс: eng-124, audit claim, source-defined stop-pierce quantiles

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No external source was found for the pierce quantiles or their use in live selection.

### DOC-0842 — strategies/geometry.py:57 — kind_at

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    The measured kind of the map zone a stop base sits on (the zone's own kinds, not its text label).

Исправленный докстринг:

    Returns the level kinds associated with a zone used as a stop base.

Причина: Kept the structured-zone lookup and removed any implied methodological meaning.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- The project's level-kind taxonomy has no external primary source.

### DOC-0843 — strategies/geometry.py:67 — kind_of_label

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    The level kind behind a stop's source label (for its measured buffer).

Исправленный докстринг:

    Maps a stop-source label to its configured level kind.

Причина: Kept the label mapping only.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- The source-label taxonomy is project-specific and not externally defined.

### DOC-0844 — strategies/geometry.py:79 — stop_too_far

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    eng-91: a stop farther than levels.max_stop_pct from the entry is no trade (the 1.5 ATR(4h) pad of a coin whose 4h
        ATR a pump inflated put W's stop 48% away, PONS' 18% - live). Systems whose wide stop IS the method (the Turtles' 2N,
        Connors) are exempt.

Исправленный докстринг:

    Tests whether a stop exceeds the configured maximum distance. Exemptions are local configuration;
    no named-system fidelity is claimed.

Причина: Removed eng-91, live examples and Turtle/Connors exemption claims; these do not validate the rule.

Удалённые атрибуции/провенанс: eng-91, live trade examples, Turtles, Connors

Внешние URL проверки:
- https://oxfordstrat.com/coasdfASD32/uploads/2016/01/turtle-rules.pdf
- https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2

Утверждения без найденного первоисточника:
- The maximum-stop percentage, ATR pad and exemptions have no source-verified provenance.

### DOC-0845 — strategies/geometry.py:90 — stop_floor

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    Minimum stop distance: min_stop_atr x the larger of ATR14 and the last hour's ATR (ATR14 lags a waking market).

Исправленный докстринг:

    Returns the configured minimum stop distance from the relevant ATR values.

Причина: Kept the calculation and removed the implied universal stop principle.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- The selected ATR combination and minimum multiplier are local parameters.

### DOC-0846 — strategies/geometry.py:99 — _target_in_zones

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    Whether a persisted target is actually represented by an allowed timeframe zone.

Исправленный докстринг:

    Checks whether a persisted target is represented by an allowed timeframe zone.

Причина: Kept persisted-zone validation operation.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- The allowed-timeframe policy is not externally specified.

### DOC-0847 — strategies/geometry.py:119 — _kind_rank

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    One level kind's timeframe rank (see _zone_rank); None = valid on every timeframe.

Исправленный докстринг:

    Returns the configured timeframe rank for a level kind.

Причина: Kept the taxonomy lookup.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- The ranking of level kinds is project-specific.

### DOC-0848 — strategies/geometry.py:129 — _zone_rank

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    The highest timeframe rank among the zone's kinds (swing_15m, fvg_1h, ob_4h ...); None = valid on every
        timeframe (it holds a daily-or-longer untimed reference: previous day / week / month, the year, an open, a completed
        day's profile, a range); intraday untimed kinds (VWAP, round, book, liquidations, equal highs / lows, profile nodes)
        rank as 15m. A plan may target the zone when this rank >= its own timeframe's.

Исправленный докстринг:

    Returns the highest configured timeframe rank among a zone's kinds.

Причина: Kept rank aggregation and removed implication that timeframe rank is a published market concept.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- The level-kind rank mapping is not externally defined.

### DOC-0849 — strategies/geometry.py:143 — _trim

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    audit D05: the zone as a plan of timeframe rank `rank` sees it - the edges of its own levels only. A lower
        timeframe's level merged into a 1h swing's zone moved the 1h target (130.1 -> 129.9, R:R 3.01 -> 2.99).

Исправленный докстринг:

    Trims a merged zone to levels that qualify for the requested timeframe rank. No audit result or
    performance effect is asserted.

Причина: Removed audit D05, example prices and implied R:R effect.

Удалённые атрибуции/провенанс: audit D05, historical target/R:R example

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No independent experiment was found for the effect of the trimming rule.

### DOC-0850 — strategies/geometry.py:156 — htf_zones

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    The zones a plan of timeframe `tf` may target: its own timeframe and higher (2026-10-05, the owner: a 1h / 4h
        trade's TP1 was the nearest 15m swing / FVG, cutting the R:R of a stop now sized in the structure's ATR). A merged
        zone is cut back to the edges of the levels that qualify.

Исправленный докстринг:

    Returns zones eligible for a plan's timeframe under the configured rank rule. No owner decision or
    source methodology is asserted.

Причина: Removed owner/date claim and asserted trade-level target decision.

Удалённые атрибуции/провенанс: owner statement, 2026-10-05 provenance

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No primary evidence was found for the claimed trade decision or target policy.

### DOC-0851 — strategies/geometry.py:173 — map_fill

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    
        Fill the empty target slots (up to 3) with the nearest map zones beyond the last target, ANY strength (a single
        swing, a session high, an FVG, an order block): a level on the chart before an ATR step (the steps sat in empty
        space while levels stood right there, 2026-10-01: TP2 / TP3 were ATR steps on 18 / 21 of 35 entries).
        

Исправленный докстринг:

    Fills empty target slots, up to three, with the nearest map zones beyond the last target; any
    qualifying zone may be used before the configured synthetic fallback.

Причина: Removed audit count and kept target-fill behavior.

Удалённые атрибуции/провенанс: audit 2026-10-01, 18/21 of 35 entries

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- The claimed audit frequency and any performance effect were not independently sourced.

### DOC-0852 — strategies/geometry.py:192 — is_synthetic

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    A target that is no price level: an ATR step, an R multiple, a placeholder ('none: ...').

Исправленный докстринг:

    Identifies a target represented by a synthetic step, R multiple or placeholder rather than a mapped
    price level.

Причина: Kept label classification.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- The synthetic-target taxonomy is project-specific.

### DOC-0853 — strategies/geometry.py:206 — setup_key

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    HIT_RATE's key: the setup without the journal's 'ENTRY ' prefix (audit C13).

Исправленный докстринг:

    Builds the normalized setup key used to group journal statistics. No hit-rate validation is implied.

Причина: Removed audit C13 and implied validation of grouping key.

Удалённые атрибуции/провенанс: audit C13

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No independent source was found for setup-key grouping or statistical validity.

### DOC-0854 — strategies/geometry.py:212 — finish_levels

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    
        Entry / stop / three targets and the R:R checks, the same for every path (eng-41):
        - a LEVEL target sits in front of its level by the level kind's typical pierce (p50): price often turns before
          the level, and the replay counts a target only once traded through it - the old target on the level overstated
          R:R by about that pierce;
        - R:R is measured on the level targets only (an ATR step / an R multiple / a placeholder passes any threshold by
          construction - SMT's '2.5 R' targets: 2 of 44 reached); ATR steps count where the map holds nothing beyond the
          entry at all (price discovery - the owner's rule);
        - the R:R that decides is the BLENDED one of the actual exit (a third at each target; a missing level slot exits
          at the last level);
        - risk must be >= cost_guard x the round-trip execution cost (audit F09: the text said 3x / 'a third of the
          risk'; the rule is CONFIG.levels.cost_guard, 1 since eng-108 - the risk at least pays one round trip)
        - with a journal-measured p(TP_k before the stop) for the setup the entry must have a positive expectancy of its
          three thirds, sum_k (p_k x R:R_k - (1 - p_k)) / 3 at the upper ends of the shrinkage intervals; the method's
          minimum R:R (Strategy.min_rr, else the global one) holds as well.
        

Исправленный докстринг:

    Builds entry, stop, target and configured risk/reward/cost checks. Calculated expectancy is a model
    output; no measured edge, owner rule or audit result is asserted.

Причина: Removed eng-41, owner rules, historical examples, SMT counts, cost-guard audit and shrinkage claim.

Удалённые атрибуции/провенанс: eng-41, owner rule, historical trade examples, SMT 2/44 claim, audit F09, expectancy proof

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558
- https://arxiv.org/abs/1011.6402

Утверждения без найденного первоисточника:
- No primary evidence was found for pierce p50, historical R values, SMT count or expectancy interpretation.

### DOC-0855 — strategies/geometry.py:428 — obstacle_before

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    audit 2026-10-18 P2 #7, a diagnostic (journaled, never a filter): the nearest strong map zone the price meets
        between the entry and TP1 - (its near edge in R from the entry, its label). A method's own objective (a range's far
        side, an extension) skips the map on purpose; this shows what stands in the way, not that the target is wrong.

Исправленный докстринг:

    Reports the nearest intervening map zone between entry and the first target as a diagnostic. It is
    not a filter and does not establish that the target is wrong.

Причина: Removed audit identifier and retained explicitly diagnostic role.

Удалённые атрибуции/провенанс: audit 2026-10-18 P2 #7

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No independent source was found for the claimed diagnostic's interpretation.

### DOC-0856 — strategies/geometry.py:443 — _cost_reason

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    The cost guard's veto as the rule actually stands (CONFIG.levels.cost_guard x the round-trip cost).

Исправленный докстринг:

    Returns the reason for a cost-guard decision under the configured rule.

Причина: Kept decision explanation.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://www.binance.com/en/fee/trading

Утверждения без найденного первоисточника:
- The configured cost-guard threshold is not externally established.

### DOC-0857 — strategies/geometry.py:449 — _min_rr

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    The plan's minimum R:R to TP1: its method's own (Strategy.min_rr, from the source) else the global rule.

Исправленный докстринг:

    Returns the configured minimum risk/reward ratio to TP1.

Причина: Removed statement that a source-defined strategy supplies the value.

Удалённые атрибуции/провенанс: source-defined Strategy.min_rr claim

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- The minimum ratio and method-specific provenance are not identified.

### DOC-0858 — strategies/geometry.py:458 — _liq_price

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    The nearest untaken liquidity extreme of the zone in the trade's direction (its levels' own prices: a swing's
        wick, not the body edge the S/R zone starts from); the zone's near edge when it carries no liquidity part.

Исправленный докстринг:

    Returns the nearest untaken liquidity extreme of the zone in the trade direction.

Причина: Kept level selection without treating the level as guaranteed resting liquidity.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1011.6402

Утверждения без найденного первоисточника:
- The interpretation of the selected extreme as actual resting liquidity is not established.

### DOC-0859 — strategies/geometry.py:467 — select_targets

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    
        Up to three targets beyond `ref` in the trade's direction by the strategy's intent; `first` forces a primary
        objective (a range's far side) into the candidates. Returns (prices, labels).
        

Исправленный докстринг:

    Selects up to three target candidates beyond a reference in the strategy's configured direction;
    the configured primary objective may be forced into the candidate set.

Причина: Kept candidate selection without implying a validated target method.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- Intent ranking and target selection have no external primary source.

### DOC-0860 — strategies/geometry.py:570 — zone_pad

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    The buffer beyond the stop's structure: the larger of the measured pierce of the level and
        zone_buffer_atr x the ATR of the structure's own timeframe (Seiden-style: 1-2 ATR of the zone's timeframe beyond
        its distal line; the owner: beyond the zone with a 3-5% margin - on alts' 4h that is ~1.5 ATR). eng-69.

Исправленный докстринг:

    Computes a stop buffer from configured measured penetration and ATR inputs. No named-source rule,
    owner margin or source-based optimality is claimed.

Причина: Removed Sam Seiden and owner attributions; exact 1–2 ATR and margin parameters are not source-verified.

Удалённые атрибуции/провенанс: Sam Seiden, owner margin, eng-69

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No primary source was found for the stated ATR range, margin or parameter choice.

### DOC-0861 — strategies/geometry.py:586 — capped_pad

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    eng-147: the buffer beyond a stop's structure. Moved past a pool / swing by stop_beyond: only moved_pad_atr x
        the working ATR (the stop sits at the pool's far edge; a deep raid of the pool itself can still reach it). Else the measured pierce, capped at pierce_cap_atr x
        the working ATR.

Исправленный докстринг:

    Computes the configured stop buffer after pool and penetration caps.

Причина: Removed eng-147 and implied validated cap rule.

Удалённые атрибуции/провенанс: eng-147

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- The cap, moved-pad and penetration thresholds are not externally sourced.

### DOC-0862 — strategies/geometry.py:600 — stop_levels

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    
        The stop: beyond the strategy's reference (the anchor's extreme / the range middle / the trigger's swing) and a
        stop pool just behind it, then the ATR buffer, never closer than the stop floor.
        

Исправленный докстринг:

    Builds a stop from configured structure, pool, ATR and floor rules.

Причина: Kept calculation components without asserting a published strategy.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- Ordering and multipliers of stop components are project-specific.

### DOC-0863 — strategies/geometry.py:645 — exit_stop

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    A system's own stop rule (plan['exit']['stop']): ['pct', f] / ['atr', k] / ['ref', pad ATR] / ['price', p].

Исправленный докстринг:

    Returns the plan's configured stop specification.

Причина: Kept plan lookup.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No external source is needed for the local plan schema; no method claim is made.

### DOC-0864 — strategies/geometry.py:660 — exit_target

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    
        A system's own first target (plan['exit']['tp']): ['pct', f] / ['rr', r] / ['level', price, min R:R, fallback R]
        (the level when it pays min R:R, else the system skips - `low` True; no level -> fallback R) / ['map', min R:R]
        (the map's TP1). Returns (price, label, below the system's minimum R:R).
        

Исправленный докстринг:

    Returns the plan's configured first-target specification and whether its risk/reward check fails.

Причина: Kept plan lookup and risk/reward check without an edge claim.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- Configured fallback and minimum ratio are not externally established.

### DOC-0865 — strategies/geometry.py:701 — structure_stop

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    
        Stop beyond the nearest price-action structure on the stop side (swings, equal highs / lows, previous day / week /
        sessions, range edges, round numbers, book bands) that leaves at least `floor` of risk, pushed beyond a stop pool
        right behind it, plus the ATR buffer. None when no such structure lies within max_stop_atr ATR (price discovery:
        then the fixed rule is all there is).
        

Исправленный докстринг:

    Finds a qualifying configured price structure on the stop side and applies the configured pool,
    ATR and maximum-distance rules.

Причина: Kept selection behavior and removed implication that structures guarantee a stop.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- Structure taxonomy and distance thresholds are project-specific.

### DOC-0866 — strategies/geometry.py:742 — clear_pool

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    eng-84: a system's fixed-price stop (AUCTION's test, a trendline pivot, Connors' 3 ATR) went straight to the
        exchange, never checked against the map: SKY's sat 0.24% beyond the 1h low - inside that pool's usual pierce, and
        the raid of the low took it (liquidated longs printed below). A resting-stop pool between the stop and the entry
        whose usual pierce (p90) reaches the stop moves the stop beyond the pool's pierce.

Исправленный докстринг:

    Moves a fixed-price stop beyond an intervening configured stop pool when the configured penetration
    test requires it. No live example, liquidation inference or named-strategy rule is asserted.

Причина: Removed eng-84, named strategy examples and claims that printed liquidation levels validate the rule.

Удалённые атрибуции/провенанс: eng-84, AUCTION/SKY/PONS/Connors examples, liquidation inference

Внешние URL проверки:
- https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2
- https://arxiv.org/abs/1011.6402

Утверждения без найденного первоисточника:
- The example trades, p90 rule and identification of a liquidation pool have no primary evidence.

### DOC-0867 — strategies/geometry.py:767 — system_levels

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    
        Entry / stop / targets of the ported systems (strategies/maniac.py). Their own structural exits (beyond the sweep,
        the impulse's start, a level) are kept. Their FIXED exits (a % or ATR stop, a % or R target) ignore the map: a 1%
        stop on SUI (15m ATR 1.35%) sat inside one candle's noise and was taken before the move (live, 2026-09-30). Those
        are replaced by the map: the stop beyond the nearest structure, the targets at the next levels; the fixed rule is
        only the fallback where the map has nothing (price discovery).
        

Исправленный докстринг:

    Builds levels for configured system plans. Fixed exits are used as configured, with map-based levels
    only where the documented fallback permits; no porting fidelity or live example is claimed.

Причина: Removed claim that systems were ported faithfully and removed live SUI example.

Удалённые атрибуции/провенанс: ported systems claim, live SUI example

Внешние URL проверки:
- https://oxfordstrat.com/coasdfASD32/uploads/2016/01/turtle-rules.pdf
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No primary source was found for fidelity of the ported systems or the claimed live result.

### DOC-0868 — strategies/geometry.py:931 — _ext_label

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    'ext 1.272' for an extension target, '+ <zone>' when a 4h / daily / weekly zone sits within the pierce of it.

Исправленный докстринг:

    Formats an extension target label and an optional nearby higher-timeframe zone label.

Причина: Kept formatting operation.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No external source establishes the extension labeling convention.

### DOC-0869 — strategies/geometry.py:946 — entry_levels

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    Entry / stop / targets for an entry at `entry` (targets behind the entry are dropped, refilled beyond it).

Исправленный докстринг:

    Builds entry, stop and target levels for an entry at the supplied price, dropping targets behind
    the entry and refilling beyond it as configured.

Причина: Kept local level construction.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- Refill and target ordering policy is project-specific.

### DOC-0870 — strategies/geometry.py:1019 — cap_for_rr

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    
        The furthest entry (from the extreme toward TP1) that still pays min_rr_tp1 (net of fees) to TP1 with the stop at `stop_est`
        or the stop floor, whichever is wider: a waiting zone ends there.
        

Исправленный докстринг:

    Returns the furthest entry from the extreme toward TP1 that still satisfies the configured minimum
    risk/reward after modeled costs, using the wider of the estimated stop and stop floor.

Причина: Kept calculation and stated modeled-cost assumption without an optimality claim.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://www.binance.com/en/fee/trading
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- Minimum ratio, cost model and use of furthest feasible entry have no external validation.

### DOC-0871 — strategies/ict.py:1 — <module>

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    
    ICT / SMC readings of a plan (hypotheses, measured by the journal - never proven edges; Osler's NY Fed SR150 backs only
    the stop clustering beyond round numbers / levels):
    
    - protected swing: the last 15m pivot on the stop side that produced a break of structure (a later close beyond the
      opposite pivot before it). While it holds, the idea holds: the stop goes beyond it, not right behind an obvious
      unswept pool (equal lows, the day's low: the stops a raid takes before the move).
    - premium / discount: where the entry sits in the dealing range (the last 48 1h candles' high - low), for the trade's
      direction: 0 = the cheapest end (a long at the range low), 1 = the dearest. ICT buys only in discount (< 0.5).
      Journaled as `range_pos`, split in stats.py; a filter only if the journal proves it.
    

Исправленный докстринг:

    Computes configured market-structure readings and a premium/discount position within a dealing
    range. These are project labels and hypotheses; no external attribution is asserted.

Причина: Removed ICT/SMC and Osler provenance because exact combined feature set is not supported by a primary source.

Удалённые атрибуции/провенанс: ICT/SMC, Osler/SR150, eng-51/eng-58

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No primary source was found for protected swing, premium/discount or stop-clustering implementation.

### DOC-0872 — strategies/ict.py:19 — protected_swing

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    The price of the protected swing (the most recent one), None without a break of structure in the window.

Исправленный докстринг:

    Returns the most recent protected-swing price under the configured pivot and structure rule.

Причина: Removed ICT label; a local pivot lookup is not enough to establish ICT market structure.

Удалённые атрибуции/провенанс: ICT protected swing

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No primary source was found for the exact protected-swing rule.

### DOC-0873 — strategies/ict.py:40 — dealing_range

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    
        ICT's dealing range (eng-51): the leg between the latest significant swing low and swing high (1h pivots with k
        candles on each side), equilibrium at its 50%. Was the 48h high / low window - a time box is not ICT's definition.
        Falls back to the window while the 1h history holds no pivot pair.
        

Исправленный докстринг:

    Builds a dealing range from configured pivots, with a window fallback and midpoint equilibrium.
    No external attribution is claimed.

Причина: Removed ICT and engineering attribution; pivot and 48-hour fallback are local parameters.

Удалённые атрибуции/провенанс: ICT's dealing range, eng-51

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- Pivot significance, fallback window and 50% equilibrium use are not source-verified as an original rule.

### DOC-0874 — strategies/ict.py:69 — range_position

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    0 = the cheapest end of the dealing range for this direction, 1 = the dearest (clipped).

Исправленный докстринг:

    Returns the clipped position of price within the configured dealing range for the trade direction.

Причина: Kept normalized range-position calculation.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- Directional clipping convention is project-specific.

### DOC-0875 — strategies/ict.py:79 — fvg_trigger

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    
        ICT entry after a liquidity sweep: displacement (a candle with a body >= half its range in the trade's direction)
        that leaves a fair value gap (long: low[i] > high[i-2]) and shifts structure (a close beyond the highest high /
        lowest low since the sweep, before the displacement); the entry is the first later candle that retraces into the
        gap and closes without closing through it. A close through the gap kills it; the next displacement is searched.
        

Исправленный докстринг:

    Evaluates a configured sweep/displacement/gap/structure-shift trigger. The exact thresholds are
    project rules, not a verified published model.

Причина: The combined displacement, FVG, MSS and retrace conditions are not established by a primary ICT source.

Удалённые атрибуции/провенанс: ICT entry after liquidity sweep

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No primary source was found for body threshold, gap indexing, swing reference or close requirement.

### DOC-0876 — strategies/ict.py:130 — _contiguous

Статус: NARROWED_NO_ATTRIBUTION

Исходный докстринг:

    The run of time-contiguous bars ending at the last one (a gap / MSS across a hole is no structure).

Исправленный докстринг:

    Returns the contiguous bar run ending at the latest bar; time gaps break the run.

Причина: Kept time-contiguity operation.

Удалённые атрибуции/провенанс: нет

Внешние URL проверки:
- https://github.com/binance/binance-public-data

Утверждения без найденного первоисточника:
- Use of contiguity as a structure condition has no external source in the record.

### DOC-0877 — strategies/ict.py:138 — raid_swing

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    The swing the raid came from: the last 3-candle pivot high (long; low for a short) of the bars before the sweep
        at `since_ms` (up to 48 bars back) - the level fvg_setup's structure shift must close beyond. None without one.

Исправленный докстринг:

    Returns the configured pre-sweep pivot used as the structure reference.

Причина: Removed implied ICT structure interpretation; this is a configured pivot lookup.

Удалённые атрибуции/провенанс: ICT raid-swing attribution

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No primary source was found for the three-candle, 48-bar pivot selection rule.

### DOC-0878 — strategies/ict.py:153 — fvg_setup

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    
        ICT's 2022 model after a liquidity sweep at `since_ms` (eng-58): a displacement candle (body >= half its range, in
        the trade's direction) that CLOSES BEYOND THE SWING THE RAID CAME FROM - the last 3-candle swing high (long; low
        for a short) of the bars before the sweep, the market structure shift - and leaves a fair value gap. Returns the
        gap and its consequent encroachment (CE, 50%) for a resting limit; the entry is that limit's fill (touch_trigger),
        not a later candle's close. eng-36..57 took any close above the highest high SINCE the sweep as the shift.
        

Исправленный докстринг:

    Evaluates a configured sweep/displacement/FVG candidate and returns its gap and CE reference.
    Any limit fill is a simulation assumption; this is not claimed as an original published model.

Причина: Local thresholds, CE entry and resting-limit fill are not source-verified as the original ICT model.

Удалённые атрибуции/провенанс: ICT 2022 model, eng-58, historical old-logic claim

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No primary source was found for the exact 2022 model wording, gap conditions or fill rule.

### DOC-0879 — strategies/ict.py:201 — touch_trigger

Статус: EXECUTION_ASSUMPTION_CORRECTED

Исходный докстринг:

    
        Sam Seiden's entry: a resting limit at the fresh zone's PROXIMAL line, filled by the first candle that trades into
        it (at the open if it gapped past the line); the extreme is that candle's wick.
        

Исправленный докстринг:

    Models a limit entry at the configured proximal line when a candle trades into it. A price touch is
    not evidence of actual queue execution; no external attribution is asserted.

Причина: Corrected the touch-to-fill statement and removed the named attribution.

Удалённые атрибуции/провенанс: Sam Seiden

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No primary source was found for the exact proximal-line, gap and candle-touch rule.

### DOC-0880 — strategies/ict.py:218 — touch_confirm

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    
        eng-105, the owner: the touch confirmed by a CLOSE - the first closed trigger candle (since the zone was reached)
        that traded into the zone and closed back beyond its proximal line on the trade's side (a long: low <= zone_hi and
        close > zone_hi; a 'zone' of one price - a CE - the same with that price). The entry is that close; the extreme
        is the lowest low (highest high) since the zone was reached. A close through the zone's far side is no entry.
        

Исправленный докстринг:

    Evaluates a close-confirmed zone touch under the configured rule. Owner and engineering provenance
    are removed; the returned entry is a model reference price.

Причина: Removed owner quote and eng-105 claim, and made the reference-price assumption explicit.

Удалённые атрибуции/провенанс: owner quote, eng-105

Внешние URL проверки:
- https://arxiv.org/abs/1412.5558

Утверждения без найденного первоисточника:
- No primary source was found for confirmation-close and no-through-zone conditions.

### DOC-0881 — strategies/ind_panel.py:1 — <module>

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    
    Classic indicator panel of one coin at one moment (strategies.confirm journals it on every entry as `_ind`; the archive
    study research_indicator_confirms.py uses the same functions): EMA 20 / 50 / 200 and the EMA50 slope (Murphy, Elder),
    RSI 14 (Wilder), MACD 12 / 26 / 9 (Appel), ADX 14 with +DI / -DI (Wilder), stochastic 14 / 3 (Lane), Bollinger %B and
    band width (Bollinger), MFI 14 (Quong & Soudack), OBV (Granville), CCI 20 (Lambert), ATR rank, relative volume.
    `rules(ind, d)` turns them into booleans "the indicator agrees with a trade in direction d"; which of them CONFIRM an
    entry is decided by research/indicator_confirms.md (pre-registered), not by this module.
    

Исправленный докстринг:

    Computes the configured indicator panel (moving averages, RSI, MACD, ADX/DI, stochastic,
    volatility bands, MFI, OBV, CCI, ATR rank and relative volume). Indicator names are descriptive; no
    author fidelity, pre-registration or predictive-confirmation claim is made.

Причина: Removed list of author attributions and unsupported pre-registration/research claim.

Удалённые атрибуции/провенанс: Murphy, Elder, Wilder, Appel, Lane, Bollinger, Quong & Soudack, Granville, Lambert, research_indicator_confirms.py pre-registration

Внешние URL проверки:
- https://bollingerbands.us/help-methods.php
- https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/PSAR

Утверждения без найденного первоисточника:
- No primary source was found for the exact combined panel, parameter set or pre-registration claim.

### DOC-0882 — strategies/ind_panel.py:12 — ema

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    EMA seeded with the SMA of the first n values (TA-Lib / Appel; NaN before). Seeding with x[0] left EMA200 on the
        panel's 499 candles up to 0.4% off (research/talib_check.md). Shorter than n: seeded with x[0] (best effort).

Исправленный докстринг:

    Computes an EMA using the configured seed and period; short histories use the documented fallback.
    No named-method or library-fidelity claim and no research result are asserted.

Причина: Local seed/fallback and cited research result are not established by the named source.

Удалённые атрибуции/провенанс: Appel, TA-Lib fidelity, research/talib_check.md

Внешние URL проверки:
- https://ta-lib.org/functions/ema.html

Утверждения без найденного первоисточника:
- No primary source was found for the exact seed, short-history fallback or claimed 0.4% example.

### DOC-0883 — strategies/ind_panel.py:35 — rma

Статус: REMOVED_FALSE_ATTRIBUTION

Исходный докстринг:

    Wilder's smoothing (RSI, ADX, ATR as their authors define them).

Исправленный докстринг:

    Computes the configured RMA-style smoothing used by the panel. No named-author attribution or strategy claim is asserted.

Причина: Removed Wilder attribution because exact panel use and seed are not documented against a primary source.

Удалённые атрибуции/провенанс: Wilder

Внешние URL проверки:
- https://ta-lib.org/functions/rma.html

Утверждения без найденного первоисточника:
- No primary source was found for the exact smoothing seed and panel interpretation.

### DOC-0884 — strategies/ind_panel.py:56 — rolling_std

Статус: REMOVED_UNSUPPORTED_PROVENANCE

Исходный докстринг:

    Population std of each n-window from the deviations from its own mean (audit F01: sqrt(E[x^2] - E[x]^2)
        cancelled catastrophically at large prices - std 10.5 for 0.0009, false zeros at 1e8).

Исправленный докстринг:

    Computes population standard deviation around each window's own mean. Numerical-stability and audit
    claims are omitted; they require a separate reproducible test.

Причина: Removed audit F01, large-price examples and implied validated numerical-stability claim.

Удалённые атрибуции/провенанс: audit F01, catastrophic-cancellation example

Внешние URL проверки:
- https://numpy.org/doc/stable/reference/generated/numpy.std.html

Утверждения без найденного первоисточника:
- No independent reproducible test was found for the claimed cancellation examples or numerical effect.

## Удалённые ложные атрибуции

- 18/21 of 35 entries — записи: DOC-0851.
- 2026-10-05 provenance — записи: DOC-0850.
- Appel — записи: DOC-0881, DOC-0882.
- AUCTION/SKY/PONS/Connors examples — записи: DOC-0866.
- audit 2026-10-01 — записи: DOC-0851.
- audit 2026-10-18 P2 #7 — записи: DOC-0855.
- audit C13 — записи: DOC-0853.
- audit claim — записи: DOC-0841.
- audit D05 — записи: DOC-0849.
- audit F01 — записи: DOC-0884.
- audit F09 — записи: DOC-0854.
- audit P2 — записи: DOC-0827.
- audit/engineering provenance — записи: DOC-0812.
- audit/promoted confirmation provenance — записи: DOC-0824.
- author-fidelity claim — записи: DOC-0815.
- Binance VIP0 cost claim — записи: DOC-0840.
- Bollinger — записи: DOC-0881.
- Bulkowski — записи: DOC-0834.
- catastrophic-cancellation example — записи: DOC-0884.
- Connors — записи: DOC-0801, DOC-0814, DOC-0815, DOC-0818, DOC-0844.
- Connors contract — записи: DOC-0820.
- Crabel — записи: DOC-0801, DOC-0812, DOC-0815, DOC-0817.
- Crabel ORB contract — записи: DOC-0819.
- Crabel's NR-n — записи: DOC-0807.
- Crabel's Stretch — записи: DOC-0806.
- cup-and-handle source fidelity — записи: DOC-0832.
- Dalton — записи: DOC-0802, DOC-0811, DOC-0815.
- Dalton's 80% rule — записи: DOC-0805, DOC-0810, DOC-0816.
- Dalton/Market Profile — записи: DOC-0801.
- Elder — записи: DOC-0881.
- eng-105 — записи: DOC-0880.
- eng-124 — записи: DOC-0841.
- eng-127 — записи: DOC-0811.
- eng-147 — записи: DOC-0861.
- eng-169d — записи: DOC-0827.
- eng-29 — записи: DOC-0801, DOC-0814.
- eng-29/audit narrative — записи: DOC-0803.
- eng-41 — записи: DOC-0854.
- eng-51 — записи: DOC-0873.
- eng-51/eng-58 — записи: DOC-0871.
- eng-58 — записи: DOC-0831, DOC-0878.
- eng-69 — записи: DOC-0860.
- eng-84 — записи: DOC-0866.
- eng-91 — записи: DOC-0844.
- eng-93 — записи: DOC-0817.
- eng-95 — записи: DOC-0810.
- expectancy proof — записи: DOC-0854.
- Granville — записи: DOC-0881.
- historical old-logic claim — записи: DOC-0878.
- historical target/R:R example — записи: DOC-0849.
- historical trade examples — записи: DOC-0854.
- ICT 2022 model — записи: DOC-0878.
- ICT entry after liquidity sweep — записи: DOC-0875.
- ICT protected swing — записи: DOC-0872.
- ICT raid-swing attribution — записи: DOC-0877.
- ICT's dealing range — записи: DOC-0873.
- ICT/SMC — записи: DOC-0871.
- independent evidence — записи: DOC-0821, DOC-0830.
- Lambert — записи: DOC-0881.
- Lane — записи: DOC-0881.
- liquidation inference — записи: DOC-0866.
- live SUI example — записи: DOC-0867.
- live trade examples — записи: DOC-0844.
- Market Profile TPO value area — записи: DOC-0802.
- Murphy — записи: DOC-0881.
- O'Neil — записи: DOC-0834.
- O'Neil's cup with handle — записи: DOC-0833.
- Osler/SR150 — записи: DOC-0871.
- owner margin — записи: DOC-0860.
- owner quote — записи: DOC-0880.
- owner rule — записи: DOC-0854.
- owner statement — записи: DOC-0850.
- owner/audit promotion claims — записи: DOC-0821.
- owner/engineering provenance — записи: DOC-0801.
- Playing the Opening Range Breakout — записи: DOC-0812.
- ported systems claim — записи: DOC-0867.
- Quong & Soudack — записи: DOC-0881.
- research/statistics claim — записи: DOC-0831.
- research/talib_check.md — записи: DOC-0882.
- research_indicator_confirms.py pre-registration — записи: DOC-0881.
- Sam Seiden — записи: DOC-0860, DOC-0879.
- SMT 2/44 claim — записи: DOC-0854.
- source-defined stop-pierce quantiles — записи: DOC-0841.
- source-defined Strategy.min_rr claim — записи: DOC-0857.
- Steidlmayer — записи: DOC-0811.
- TA-Lib fidelity — записи: DOC-0882.
- Thomas Bulkowski — записи: DOC-0831.
- Tom Williams/VSA — записи: DOC-0821.
- Turtles — записи: DOC-0844.
- validated confirmation claim — записи: DOC-0830.
- Wilder — записи: DOC-0813, DOC-0881, DOC-0883.
- William O'Neil — записи: DOC-0831.
- Wyckoff phase attribution — записи: DOC-0821.

## Утверждения, для которых первоисточник не найден

- DOC-0797: The origin and validation of the configured cascade cap are not documented.
- DOC-0798: No external source was found for the exact one-minute cascade-leg definition.
- DOC-0799: No external validation was found for the configured cascade detector.
- DOC-0800: The retracement, mean-target and stop rules have no identified external primary source.
- DOC-0801: No primary source was found for the combined local session, fill, stop and exit rules.
- DOC-0802: The exact local volume-spread and 30-minute TPO parameters are not established by the cited source.
- DOC-0803: The local completeness check is a policy choice, not an externally validated rule.
- DOC-0804: The session-relative midpoint-bucket convention has no identified external primary source.
- DOC-0805: The exact 30-minute re-entry condition and threshold are not found in the source.
- DOC-0806: The exact formula, window and market application are not verified from a primary Crabel source.
- DOC-0807: The exact lookback and crypto application are not established by a primary source.
- DOC-0808: No external source was found for the project's session tuple configuration.
- DOC-0809: The local holiday and weekday handling is not externally specified in the record.
- DOC-0810: No primary source was found for the exact session-open, two-period and far-edge conditions.
- DOC-0811: The exact open-location, probe, close and target conditions are not found in a primary source.
- DOC-0812: No primary source was found for the exact first-minutes, stop-order, touch-fill and session-close rules.
- DOC-0813: The smoothing and seed details for this RSI implementation are not documented by an external source here.
- DOC-0814: The exact trigger, first-event handling and moving-average exit are not established by the source.
- DOC-0815: No external source establishes the shared lifecycle or configured execution conventions.
- DOC-0816: The far-edge target and stop-beyond-edge rule are not verified as an original method.
- DOC-0817: The exact session list, first-break interval, midpoint stop and range-width target lack a primary source.
- DOC-0818: The explicit daily ATR stop and SMA5 exit are not found in the source.
- DOC-0819: No primary source was found for the opposite-range stop and session-close exit.
- DOC-0820: The SMA5 exit and daily ATR stop combination is not established by the source.
- DOC-0821: No external experiment was found that validates the combined confirmation set or its promotion rule.
- DOC-0822: The predictive value of a present confirmation is not established.
- DOC-0823: No external source establishes the required confirmation set.
- DOC-0824: No primary experiment was found for promotion thresholds or incremental predictive value.
- DOC-0825: No external source establishes the veto's trading benefit.
- DOC-0826: Trade delta alone does not identify passive liquidity or participant direction.
- DOC-0827: No external source was found for the project's coverage threshold.
- DOC-0828: The lookback, minimum-history and missing-listing rules are project parameters without an external source.
- DOC-0829: No external source was found for the exact swing lookback and divergence thresholds.
- DOC-0830: No independent out-of-sample validation of the combined set was found.
- DOC-0831: No primary source was found for the exact depth, duration, volume, stop and measured-target thresholds.
- DOC-0832: The exact local breakout and candle conditions are not source-verified.
- DOC-0833: No primary source was found for the local stop and measured-target implementation.
- DOC-0834: The 8% stop and exact measured-target rules are not established by the checked sources.
- DOC-0835: No external validation was found for the combined event detector.
- DOC-0836: The retention window is a local storage choice.
- DOC-0837: No external source establishes the eligibility policy.
- DOC-0838: Historical microstructure and queue information are not supplied by this input alone.
- DOC-0839: No external source establishes intent labels, target selection or ATR fallback parameters.
- DOC-0840: The exact fee tier, slippage curve and realized-cost equivalence are not established for every trade.
- DOC-0841: No external source was found for the pierce quantiles or their use in live selection.
- DOC-0842: The project's level-kind taxonomy has no external primary source.
- DOC-0843: The source-label taxonomy is project-specific and not externally defined.
- DOC-0844: The maximum-stop percentage, ATR pad and exemptions have no source-verified provenance.
- DOC-0845: The selected ATR combination and minimum multiplier are local parameters.
- DOC-0846: The allowed-timeframe policy is not externally specified.
- DOC-0847: The ranking of level kinds is project-specific.
- DOC-0848: The level-kind rank mapping is not externally defined.
- DOC-0849: No independent experiment was found for the effect of the trimming rule.
- DOC-0850: No primary evidence was found for the claimed trade decision or target policy.
- DOC-0851: The claimed audit frequency and any performance effect were not independently sourced.
- DOC-0852: The synthetic-target taxonomy is project-specific.
- DOC-0853: No independent source was found for setup-key grouping or statistical validity.
- DOC-0854: No primary evidence was found for pierce p50, historical R values, SMT count or expectancy interpretation.
- DOC-0855: No independent source was found for the claimed diagnostic's interpretation.
- DOC-0856: The configured cost-guard threshold is not externally established.
- DOC-0857: The minimum ratio and method-specific provenance are not identified.
- DOC-0858: The interpretation of the selected extreme as actual resting liquidity is not established.
- DOC-0859: Intent ranking and target selection have no external primary source.
- DOC-0860: No primary source was found for the stated ATR range, margin or parameter choice.
- DOC-0861: The cap, moved-pad and penetration thresholds are not externally sourced.
- DOC-0862: Ordering and multipliers of stop components are project-specific.
- DOC-0863: No external source is needed for the local plan schema; no method claim is made.
- DOC-0864: Configured fallback and minimum ratio are not externally established.
- DOC-0865: Structure taxonomy and distance thresholds are project-specific.
- DOC-0866: The example trades, p90 rule and identification of a liquidation pool have no primary evidence.
- DOC-0867: No primary source was found for fidelity of the ported systems or the claimed live result.
- DOC-0868: No external source establishes the extension labeling convention.
- DOC-0869: Refill and target ordering policy is project-specific.
- DOC-0870: Minimum ratio, cost model and use of furthest feasible entry have no external validation.
- DOC-0871: No primary source was found for protected swing, premium/discount or stop-clustering implementation.
- DOC-0872: No primary source was found for the exact protected-swing rule.
- DOC-0873: Pivot significance, fallback window and 50% equilibrium use are not source-verified as an original rule.
- DOC-0874: Directional clipping convention is project-specific.
- DOC-0875: No primary source was found for body threshold, gap indexing, swing reference or close requirement.
- DOC-0876: Use of contiguity as a structure condition has no external source in the record.
- DOC-0877: No primary source was found for the three-candle, 48-bar pivot selection rule.
- DOC-0878: No primary source was found for the exact 2022 model wording, gap conditions or fill rule.
- DOC-0879: No primary source was found for the exact proximal-line, gap and candle-touch rule.
- DOC-0880: No primary source was found for confirmation-close and no-through-zone conditions.
- DOC-0881: No primary source was found for the exact combined panel, parameter set or pre-registration claim.
- DOC-0882: No primary source was found for the exact seed, short-history fallback or claimed 0.4% example.
- DOC-0883: No primary source was found for the exact smoothing seed and panel interpretation.
- DOC-0884: No independent reproducible test was found for the claimed cancellation examples or numerical effect.

## Контроль

- Исправлено записей: 88.
- Удалённых атрибуций: 111.
- Нерешённых утверждений без найденного первоисточника: 88.
- Исходные docstring сохранены в основном реестре и продублированы в JSONL-регистре.
- Исправленные docstring-узлы применены к *.py; алгоритмические тела функций этой операцией не менялись.
