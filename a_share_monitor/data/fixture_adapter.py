"""Fixture-backed data adapter for offline validation."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Callable
from typing import TypeVar

from a_share_monitor.data.models import DailyBar
from a_share_monitor.data.models import FundamentalRiskEvent
from a_share_monitor.data.models import IndexBar
from a_share_monitor.data.models import MarketBreadth
from a_share_monitor.data.models import MarketContext
from a_share_monitor.data.models import MarketDataset
from a_share_monitor.data.models import OwnershipFlowSignal
from a_share_monitor.data.models import SectorBar
from a_share_monitor.data.models import Security


T = TypeVar("T")

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_ROOT = PACKAGE_ROOT / "fixtures" / "b2_minimal"


class FixtureAdapterError(ValueError):
    """Raised when fixture data cannot be loaded into normalized records."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FixtureAdapterError(f"Missing fixture file: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_manifest(root: Path) -> dict:
    path = root / "manifest.json"
    if not path.exists():
        raise FixtureAdapterError(f"Missing fixture manifest: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise FixtureAdapterError("Fixture manifest must be a JSON object")
    return data


def _bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise FixtureAdapterError(f"Expected boolean string, got: {value!r}")


def _int(value: str, *, optional: bool = False) -> int | None:
    if optional and value == "":
        return None
    return int(value)


def _float(value: str, *, optional: bool = False) -> float | None:
    if optional and value == "":
        return None
    return float(value)


def _tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(";") if item.strip())


def _map_rows(
    file_name: str,
    rows: list[dict[str, str]],
    mapper: Callable[[dict[str, str]], T],
) -> tuple[T, ...]:
    mapped = []
    for index, row in enumerate(rows, start=2):
        try:
            mapped.append(mapper(row))
        except (KeyError, TypeError, ValueError) as exc:
            raise FixtureAdapterError(f"{file_name}:{index}: {exc}") from exc
    return tuple(mapped)


def _security(row: dict[str, str]) -> Security:
    return Security(
        symbol=row["symbol"],
        exchange=row["exchange"],
        name=row["name"],
        list_date=row["list_date"],
        market_board=row["market_board"],
        tradable=_bool(row["tradable"]),
        bse_reference_only=_bool(row["bse_reference_only"]),
        industry=row.get("industry", ""),
        sector_tags=_tuple(row.get("sector_tags", "")),
        risk_flags=_tuple(row.get("risk_flags", "")),
    )


def _daily_bar(row: dict[str, str]) -> DailyBar:
    return DailyBar(
        symbol=row["symbol"],
        trade_date=row["trade_date"],
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=int(row["volume"]),
        amount=float(row["amount"]),
        adj_factor=float(row["adj_factor"]),
        is_suspended=_bool(row["is_suspended"]),
        limit_up=float(row["limit_up"]),
        limit_down=float(row["limit_down"]),
        is_st=_bool(row["is_st"]),
        is_new_stock=_bool(row["is_new_stock"]),
        turnover_rate=_float(row.get("turnover_rate", ""), optional=True),
        amplitude=_float(row.get("amplitude", ""), optional=True),
        prev_close=_float(row.get("prev_close", ""), optional=True),
        free_float_market_cap=_float(
            row.get("free_float_market_cap", ""), optional=True
        ),
    )


def _index_bar(row: dict[str, str]) -> IndexBar:
    return IndexBar(
        index_symbol=row["index_symbol"],
        trade_date=row["trade_date"],
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=int(row["volume"]),
        amount=float(row["amount"]),
        index_name=row.get("index_name", ""),
        reference_market=row.get("reference_market", ""),
    )


def _sector_bar(row: dict[str, str]) -> SectorBar:
    return SectorBar(
        sector_id=row["sector_id"],
        sector_name=row["sector_name"],
        trade_date=row["trade_date"],
        close=float(row["close"]),
        pct_change=float(row["pct_change"]),
        amount=float(row["amount"]),
        constituent_count=int(row["constituent_count"]),
        provider=row.get("provider", ""),
        industry_level=row.get("industry_level", ""),
        concept_tags=_tuple(row.get("concept_tags", "")),
    )


