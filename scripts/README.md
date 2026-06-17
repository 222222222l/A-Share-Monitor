# Scripts

Operational and smoke scripts for `a-share-monitor`.

Current scripts:

- `generate_b2_fixture.py`: regenerates the deterministic synthetic fixture
  dataset.
- `verify_all_offline.py`: runs the compact offline validation suite across
  manifest/config, fixture loading, strategy chain, report packaging, and
  real-mode data-failure boundaries.
- `run_real_snapshot_smoke.py`: optional real-market snapshot smoke test using
  the configured quote/kline sources.

Run scripts from the package root:

```bash
cd examples/a-share-monitor
python -m scripts.verify_all_offline --repo-root ../..
```
