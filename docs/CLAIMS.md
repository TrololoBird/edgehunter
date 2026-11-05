# Evidence and claims register

This register separates facts about the implementation from mathematical and
market hypotheses. A passing unit test does not prove a trading edge.

| ID | Claim | Type | Evidence required | Status |
|---|---|---|---|---|
| CODE-001 | SQLite uses WAL, `synchronous=NORMAL`, `busy_timeout=5000` | CODE_FACT | `journal.py`, unit test | confirmed |
| CODE-002 | Demo execution uses BingX CCXT sandbox/VST mode | CODE_FACT | `executor.py`, config test | confirmed |
| CODE-003 | Process pools are created by scanner/ML/pretrain, not `pools.py` | CODE_FACT | source inspection | confirmed |
| CODE-004 | Production installation constraints resolve | INVARIANT | `pip install -r requirements.txt -c constraints.txt` | pending CI |
| DATA-001 | A missing secondary venue must not become a zero measurement | INVARIANT | fault-injection test | pending |
| DATA-002 | OI changes are computed only from fresh comparable venues | INVARIANT | venue outage fixture | pending |
| MATH-001 | A proposed level merge rule improves signal quality | MARKET_HYPOTHESIS | shadow mode and forward data | unverified |
| MATH-002 | A proposed room-to-run gate improves outcomes | MARKET_HYPOTHESIS | shadow mode and holdout | unverified |
| MATH-003 | ML probabilities are calibrated | MARKET_HYPOTHESIS | calibration report on independent data | unverified |

Claims without reproducible evidence must remain labelled `unverified`.