def _market_breadth(row: dict[str, str]) -> MarketBreadth:
    return MarketBreadth(
        trade_date=row["trade_date"],
        universe=row["universe"],
        advancing_count=int(row["advancing_count"]),
        declining_count=int(row["declining_count"]),
        limit_up_count=int(row["limit_up_count"]),
        limit_down_count=int(row["limit_down_count"]),
        new_high_20d_count=int(row["new_high_20d_count"]),
        new_low_20d_count=int(row["new_low_20d_count"]),
        total_amount=float(row["total_amount"]),
        bse_amount=_float(row.get("bse_amount", ""), optional=True),
        bse_advancing_count=_int(row.get("bse_advancing_count", ""), optional=True),
        bse_declining_count=_int(row.get("bse_declining_count", ""), optional=True),
    )


def _fundamental_event(row: dict[str, str]) -> FundamentalRiskEvent:
    return FundamentalRiskEvent(
        symbol=row["symbol"],
        event_date=row["event_date"],
        announcement_date=row["announcement_date"],
        event_type=row["event_type"],
        severity=row["severity"],
        summary=row["summary"],
        source=row["source"],
        source_url=row.get("source_url", ""),
        numeric_impact=_float(row.get("numeric_impact", ""), optional=True),
        related_report_period=row.get("related_report_period", ""),
    )


def _ownership_flow(row: dict[str, str]) -> OwnershipFlowSignal:
    return OwnershipFlowSignal(
        symbol=row["symbol"],
        trade_date=row["trade_date"],
        retail_crowding_score=float(row["retail_crowding_score"]),
        institutional_accumulation_score=float(row["institutional_accumulation_score"]),
        institutional_exit_score=float(row["institutional_exit_score"]),
        counterparty_signal=row["counterparty_signal"],
        evidence=row["evidence"],
        shareholder_count_change_pct=_float(
            row.get("shareholder_count_change_pct", ""), optional=True
        ),
        avg_holding_per_account_change_pct=_float(
            row.get("avg_holding_per_account_change_pct", ""), optional=True
        ),
        northbound_holding_change_pct=_float(
            row.get("northbound_holding_change_pct", ""), optional=True
        ),
        margin_balance_change_pct=_float(
            row.get("margin_balance_change_pct", ""), optional=True
        ),
        margin_buy_ratio=_float(row.get("margin_buy_ratio", ""), optional=True),
        dragon_tiger_institution_net_buy=_float(
            row.get("dragon_tiger_institution_net_buy", ""), optional=True
        ),
        block_trade_discount_rate=_float(
            row.get("block_trade_discount_rate", ""), optional=True
        ),
        block_trade_net_amount=_float(
            row.get("block_trade_net_amount", ""), optional=True
        ),
        fund_holding_change_pct=_float(
            row.get("fund_holding_change_pct", ""), optional=True
        ),
        etf_flow_proxy=_float(row.get("etf_flow_proxy", ""), optional=True),
        insider_reduction_amount=_float(
            row.get("insider_reduction_amount", ""), optional=True
        ),
        data_lag_days=_int(row.get("data_lag_days", ""), optional=True),
    )


