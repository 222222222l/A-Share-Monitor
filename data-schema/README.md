# Data Schema

This directory will hold normalized market, sector, risk, and recommendation
schemas for the A-share monitor package.

Current schema:

- `market-data-schema.yaml`: normalized records for security master, daily bars,
  index bars, sector bars, market breadth, technical indicators, divergence,
  fundamental risk events, retail/institution counterparty-flow proxies, sector
  scores, stock signals, and recommendations.

Planned tasks:

- `B1`: define market data schema
- `C0`: define technical indicator and divergence evidence fields
- `C4`: define risk-reward and exit-risk fields
