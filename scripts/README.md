# Scripts

Verification and offline smoke scripts for `a-share-monitor`.

Current script:

- `generate_b2_fixture.py`: regenerates the deterministic synthetic fixture
  dataset created in `B2`.
- `verify_a1_package_skeleton.py`: validates the package skeleton created in
  `A1`.
- `verify_b1_market_data_schema.py`: validates the normalized market data
  schema created in `B1`.
- `verify_b2_offline_fixture.py`: validates the offline fixture dataset created
  in `B2`.
- `verify_b3_fixture_adapter.py`: validates the fixture-backed normalized data
  adapter created in `B3`.
- `verify_c1_market_state.py`: validates the staged A-share market-state gate
  created in `C1`.
- `verify_c2_sector_strength.py`: validates staged sector-strength scoring
  created in `C2`.
- `verify_c3_stock_screen.py`: validates staged right-side stock screening and
  incremental watchlist output created in `C3`.
- `verify_c0_technical_indicators.py`: validates candidate/watchlist-scoped
  technical indicators created in `C0`.

`verify_b3_fixture_adapter.py` imports the package modules. Run it from the
package root:

```bash
cd examples/a-share-monitor
python -m scripts.verify_b3_fixture_adapter --repo-root ../..
python -m scripts.verify_c1_market_state --repo-root ../..
python -m scripts.verify_c2_sector_strength --repo-root ../..
python -m scripts.verify_c3_stock_screen --repo-root ../..
python -m scripts.verify_c0_technical_indicators --repo-root ../..
```
