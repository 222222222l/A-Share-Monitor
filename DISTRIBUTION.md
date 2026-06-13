# Distribution

`a-share-monitor` is intended to become a standalone user package, not a
framework-core feature. Keep it self-contained so it can be moved out of this
repository without code changes.

## Recommended Path

1. Develop and validate locally from this package directory.
2. Move `examples/a-share-monitor/` to its own git repository when the first
   usable offline workflow is ready.
3. Tag releases and keep `kohaku.yaml` `version` in sync with git tags.
4. Share early builds by direct git URL:

   ```bash
   kt install https://github.com/<owner>/a-share-monitor.git
   ```

5. Use editable install for local iteration:

   ```bash
   kt install ./a-share-monitor -e
   ```

6. Apply for marketplace listing only after the package has:

   - deterministic offline validation
   - clear financial safety boundaries
   - no real-order execution enabled by default
   - version tags
   - complete README and release notes

## Marketplace Position

The first public channel should be an experimental template. It should be
listed as research, backtesting, and paper-trading infrastructure, not as an
investment-advice product.

`kohaku.yaml` keeps `marketplace_eligible: false` until the workflow is stable.
