"""
Token Research Framework - Library Module
"""

from .lp_calculator import (
    LPCalculator,
    PonsCalculator,
    UniswapV4Calculator,
    PoolParams,
    PositionParams,
    RangeResult,
    DexType,
    price_to_tick,
    tick_to_price,
    sqrt_price_x96_to_price,
    price_to_sqrt_price_x96,
    get_liquidity_for_amounts,
    get_amounts_for_liquidity,
    calculate_il,
    format_result,
)

from .monitor import (
    AlertManager,
    AlertLevel,
    Alert,
    ConsoleChannel,
    TelegramChannel,
    WebhookChannel,
    PositionMonitor,
)

__all__ = [
    # LP Calculator
    "LPCalculator",
    "PonsCalculator",
    "UniswapV4Calculator",
    "PoolParams",
    "PositionParams",
    "RangeResult",
    "DexType",
    "price_to_tick",
    "tick_to_price",
    "sqrt_price_x96_to_price",
    "price_to_sqrt_price_x96",
    "get_liquidity_for_amounts",
    "get_amounts_for_liquidity",
    "calculate_il",
    "format_result",
    # Monitor
    "AlertManager",
    "AlertLevel",
    "Alert",
    "ConsoleChannel",
    "TelegramChannel",
    "WebhookChannel",
    "PositionMonitor",
]

__version__ = "1.0.0"