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
- `verify_c4_risk_plan.py`: validates candidate-only risk-reward, position,
  and exit-risk planning created in `C4`.
- `verify_c_group_technical_screening.py`: runs the C-group technical screening
  system test after C0-C4 closure.
- `generate_d1_structured_report.py`: writes the deterministic D1 structured
  report JSON.
- `verify_d1_structured_report.py`: validates D1 report generation and
  `lab-runner` tool wiring.
- `verify_d2_daily_monitor_terrarium.py`: validates the D2 daily-monitor
  terrarium chain.
- `verify_d3_strategy_critic.py`: validates D3 deterministic critic guardrails.
- `verify_e2_event_backtest.py`: validates the E2 event-driven backtest model
  with T+1, costs, slippage, and exit events.
- `verify_e3_paper_trading_log.py`: validates the E3 paper-trading log format.
- `verify_all_offline.py`: runs the minimal offline A-E validation suite.
- `smoke_d_group_llm_report.py`: optional OpenAI-compatible LLM smoke test for
  user-facing structured report generation.
- `run_real_snapshot_smoke.py`: optional real-market snapshot smoke test using
  public quote/kline endpoints plus an OpenAI-compatible LLM API. This is not
  the formal F1 data adapter.

`verify_b3_fixture_adapter.py` imports the package modules. Run it from the
package root:

```bash
cd examples/a-share-monitor
python -m scripts.verify_b3_fixture_adapter --repo-root ../..
python -m scripts.verify_c1_market_state --repo-root ../..
python -m scripts.verify_c2_sector_strength --repo-root ../..
python -m scripts.verify_c3_stock_screen --repo-root ../..
python -m scripts.verify_c0_technical_indicators --repo-root ../..
python -m scripts.verify_c4_risk_plan --repo-root ../..
python -m scripts.verify_c_group_technical_screening --repo-root ../..
python -m scripts.verify_d1_structured_report --repo-root ../..
python -m scripts.verify_d2_daily_monitor_terrarium --repo-root ../..
python -m scripts.verify_d3_strategy_critic --repo-root ../..
python -m scripts.verify_e2_event_backtest --repo-root ../..
python -m scripts.verify_e3_paper_trading_log --repo-root ../..
python -m scripts.verify_all_offline --repo-root ../..
```
