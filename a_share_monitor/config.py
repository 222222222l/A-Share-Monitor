"""User-editable strategy configuration for the A-share monitor package."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STRATEGY_CONFIG_PATH = PACKAGE_ROOT / "config" / "strategy.yaml"
STRATEGY_CONFIG_ENV = "A_SHARE_MONITOR_STRATEGY_CONFIG"

DEFAULT_STRATEGY_CONFIG: dict[str, Any] = {
    "version": 1,
    "profile": "default",
    "data_quality": {
        "minimum_full_market_quotes": 500,
        "http_attempts_per_request": 2,
        "http_timeout_seconds": 12,
        "fallback_trade_date_walk_days": 8,
        "fallback_probe_limit": 3,
        "eastmoney_backup_page_size": 100,
        "eastmoney_backup_max_pages": 70,
        "eastmoney_backup_page_delay_seconds": 0.12,
        "kline_request_delay_seconds": 0.1,
    },
    "quote_screen": {
        "min_entry_amount": 80_000_000,
        "max_abs_pct_change": 8.0,
        "require_close_above_open": True,
        "max_kline_screen_symbols": 12,
        "max_signal_rows": 12,
        "recommendation_limit": 5,
        "watchlist_limit": 10,
        "watchlist_min_amount": 120_000_000,
    },
    "market_gate": {
        "liquidity_crisis_declining_ratio": 0.72,
        "liquidity_crisis_limit_down_min": 20,
        "liquidity_crisis_limit_down_vs_up_multiplier": 2.0,
        "broad_risk_on_advancing_ratio": 0.60,
        "broad_risk_on_index_average_pct_change": 0.2,
        "rotation_advancing_ratio": 0.45,
        "policy_support_index_average_pct_change": 0.0,
        "policy_support_max_advancing_ratio": 0.45,
        "active_style_pct_change": 0.2,
        "weak_style_pct_change": -0.3,
        "high_liquidity_amount": 1_500_000_000_000,
        "normal_liquidity_amount": 800_000_000_000,
        "breadth_broad_positive_ratio": 0.60,
        "breadth_positive_rotation_ratio": 0.45,
        "breadth_mixed_ratio": 0.35,
    },
    "ownership_flow": {
        "enabled": True,
        "batch_size": 80,
        "min_institutional_net_amount": 10_000_000,
        "min_retail_proxy_net_amount": 5_000_000,
        "use_as_hard_filter": False,
        "fallback_history_limit": 5,
    },
    "sector_crowding": {
        "enabled": True,
        "page_size": 100,
        "max_pages": 6,
        "top_n": 20,
        "relative_warming_score": 0.55,
        "high_score": 0.75,
        "extreme_score": 0.85,
        "avoid_extreme_crowding": True,
    },
    "technical": {
        "min_history_days": 60,
        "ema_fast": 5,
        "ema_mid": 10,
        "ema_trend": 20,
        "ema_long": 60,
        "ema_long_tolerance": 0.995,
        "near_trend_ema_pct": 0.08,
        "atr_window": 14,
        "stop_lookback_days": 10,
        "stop_atr_buffer": 0.35,
        "entry_atr_buffer": 0.2,
        "target_lookback_days": 20,
        "target_risk_multiple": 1.6,
        "min_price_risk_pct": 0.01,
    },
    "risk_preference": {
        "min_risk_reward": 1.5,
        "max_position_fraction": 0.2,
        "account_risk_fraction": 0.01,
        "time_exit_days": 10,
        "max_user_drawdown_pct": 0.15,
        "target_2_lookback_days": 60,
        "target_2_risk_multiple": 2.4,
        "target_2_extension_multiple": 0.6,
        "thin_liquidity_amount": 20_000_000,
    },
    "fallback_pool": {
        "300750": "CATL",
        "002594": "BYD",
        "600519": "Kweichow Moutai",
        "601318": "Ping An",
        "600036": "CMB",
        "601899": "Zijin Mining",
        "688981": "SMIC",
        "300059": "East Money",
        "002230": "iFlytek",
        "601138": "Foxconn Industrial Internet",
        "002371": "NAURA",
        "688111": "Kingsoft Office",
        "600900": "Yangtze Power",
    },
}


def load_strategy_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load user strategy config, preserving defaults for omitted fields."""
    config_path = _resolve_config_path(path)
    config = copy.deepcopy(DEFAULT_STRATEGY_CONFIG)
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"strategy config must be a mapping: {config_path}")
        _deep_merge(config, data)
    config["config_path"] = str(config_path)
    return config


