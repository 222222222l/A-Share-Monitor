"""Data adapters and normalized data contracts for A-share monitoring."""

from a_share_monitor.data.fixture_adapter import FixtureAdapterError
from a_share_monitor.data.fixture_adapter import FixtureMarketDataAdapter
from a_share_monitor.data.fixture_adapter import load_fixture_dataset
from a_share_monitor.data.models import DailyBar
from a_share_monitor.data.models import FundamentalRiskEvent
from a_share_monitor.data.models import IndexBar
from a_share_monitor.data.models import MarketBreadth
from a_share_monitor.data.models import MarketContext
from a_share_monitor.data.models import MarketDataset
from a_share_monitor.data.models import OwnershipFlowSignal
from a_share_monitor.data.models import SectorBar
from a_share_monitor.data.models import Security

__all__ = [
    "DailyBar",
    "FixtureAdapterError",
    "FixtureMarketDataAdapter",
    "FundamentalRiskEvent",
    "IndexBar",
    "MarketBreadth",
    "MarketContext",
    "MarketDataset",
    "OwnershipFlowSignal",
    "SectorBar",
    "Security",
    "load_fixture_dataset",
]
