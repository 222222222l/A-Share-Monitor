# a-share-monitor

`a-share-monitor` is a lab-stage package for A-share daily monitoring,
screening, risk planning, and recommendation workflows.

The first implementation phase is deliberately offline-first:

- use local fixtures before live APIs
- calculate technical indicators from normalized OHLCV data
- keep real trading disabled
- emit structured recommendations for user review
- preserve future broker / paper-order extension points

## Scope

Initial tradable universe:

- Shanghai and Shenzhen A-shares
- Main board, ChiNext, and STAR Market
- Beijing Stock Exchange is excluded from tradable output for now, but can be
  used later as a sentiment or small-cap activity reference

## Current Stage

This package currently contains the A1 skeleton plus B1/B2 validation assets:

- package manifest
- minimal `lab-runner` creature
- normalized market data schema
- deterministic synthetic offline fixture
- fixture-backed normalized data adapter
- validation scripts for the package skeleton, schema, and fixture

The strategy and data modules will be added in later blueprint tasks.

Blueprint: `docs/zh-CN/dev/a-share-monitor-blueprint.md`

## Verify

```bash
python ./examples/a-share-monitor/scripts/verify_a1_package_skeleton.py --repo-root .
python ./examples/a-share-monitor/scripts/verify_b1_market_data_schema.py --repo-root .
python ./examples/a-share-monitor/scripts/verify_b2_offline_fixture.py --repo-root .
```

Run the B3 adapter verification from the package root so package modules are
importable without relying on this repository:

```bash
cd examples/a-share-monitor
python -m scripts.verify_b3_fixture_adapter --repo-root ../..
python -m scripts.verify_c1_market_state --repo-root ../..
python -m scripts.verify_c2_sector_strength --repo-root ../..
python -m scripts.verify_c3_stock_screen --repo-root ../..
```

## Safety Boundary

This package is for research, backtesting, paper trading, and architecture
validation. It does not place real orders. Any future broker adapter must be
disabled by default and require explicit user confirmation, risk limits, audit
logs, and compliance review.
