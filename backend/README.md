# Live Paper Trading Backend

FastAPI backend for a live paper-trading simulator that:

- starts with `$100,000` in virtual capital
- trades only names from the S&P 500 universe
- combines market signals and news sentiment
- simulates buys, sells, and shorts at current market prices
- exposes API endpoints for portfolio state, holdings, trades, performance, and manual cycle execution

## Strategy

Each trading cycle ranks the S&P 500 by a blended score:

- medium-term momentum
- short-term reversal
- volatility penalty
- volume/liquidity preference
- news sentiment from RSS headlines

The engine then:

- goes long the highest-ranked names above a positive threshold
- goes short the lowest-ranked names below a negative threshold
- sizes positions using inverse-volatility weighting
- caps gross exposure, per-position exposure, and turnover indirectly through target weights

## Data sources

- `yfinance` for historical bars and latest prices
- optional Alpaca latest bars/quotes when API keys are present
- RSS feeds via Google News queries and a market-wide Reuters business feed

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

## Environment

Optional environment variables:

- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `ALPACA_BASE_URL`
- `GROQ_API_KEY`
- `GROQ_MODEL=llama-3.1-8b-instant`
- `ENABLE_TRADE_EXPLANATIONS=true`
- `TRADING_INTERVAL_SECONDS=900`
- `UNIVERSE_LIMIT=500`
- `AUTO_RUN_ON_START=true`
- `DATA_DIR=./data`

Trade explanations use Groq through its OpenAI-compatible API when `GROQ_API_KEY` is available.

Runtime portfolio state is stored in `DATA_DIR/state.sqlite3`. If a legacy `state.json` exists and SQLite has
not been initialized yet, the backend imports it once and rebases the first equity point to `$100,000`.

## Important endpoints

- `GET /health`
- `GET /portfolio`
- `GET /holdings`
- `GET /trades`
- `GET /performance`
- `GET /signals`
- `POST /cycle/run`
