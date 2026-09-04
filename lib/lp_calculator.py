"""
LP Range Calculator — Uniswap V3, V4, and Pons

Calculates optimal tick ranges for concentrated liquidity positions
based on volatility, fee tier, and risk tolerance.
"""

import math
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, List
from enum import Enum


class DexType(Enum):
    UNISWAP_V3 = "uniswap_v3"
    UNISWAP_V4 = "uniswap_v4"
    PANCAKE_V3 = "pancake_v3"
    PONS = "pons"


@dataclass
class PoolParams:
    """Pool configuration parameters."""
    fee_tier: int           # 100, 500, 3000, 10000 (basis points)
    tick_spacing: int       # 10, 60, 200
    current_tick: int       # Current pool tick
    current_sqrt_price_x96: int
    liquidity: int
    token0_decimals: int
    token1_decimals: int


@dataclass
class PositionParams:
    """User position parameters."""
    amount0: float          # Amount of token0 to deposit
    amount1: float          # Amount of token1 to deposit
    price_lower: float      # Lower price bound
    price_upper: float      # Upper price bound
    # OR tick-based
    tick_lower: Optional[int] = None
    tick_upper: Optional[int] = None


@dataclass
class RangeResult:
    """Calculated range output."""
    tick_lower: int
    tick_upper: int
    price_lower: float
    price_upper: float
    amount0: float
    amount1: float
    liquidity: int
    in_range: bool
    distance_to_lower_ticks: int
    distance_to_upper_ticks: int
    il_estimate_1x: float      # IL if price moves 1x range width
    il_estimate_2x: float      # IL if price moves 2x range width
    fee_apr_estimate: float    # Estimated fee APR at current volume
    risk_score: float          # 0-100 (higher = riskier)


# ===================== CORE MATH =====================

TICK_BASE = 1.0001
Q96 = 2**96

def price_to_tick(price: float) -> int:
    """Convert price to tick (price = token1/token0)."""
    return math.floor(math.log(price) / math.log(TICK_BASE))

def tick_to_price(tick: int) -> float:
    """Convert tick to price."""
    return TICK_BASE ** tick

def sqrt_price_x96_to_price(sqrt_price_x96: int, decimals0: int, decimals1: int) -> float:
    """Convert sqrtPriceX96 to human-readable price (token1/token0)."""
    price_x192 = sqrt_price_x96 * sqrt_price_x96
    price = price_x192 / (2**192)
    # Adjust for decimals: price = (token1/token0) * 10^(d0-d1)
    return price * (10 ** (decimals0 - decimals1))

def price_to_sqrt_price_x96(price: float, decimals0: int, decimals1: int) -> int:
    """Convert human price to sqrtPriceX96."""
    adjusted_price = price * (10 ** (decimals1 - decimals0))
    sqrt_price = math.sqrt(adjusted_price)
    return int(sqrt_price * Q96)

def tick_to_sqrt_price_x96(tick: int) -> int:
    """Convert tick to sqrtPriceX96."""
    return int((TICK_BASE ** (tick / 2)) * Q96)


# ===================== LIQUIDITY MATH =====================

def get_liquidity_for_amounts(
    sqrt_price_x96: int,
    tick_lower: int,
    tick_upper: int,
    amount0: int,
    amount1: int
) -> int:
    """
    Calculate liquidity from token amounts.
    Based on Uniswap V3 math.
    """
    sqrt_ratio_lower = tick_to_sqrt_price_x96(tick_lower)
    sqrt_ratio_upper = tick_to_sqrt_price_x96(tick_upper)

    if sqrt_price_x96 <= sqrt_ratio_lower:
        # Price below range - all amount0
        liquidity = (amount0 * sqrt_ratio_lower * sqrt_ratio_upper) // (sqrt_ratio_upper - sqrt_ratio_lower)
    elif sqrt_price_x96 >= sqrt_ratio_upper:
        # Price above range - all amount1
        liquidity = amount1 // (sqrt_ratio_upper - sqrt_ratio_lower)
    else:
        # Price in range
        liquidity0 = (amount0 * sqrt_ratio_upper * sqrt_price_x96) // (sqrt_ratio_upper - sqrt_price_x96)
        liquidity1 = (amount1 * sqrt_price_x96) // (sqrt_price_x96 - sqrt_ratio_lower)
        liquidity = min(liquidity0, liquidity1)

    return liquidity


