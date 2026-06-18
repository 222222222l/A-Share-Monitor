# a-share-monitor

`a-share-monitor` is a lab-stage package for A-share daily monitoring,
screening, risk planning, and recommendation workflows.

The current package defaults to real-market monitoring while keeping deterministic
offline fixtures for validation:

- resolve the latest completed A-share session for current-market questions
- fetch full-market quotes and candidate klines before screening
- calculate technical indicators from normalized OHLCV data
- enrich only candidate/watchlist symbols with fund-flow and sector-crowding data
- keep real trading disabled
- emit compact structured recommendations for user review
- preserve future broker / paper-order extension points

## Scope

Initial tradable universe:

- Shanghai and Shenzhen A-shares
- Main board, ChiNext, and STAR Market
- Beijing Stock Exchange is excluded from tradable output for now, but can be
  used later as a sentiment or small-cap activity reference

## Current Stage

This package currently contains the daily-monitor package path:

- package manifest
- minimal `lab-runner` creature
- normalized market data schema
- deterministic synthetic offline fixture
- fixture-backed normalized data adapter
- staged market-state, sector-strength, right-side stock screening, technical
  indicator, and risk-reward planning modules
- a minimal `lab-runner` creature, `strategy-critic` creature, and
  `daily-monitor` terrarium for structured report workflows
- compact offline validation, event backtest, and paper-trading log helpers
- compact Web UI handoff packets that avoid sending full-market rows or verbose
  duplicate reports through every agent node
- direct Web UI pipeline routing where root supervises status and only receives
  the final critic-reviewed result

Blueprint: `docs/zh-CN/dev/a-share-monitor-blueprint.md`

## Data Flow

For current-market requests, the daily monitor uses a staged data path:

1. Resolve the latest completed China A-share trading session.
2. Fetch a full-market quote universe from GM when configured, then Tencent, then
   Eastmoney fallback sources.
3. Build market regime, breadth, liquidity, sector-scope, and industry-crowding
   summaries from aggregate data only.
4. Run technical screening on a limited liquid candidate set.
5. Enrich only buy-ready and watchlist symbols with selected-symbol fund-flow
   sources, preferring GM money-flow data, then 10jqka `realFunds`, then public
   Eastmoney/AkShare fallbacks.

Raw full-market rows and full kline histories are not passed to LLM nodes. The
Web UI terrarium receives `a-share-monitor.agent-packet.v1`, a compact packet
containing only data-quality counts, market context, sector context,
recommendations, watchlist conditions, and risk fields.

In the Web UI terrarium, normal content flows directly through:

`data -> regime -> screen -> risk -> recommendation -> critic -> root`

Root is only a lightweight supervisor. It starts the workflow, receives
metadata-only status pings from intermediate nodes, and shows the final
critic-reviewed result. It does not broker or resend compact packets.

## Strategy Configuration

User-adjustable screening and risk parameters live in
`config/strategy.yaml`. The default profile keeps the current behavior stable
while exposing the main decision knobs:

- data quality gates and retry bounds
- optional GM SDK quote/kline priority source
- optional 10jqka selected-symbol fund-flow source
- quote pre-screening thresholds
- market-regime and liquidity gates
- EMA/ATR technical confirmation windows
- risk-reward, position, drawdown, and time-exit preferences
- fallback quote-pool symbols

To keep local preferences outside the package checkout, point
`A_SHARE_MONITOR_STRATEGY_CONFIG` to another YAML file with only the fields you
want to override.

## Optional GM SDK Source

GM SDK is treated as a preferred but optional data source for trading dates,
full-market quotes, and daily kline history. Keep secrets outside the package:

```bash
set A_SHARE_MONITOR_GM_TOKEN=<your-gm-token>
set A_SHARE_MONITOR_GM_PYTHON=<python-with-gm-sdk>
```

If GM is not installed, the token is absent, the terminal service is offline, or
the account lacks a specific data permission, the package falls back to the
public Tencent/Eastmoney/AkShare sources and records the failed source in the
data-acquisition summary.

## Optional 10jqka Fund-Flow Source

For candidate and watchlist symbols, the package can call 10jqka's
selected-symbol `realFunds` endpoint as a lightweight fallback when GM money
flow is unavailable. This source does not require full-market scraping and does
not block the workflow if a symbol request fails. Large-order net flow is used
as an institutional proxy; medium/small-order net flow is used as a retail
proxy. Turnover is treated as an optional enrichment field and sector crowding
is the preferred crowding-risk substitute.

## Token Cost Control

The Web UI package is designed to keep model prompts stable across providers:

- `generate_a_share_report` defaults to `output_profile: agent_packet`.
- The compact packet omits the deterministic Chinese final report unless
  `include_user_report: true` is explicitly requested for debugging.
- Stage nodes must not echo the full upstream packet in their own YAML outputs.
- Non-critic nodes send only metadata-only status pings to root; full packet
  content stays on the direct downstream edge.
- `critic` reviews once and must not ask data nodes to retry optional sector or
  fund-flow enrichment.
- Data-acquisition progress is streamed to the UI as activity metadata and is
  not embedded into the normal compact packet.
- Use `output_profile: full_report` only for manual debugging because it can
  include verbose source summaries.

## Verify

```bash
cd examples/a-share-monitor
python -m scripts.verify_all_offline --repo-root ../..
```

Optional real-market smoke test:

```bash
cd examples/a-share-monitor
python -m scripts.run_real_snapshot_smoke --trade-date 2026-06-16
```

## Safety Boundary

This package is for research, backtesting, paper trading, and architecture
validation. It does not place real orders. Any future broker adapter must be
disabled by default and require explicit user confirmation, risk limits, audit
logs, and compliance review.
