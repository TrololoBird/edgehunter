# edgehunter

`edgehunter` is a streaming crypto-market microstructure scanner and operator
decision-support system. It produces signal cards and a dashboard. The demo
executor talks to BingX VST only; it is not a production trading connector.

## Development

The supported runtime is Python 3.14.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt -c constraints.txt
python -m pip install -r requirements-dev.txt
ruff check .
python -m pytest tests -q
```

Run the scanner with `python main.py` or `python main.py --no-web`. Keep
credentials and local overrides in `config.local.toml` or environment
variables; this file is ignored by Git.

## Evidence status

The repository does not claim a proven trading edge. Historical replay cannot
reconstruct all live microstructure events. Mathematical and market claims are
tracked in [`docs/CLAIMS.md`](docs/CLAIMS.md) and must be supported by tests,
raw event logs, or forward observations before they are treated as facts.

Enable the raw WebSocket journal explicitly when collecting evidence:

```bash
export EDGEHUNTER_RAW_LOG_DIR=/var/lib/edgehunter/raw-events
python main.py --no-web
```

The logger is disabled by default and writes compressed append-only JSONL files.

## Demo execution

`executor.py` requires BingX credentials when enabled and forcibly sets CCXT
sandbox mode. Never provide production credentials to this module.