def get_amounts_for_liquidity(
    sqrt_price_x96: int,
    tick_lower: int,
    tick_upper: int,
    liquidity: int
) -> Tuple[int, int]:
    """Calculate token amounts from liquidity."""
    sqrt_ratio_lower = tick_to_sqrt_price_x96(tick_lower)
    sqrt_ratio_upper = tick_to_sqrt_price_x96(tick_upper)

    if sqrt_price_x96 <= sqrt_ratio_lower:
        amount0 = (liquidity * (sqrt_ratio_upper - sqrt_ratio_lower)) // sqrt_ratio_upper
        amount1 = 0
    elif sqrt_price_x96 >= sqrt_ratio_upper:
        amount0 = 0
        amount1 = liquidity * (sqrt_ratio_upper - sqrt_ratio_lower)
    else:
        amount0 = (liquidity * (sqrt_ratio_upper - sqrt_price_x96)) // sqrt_ratio_upper
        amount1 = liquidity * (sqrt_price_x96 - sqrt_ratio_lower)

    return amount0, amount1


# ===================== IMPERMANENT LOSS =====================

def calculate_il(
    price_ratio: float,
    tick_lower: int,
    tick_upper: int,
    current_tick: int
) -> float:
    """
    Estimate impermanent loss for a price move.
    price_ratio = new_price / entry_price
    """
    # Simplified IL formula for concentrated liquidity
    # IL ≈ (2 * sqrt(price_ratio)) / (1 + price_ratio) - 1 for full range
    # For concentrated: adjust based on position width

    if price_ratio <= 0:
        return -1.0  # Total loss

    # Position width in price space
    price_lower = tick_to_price(tick_lower)
    price_upper = tick_to_price(tick_upper)
    entry_price = tick_to_price(current_tick)

    # Distance from current price to bounds
    dist_lower = (entry_price - price_lower) / entry_price
    dist_upper = (price_upper - entry_price) / entry_price

    # If price moves outside range, IL becomes permanent
    new_price = entry_price * price_ratio

    if new_price <= price_lower:
        # Fully in token0 - max IL for this range
        return 1 - (2 * math.sqrt(price_lower / entry_price)) / (1 + price_lower / entry_price)
    elif new_price >= price_upper:
        # Fully in token1
        return 1 - (2 * math.sqrt(entry_price / price_upper)) / (1 + entry_price / price_upper)
    else:
        # In range - standard IL
        return 1 - (2 * math.sqrt(price_ratio)) / (1 + price_ratio)


# ===================== FEE APR ESTIMATION =====================

def estimate_fee_apr(
    pool_liquidity: int,
    position_liquidity: int,
    volume_24h: float,
    fee_tier: int,
    days: int = 365
) -> float:
    """
    Estimate fee APR for a position.
    fee_tier in basis points (3000 = 0.3%)
    """
    if pool_liquidity == 0:
        return 0.0

    # Position's share of pool
    share = position_liquidity / pool_liquidity

    # Daily fees = volume * fee_tier
    daily_fees = volume_24h * (fee_tier / 10000)
    position_daily_fees = daily_fees * share

    # Annualize
    annual_fees = position_daily_fees * days

    # Need position value to get APR%
    # This is rough - would need current token prices
    return 0.0  # Placeholder - needs position value


# ===================== MAIN CALCULATOR CLASS =====================

