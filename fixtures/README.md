# Fixtures

Offline fixtures for deterministic validation.

## B2 Minimal Dataset

`b2_minimal/` is a synthetic dataset. It is designed only for offline tests,
strategy development, and schema validation. It is not investment advice and
does not represent live market data.

Included files:

- `manifest.json`: dataset metadata, row counts, units, and safety note
- `security_master.csv`: five tradable A-share-like symbols plus one BSE
  reference-only symbol
- `daily_bars.csv`: 180 synthetic trading days for each tradable symbol
- `index_bars.csv`: two A-share market indexes plus one BSE reference index
- `sector_bars.csv`: two synthetic sectors
- `market_breadth.csv`: market breadth and BSE reference activity
- `fundamental_risk_events.csv`: one synthetic event for risk-filter tests
- `ownership_flow_signals.csv`: synthetic retail/institution counterparty-flow
  proxy signals for risk and opportunity tests

Regenerate the fixture:

```bash
python ./examples/a-share-monitor/scripts/generate_b2_fixture.py
```

Verify the fixture:

```bash
python ./examples/a-share-monitor/scripts/verify_b2_offline_fixture.py --repo-root .
```
