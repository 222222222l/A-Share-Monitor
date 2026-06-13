"""Normalized data models for the A-share monitor package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Security:
    symbol: str
    exchange: str
    name: str
    list_date: str
    market_board: str
    tradable: bool
    bse_reference_only: bool
    industry: str = ""
    sector_tags: tuple[str, ...] = ()
    risk_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float
    adj_factor: float
    is_suspended: bool
    limit_up: float
    limit_down: float
    is_st: bool
    is_new_stock: bool
    turnover_rate: float | None = None
    amplitude: float | None = None
    prev_close: float | None = None
    free_float_market_cap: float | None = None


@dataclass(frozen=True)
class IndexBar:
    index_symbol: str
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float
    index_name: str = ""
    reference_market: str = ""


@dataclass(frozen=True)
class SectorBar:
    sector_id: str
    sector_name: str
    trade_date: str
    close: float
    pct_change: float
    amount: float
    constituent_count: int
    provider: str = ""
    industry_level: str = ""
    concept_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketBreadth:
    trade_date: str
    universe: str
    advancing_count: int
    declining_count: int
    limit_up_count: int
    limit_down_count: int
    new_high_20d_count: int
    new_low_20d_count: int
    total_amount: float
    bse_amount: float | None = None
    bse_advancing_count: int | None = None
    bse_declining_count: int | None = None


@dataclass(frozen=True)
class MarketContext:
    trade_date: str
    manifest: dict[str, Any]
    market_breadth: MarketBreadth
    index_bars: tuple[IndexBar, ...]
    sector_bars: tuple[SectorBar, ...]


@dataclass(frozen=True)
class FundamentalRiskEvent:
    symbol: str
    event_date: str
    announcement_date: str
    event_type: str
    severity: str
    summary: str
    source: str
    source_url: str = ""
    numeric_impact: float | None = None
    related_report_period: str = ""


@dataclass(frozen=True)
class OwnershipFlowSignal:
    symbol: str
    trade_date: str
    retail_crowding_score: float
    institutional_accumulation_score: float
    institutional_exit_score: float
    counterparty_signal: str
    evidence: str
    shareholder_count_change_pct: float | None = None
    avg_holding_per_account_change_pct: float | None = None
    northbound_holding_change_pct: float | None = None
    margin_balance_change_pct: float | None = None
    margin_buy_ratio: float | None = None
    dragon_tiger_institution_net_buy: float | None = None
    block_trade_discount_rate: float | None = None
    block_trade_net_amount: float | None = None
    fund_holding_change_pct: float | None = None
    etf_flow_proxy: float | None = None
    insider_reduction_amount: float | None = None
    data_lag_days: int | None = None


@dataclass(frozen=True)
class MarketDataset:
    dataset_id: str
    source: str
    root: Path
    manifest: dict[str, Any]
    securities: tuple[Security, ...]
    daily_bars: tuple[DailyBar, ...]
    index_bars: tuple[IndexBar, ...]
    sector_bars: tuple[SectorBar, ...]
    market_breadth: tuple[MarketBreadth, ...]
    fundamental_risk_events: tuple[FundamentalRiskEvent, ...]
    ownership_flow_signals: tuple[OwnershipFlowSignal, ...]

    @property
    def tradable_symbols(self) -> tuple[str, ...]:
        return tuple(item.symbol for item in self.securities if item.tradable)

    @property
    def reference_only_symbols(self) -> tuple[str, ...]:
        return tuple(item.symbol for item in self.securities if item.bse_reference_only)

    @property
    def trade_dates(self) -> tuple[str, ...]:
        return tuple(sorted({item.trade_date for item in self.daily_bars}))