class LPCalculator:
    """Main calculator for LP position planning."""

    def __init__(self, dex_type: DexType = DexType.UNISWAP_V3):
        self.dex_type = dex_type

    def calculate_range_from_price(
        self,
        pool: PoolParams,
        center_price: float,
        width_pct: float,        # e.g., 0.20 = ±20% from center
        amount0: float,
        amount1: float
    ) -> RangeResult:
        """Calculate range from center price and percentage width."""

        # Convert amounts to raw (handle decimals)
        amount0_raw = int(amount0 * 10**pool.token0_decimals)
        amount1_raw = int(amount1 * 10**pool.token1_decimals)

        # Current price from pool
        current_price = sqrt_price_x96_to_price(
            pool.current_sqrt_price_x96,
            pool.token0_decimals,
            pool.token1_decimals
        )

        # Price bounds
        price_lower = center_price * (1 - width_pct)
        price_upper = center_price * (1 + width_pct)

        # Convert to ticks
        tick_lower = price_to_tick(price_lower)
        tick_upper = price_to_tick(price_upper)

        # Align to tick spacing
        tick_lower = (tick_lower // pool.tick_spacing) * pool.tick_spacing
        tick_upper = (tick_upper // pool.tick_spacing) * pool.tick_spacing

        # Get liquidity
        sqrt_price = pool.current_sqrt_price_x96
        liquidity = get_liquidity_for_amounts(
            sqrt_price, tick_lower, tick_upper, amount0_raw, amount1_raw
        )

        # Get actual amounts from liquidity
        actual_amount0, actual_amount1 = get_amounts_for_liquidity(
            sqrt_price, tick_lower, tick_upper, liquidity
        )

        # Check if in range
        current_tick = pool.current_tick
        in_range = tick_lower <= current_tick <= tick_upper

        # Distances
        dist_lower = current_tick - tick_lower
        dist_upper = tick_upper - current_tick

        # IL estimates
        il_1x = calculate_il(1.5, tick_lower, tick_upper, pool.current_tick)  # 50% move
        il_2x = calculate_il(2.0, tick_lower, tick_upper, pool.current_tick)  # 100% move

        # Convert back to human amounts
        actual_amount0_human = actual_amount0 / 10**pool.token0_decimals
        actual_amount1_human = actual_amount1 / 10**pool.token1_decimals

        price_lower_human = tick_to_price(tick_lower)
        price_upper_human = tick_to_price(tick_upper)

        return RangeResult(
            tick_lower=tick_lower,
            tick_upper=tick_upper,
            price_lower=price_lower_human,
            price_upper=price_upper_human,
            amount0=actual_amount0_human,
            amount1=actual_amount1_human,
            liquidity=liquidity,
            in_range=in_range,
            distance_to_lower_ticks=dist_lower,
            distance_to_upper_ticks=dist_upper,
            il_estimate_1x=il_1x,
            il_estimate_2x=il_2x,
            fee_apr_estimate=0.0,  # Needs volume data
            risk_score=self._calculate_risk_score(dist_lower, dist_upper, width_pct)
        )

    def calculate_range_from_ticks(
        self,
        pool: PoolParams,
        tick_lower: int,
        tick_upper: int,
        amount0: float,
        amount1: float
    ) -> RangeResult:
        """Calculate range from explicit tick bounds."""
        # Align to tick spacing
        tick_lower = (tick_lower // pool.tick_spacing) * pool.tick_spacing
        tick_upper = (tick_upper // pool.tick_spacing) * pool.tick_spacing

        amount0_raw = int(amount0 * 10**pool.token0_decimals)
        amount1_raw = int(amount1 * 10**pool.token1_decimals)

        liquidity = get_liquidity_for_amounts(
            pool.current_sqrt_price_x96, tick_lower, tick_upper, amount0_raw, amount1_raw
        )

        actual_amount0, actual_amount1 = get_amounts_for_liquidity(
            pool.current_sqrt_price_x96, tick_lower, tick_upper, liquidity
        )

        current_tick = pool.current_tick
        in_range = tick_lower <= current_tick <= tick_upper

        price_lower = tick_to_price(tick_lower)
        price_upper = tick_to_price(tick_upper)

        return RangeResult(
            tick_lower=tick_lower,
            tick_upper=tick_upper,
            price_lower=price_lower,
            price_upper=price_upper,
            amount0=actual_amount0 / 10**pool.token0_decimals,
            amount1=actual_amount1 / 10**pool.token1_decimals,
            liquidity=liquidity,
            in_range=in_range,
            distance_to_lower_ticks=current_tick - tick_lower,
            distance_to_upper_ticks=tick_upper - current_tick,
            il_estimate_1x=calculate_il(1.5, tick_lower, tick_upper, current_tick),
            il_estimate_2x=calculate_il(2.0, tick_lower, tick_upper, current_tick),
            fee_apr_estimate=0.0,
            risk_score=self._calculate_risk_score(current_tick - tick_lower, tick_upper - current_tick, 0)
        )

    def _calculate_risk_score(self, dist_lower: int, dist_upper: int, width_pct: float) -> float:
        """Calculate risk score 0-100."""
        min_dist = min(dist_lower, dist_upper)
        max_dist = max(dist_lower, dist_upper)

        # Base risk from distance to nearest boundary
        distance_risk = max(0, 100 - (min_dist / 100))  # 100 ticks = 0 risk, 0 ticks = 100 risk

        # Width risk
        width_risk = min(100, width_pct * 500) if width_pct > 0 else 50

        # Asymmetry risk
        asym_risk = abs(dist_lower - dist_upper) / max(dist_lower + dist_upper, 1) * 50

        return min(100, (distance_risk * 0.5 + width_risk * 0.3 + asym_risk * 0.2))

    def find_optimal_range(
        self,
        pool: PoolParams,
        amount0: float,
        amount1: float,
        target_width_pct: float = 0.15,
        max_width_pct: float = 0.50,
        step_pct: float = 0.02
    ) -> List[RangeResult]:
        """
        Find optimal range by testing multiple widths.
        Returns list sorted by risk-adjusted return.
        """
        results = []
        current_price = sqrt_price_x96_to_price(
            pool.current_sqrt_price_x96,
            pool.token0_decimals,
            pool.token1_decimals
        )

        width = target_width_pct
        while width <= max_width_pct:
            result = self.calculate_range_from_price(
                pool, current_price, width, amount0, amount1
            )
            if result.in_range:
                results.append(result)
            width += step_pct

        # Sort by risk-adjusted metric (lower risk_score better)
        results.sort(key=lambda x: x.risk_score)
        return results


# ===================== PONS-SPECIFIC =====================

class PonsCalculator(LPCalculator):
    """Pons-specific calculator (CLMM on Base)."""

    def __init__(self):
        super().__init__(DexType.PONS)

    def calculate_pons_range(
        self,
        pool: PoolParams,
        amount0: float,
        amount1: float,
        strategy: str = "balanced"  # "balanced", "conservative", "aggressive"
    ) -> RangeResult:
        """
        Pons-specific range calculation.
        Pons uses similar CLMM math but may have different fee tiers / incentives.
        """
        widths = {
            "conservative": 0.10,
            "balanced": 0.20,
            "aggressive": 0.40
        }
        width = widths.get(strategy, 0.20)

        current_price = sqrt_price_x96_to_price(
            pool.current_sqrt_price_x96,
            pool.token0_decimals,
            pool.token1_decimals
        )

        return self.calculate_range_from_price(pool, current_price, width, amount0, amount1)


# ===================== V4-SPECIFIC =====================

class UniswapV4Calculator(LPCalculator):
    """Uniswap V4 calculator (hooks, dynamic fees)."""

    def __init__(self):
        super().__init__(DexType.UNISWAP_V4)

    def calculate_v4_range(
        self,
        pool: PoolParams,
        amount0: float,
        amount1: float,
        hook_data: Optional[Dict] = None
    ) -> RangeResult:
        """
        V4 range calculation with hook considerations.
        hook_data can contain dynamic fee info, oracle requirements, etc.
        """
        # For now, same as V3 but with hook awareness
        # Hooks can modify fee, add oracle, restrict range, etc.
        current_price = sqrt_price_x96_to_price(
            pool.current_sqrt_price_x96,
            pool.token0_decimals,
            pool.token1_decimals
        )

        # Default to balanced width
        return self.calculate_range_from_price(pool, current_price, 0.20, amount0, amount1)


# ===================== CLI HELPER =====================

def format_result(result: RangeResult) -> str:
    """Format result for human output."""
    lines = [
        f"Range: {result.price_lower:.8f} - {result.price_upper:.8f}",
        f"Ticks: {result.tick_lower} to {result.tick_upper} (current: {result.tick_lower + result.distance_to_lower_ticks})",
        f"In Range: {'✅ YES' if result.in_range else '❌ NO'}",
        f"Deposits: {result.amount0:.6f} token0, {result.amount1:.6f} token1",
        f"Liquidity: {result.liquidity:,}",
        f"Distance to bounds: -{result.distance_to_lower_ticks} / +{result.distance_to_upper_ticks} ticks",
        f"IL Est (1.5x): {result.il_estimate_1x:.2%}",
        f"IL Est (2x): {result.il_estimate_2x:.2%}",
        f"Risk Score: {result.risk_score:.1f}/100",
    ]
    return "\n".join(lines)


# ===================== EXAMPLE USAGE =====================

if __name__ == "__main__":
    # Example: ETH/USDC 0.3% pool on Base
    pool = PoolParams(
        fee_tier=3000,
        tick_spacing=60,
        current_tick=198500,  # ~$3000 ETH
        current_sqrt_price_x96=0x5a00000000000000000000000000000000000000000000000000000000000000,
        liquidity=1000000000000000000,
        token0_decimals=6,   # USDC
        token1_decimals=18,  # WETH
    )

    calc = LPCalculator(DexType.UNISWAP_V3)

    # Calculate ±20% range with $1000 each side
    result = calc.calculate_range_from_price(pool, 3000, 0.20, 1000, 0.33)

    print("=== LP Range Calculation ===")
    print(format_result(result))

    # Find optimal
    print("\n=== Optimal Ranges ===")
    optimal = calc.find_optimal_range(pool, 1000, 0.33)
    for r in optimal[:3]:
        print(f"Width {((r.price_upper-r.price_lower)/r.price_lower)*100:.1f}%: risk={r.risk_score:.1f}, IL_1.5x={r.il_estimate_1x:.2%}")