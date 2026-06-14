"""Minimal backtesting and paper-trading helpers."""

from a_share_monitor.backtest.event_backtest import BacktestConfig
from a_share_monitor.backtest.event_backtest import BacktestEvent
from a_share_monitor.backtest.event_backtest import BacktestResult
from a_share_monitor.backtest.event_backtest import simulate_long_plan
from a_share_monitor.backtest.paper_trading import build_paper_trade_log

__all__ = [
    "BacktestConfig",
    "BacktestEvent",
    "BacktestResult",
    "build_paper_trade_log",
    "simulate_long_plan",
]