class FixtureMarketDataAdapter:
    """Load normalized market records from the local fixture dataset."""

    def __init__(self, root: Path | str = DEFAULT_FIXTURE_ROOT) -> None:
        self.root = Path(root)

    def load_manifest(self) -> dict:
        return _read_manifest(self.root)

    def load_security_master(self) -> tuple[Security, ...]:
        return _map_rows(
            "security_master.csv",
            _read_csv(self.root / "security_master.csv"),
            _security,
        )

    def load_market_context(self, trade_date: str | None = None) -> MarketContext:
        manifest = self.load_manifest()
        market_breadth = _map_rows(
            "market_breadth.csv",
            _read_csv(self.root / "market_breadth.csv"),
            _market_breadth,
        )
        index_bars = _map_rows(
            "index_bars.csv", _read_csv(self.root / "index_bars.csv"), _index_bar
        )
        sector_bars = _map_rows(
            "sector_bars.csv", _read_csv(self.root / "sector_bars.csv"), _sector_bar
        )
        selected_date = trade_date or max(item.trade_date for item in market_breadth)
        breadth = _find_one(
            market_breadth,
            lambda item: item.trade_date == selected_date,
            f"market breadth for {selected_date}",
        )
        return MarketContext(
            trade_date=selected_date,
            manifest=manifest,
            market_breadth=breadth,
            index_bars=tuple(
                item for item in index_bars if item.trade_date == selected_date
            ),
            sector_bars=tuple(
                item for item in sector_bars if item.trade_date == selected_date
            ),
        )

    def load_sector_history(
        self,
        *,
        end_date: str | None = None,
        lookback: int | None = None,
    ) -> tuple[SectorBar, ...]:
        rows = _map_rows(
            "sector_bars.csv", _read_csv(self.root / "sector_bars.csv"), _sector_bar
        )
        if end_date is not None:
            rows = tuple(item for item in rows if item.trade_date <= end_date)
        rows = tuple(sorted(rows, key=lambda item: (item.sector_id, item.trade_date)))
        if lookback is None:
            return rows
        trimmed = []
        for sector_id in sorted({item.sector_id for item in rows}):
            sector_rows = [item for item in rows if item.sector_id == sector_id]
            trimmed.extend(sector_rows[-lookback:])
        return tuple(trimmed)

    def load_symbol_daily_bars(
        self,
        symbols: tuple[str, ...] | list[str] | set[str],
        *,
        end_date: str | None = None,
        lookback: int | None = None,
    ) -> tuple[DailyBar, ...]:
        symbol_set = set(symbols)
        rows = _map_rows(
            "daily_bars.csv", _read_csv(self.root / "daily_bars.csv"), _daily_bar
        )
        scoped = [item for item in rows if item.symbol in symbol_set]
        if end_date is not None:
            scoped = [item for item in scoped if item.trade_date <= end_date]
        scoped.sort(key=lambda item: (item.symbol, item.trade_date))
        if lookback is None:
            return tuple(scoped)
        trimmed = []
        for symbol in symbol_set:
            symbol_rows = [item for item in scoped if item.symbol == symbol]
            trimmed.extend(symbol_rows[-lookback:])
        return tuple(trimmed)

    def load_ownership_flow_signals(
        self, symbols: tuple[str, ...] | list[str] | set[str]
    ) -> tuple[OwnershipFlowSignal, ...]:
        symbol_set = set(symbols)
        rows = _map_rows(
            "ownership_flow_signals.csv",
            _read_csv(self.root / "ownership_flow_signals.csv"),
            _ownership_flow,
        )
        return tuple(item for item in rows if item.symbol in symbol_set)

    def load_fundamental_risk_events(
        self, symbols: tuple[str, ...] | list[str] | set[str]
    ) -> tuple[FundamentalRiskEvent, ...]:
        symbol_set = set(symbols)
        rows = _map_rows(
            "fundamental_risk_events.csv",
            _read_csv(self.root / "fundamental_risk_events.csv"),
            _fundamental_event,
        )
        return tuple(item for item in rows if item.symbol in symbol_set)

    def load(self) -> MarketDataset:
        manifest = self.load_manifest()
        securities = self.load_security_master()
        daily_bars = _map_rows(
            "daily_bars.csv", _read_csv(self.root / "daily_bars.csv"), _daily_bar
        )
        index_bars = _map_rows(
            "index_bars.csv", _read_csv(self.root / "index_bars.csv"), _index_bar
        )
        sector_bars = _map_rows(
            "sector_bars.csv", _read_csv(self.root / "sector_bars.csv"), _sector_bar
        )
        market_breadth = _map_rows(
            "market_breadth.csv",
            _read_csv(self.root / "market_breadth.csv"),
            _market_breadth,
        )
        fundamental_events = _map_rows(
            "fundamental_risk_events.csv",
            _read_csv(self.root / "fundamental_risk_events.csv"),
            _fundamental_event,
        )
        ownership_flows = _map_rows(
            "ownership_flow_signals.csv",
            _read_csv(self.root / "ownership_flow_signals.csv"),
            _ownership_flow,
        )

        return MarketDataset(
            dataset_id=str(manifest.get("dataset_id") or self.root.name),
            source="fixture",
            root=self.root,
            manifest=manifest,
            securities=securities,
            daily_bars=daily_bars,
            index_bars=index_bars,
            sector_bars=sector_bars,
            market_breadth=market_breadth,
            fundamental_risk_events=fundamental_events,
            ownership_flow_signals=ownership_flows,
        )


def load_fixture_dataset(root: Path | str = DEFAULT_FIXTURE_ROOT) -> MarketDataset:
    """Load the default offline fixture dataset."""
    return FixtureMarketDataAdapter(root).load()


def _find_one(items: tuple[T, ...], predicate: Callable[[T], bool], label: str) -> T:
    for item in items:
        if predicate(item):
            return item
    raise FixtureAdapterError(f"Missing {label}")