def get_setting(config: dict[str, Any], dotted_path: str, default: Any) -> Any:
    """Read a nested setting using a dotted path."""
    current: Any = config
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def get_float(config: dict[str, Any], dotted_path: str, default: float) -> float:
    return float(get_setting(config, dotted_path, default))


def get_int(config: dict[str, Any], dotted_path: str, default: int) -> int:
    return int(get_setting(config, dotted_path, default))


def get_bool(config: dict[str, Any], dotted_path: str, default: bool) -> bool:
    value = get_setting(config, dotted_path, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def summarize_strategy_config(strategy_config: dict[str, Any]) -> dict[str, Any]:
    """Return the compact strategy config metadata included in reports."""
    return {
        "profile": str(strategy_config.get("profile") or "default"),
        "path": str(strategy_config.get("config_path") or ""),
        "risk_preference": {
            "min_risk_reward": get_float(
                strategy_config, "risk_preference.min_risk_reward", 1.5
            ),
            "max_user_drawdown_pct": get_float(
                strategy_config, "risk_preference.max_user_drawdown_pct", 0.15
            ),
            "max_position_fraction": get_float(
                strategy_config, "risk_preference.max_position_fraction", 0.2
            ),
        },
        "screening": {
            "min_entry_amount": get_float(
                strategy_config, "quote_screen.min_entry_amount", 80_000_000
            ),
            "max_kline_screen_symbols": get_int(
                strategy_config, "quote_screen.max_kline_screen_symbols", 12
            ),
            "recommendation_limit": get_int(
                strategy_config, "quote_screen.recommendation_limit", 5
            ),
            "watchlist_limit": get_int(
                strategy_config, "quote_screen.watchlist_limit", 10
            ),
        },
        "market_gate": {
            "broad_risk_on_advancing_ratio": get_float(
                strategy_config, "market_gate.broad_risk_on_advancing_ratio", 0.60
            ),
            "broad_risk_on_index_average_pct_change": get_float(
                strategy_config,
                "market_gate.broad_risk_on_index_average_pct_change",
                0.2,
            ),
            "rotation_advancing_ratio": get_float(
                strategy_config, "market_gate.rotation_advancing_ratio", 0.45
            ),
            "active_style_pct_change": get_float(
                strategy_config, "market_gate.active_style_pct_change", 0.2
            ),
        },
        "ownership_flow": {
            "enabled": get_bool(strategy_config, "ownership_flow.enabled", True),
            "use_as_hard_filter": get_bool(
                strategy_config, "ownership_flow.use_as_hard_filter", False
            ),
            "min_institutional_net_amount": get_float(
                strategy_config,
                "ownership_flow.min_institutional_net_amount",
                10_000_000,
            ),
            "min_retail_proxy_net_amount": get_float(
                strategy_config,
                "ownership_flow.min_retail_proxy_net_amount",
                5_000_000,
            ),
        },
        "sector_crowding": {
            "enabled": get_bool(strategy_config, "sector_crowding.enabled", True),
            "relative_warming_score": get_float(
                strategy_config, "sector_crowding.relative_warming_score", 0.55
            ),
            "high_score": get_float(
                strategy_config, "sector_crowding.high_score", 0.75
            ),
            "extreme_score": get_float(
                strategy_config, "sector_crowding.extreme_score", 0.85
            ),
            "avoid_extreme_crowding": get_bool(
                strategy_config, "sector_crowding.avoid_extreme_crowding", True
            ),
        },
    }


def _resolve_config_path(path: str | Path | None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    override = os.environ.get(STRATEGY_CONFIG_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_STRATEGY_CONFIG_PATH


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value
