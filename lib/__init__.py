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

from .thegraph import (
    TheGraphClient,
    TheGraphAnalyzer,
    PoolDayData,
    PoolSnapshot,
    PoolInfo,
    SwapEvent,
    PositionEvent,
    Chain,
    SubgraphEndpoint,
    UNISWAP_V3_FACTORIES,
    UNISWAP_V2_FACTORIES,
)

from .simulation import (
    SimulationBackend,
    SimulationResult,
    HoneypotCheckResult,
    ContractSafetyResult,
    ForgeSimulator,
    TenderlySimulator,
    AnvilSimulator,
    HoneypotDetector,
    HoneypotIsAPI,
    SafetyChecker,
)

from .rebalancer import (
    PositionRebalancer,
    PortfolioRebalancer,
    GasOptimizedExecutor,
    FlashbotsExecutor,
    Position,
    RebalanceConfig,
    RebalancePlan,
    RebalanceResult,
    RebalanceStrategy,
    RebalanceAction,
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
    # TheGraph
    "TheGraphClient",
    "TheGraphAnalyzer",
    "PoolDayData",
    "PoolSnapshot",
    "PoolInfo",
    "SwapEvent",
    "PositionEvent",
    "Chain",
    "SubgraphEndpoint",
    "UNISWAP_V3_FACTORIES",
    "UNISWAP_V2_FACTORIES",
    # Simulation
    "SimulationBackend",
    "SimulationResult",
    "HoneypotCheckResult",
    "ContractSafetyResult",
    "ForgeSimulator",
    "TenderlySimulator",
    "AnvilSimulator",
    "HoneypotDetector",
    "HoneypotIsAPI",
    "SafetyChecker",
    # Rebalancer
    "PositionRebalancer",
    "PortfolioRebalancer",
    "GasOptimizedExecutor",
    "FlashbotsExecutor",
    "Position",
    "RebalanceConfig",
    "RebalancePlan",
    "RebalanceResult",
    "RebalanceStrategy",
    "RebalanceAction",
]

__version__ = "1.3.0"