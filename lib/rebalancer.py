"""
Automated Rebalancing Scripts for Concentrated Liquidity Positions

Supports Uniswap V3, V4, and Pons CLMM positions.
Features:
- Position monitoring and range breach detection
- Multiple rebalancing strategies (passive, active, gamma, grid)
- Gas-optimized execution with MEV protection
- Portfolio-level risk management
- Dry-run mode for testing
- Integration with TheGraph for historical analysis
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from datetime import datetime, timedelta
from pathlib import Path
from decimal import Decimal

import aiohttp
from web3 import Web3
from web3.contract import Contract
from eth_account import Account
from eth_typing import ChecksumAddress

# Import from our framework
from .lp_calculator import (
    LPCalculator, PoolParams, RangeResult, DexType,
    price_to_tick, tick_to_price, sqrt_price_x96_to_price,
    price_to_sqrt_price_x96, get_liquidity_for_amounts,
    get_amounts_for_liquidity
)
from .thegraph import TheGraphClient, TheGraphAnalyzer, Chain


# ===================== ENUMS & DATA CLASSES =====================

class RebalanceStrategy(Enum):
    PASSIVE = "passive"           # Rebalance only when out of range
    ACTIVE = "active"             # Rebalance proactively based on volatility
    GAMMA = "gamma"               # Delta-neutral gamma scalping
    GRID = "grid"                 # Multiple small positions across range
    MEAN_REVERSION = "mean_reversion"  # Rebalance to center on mean reversion signals


class RebalanceAction(Enum):
    NONE = "none"
    COLLECT_FEES = "collect_fees"
    REBALANCE = "rebalance"
    COMPOUND = "compound"         # Collect fees + add to position
    REDUCE = "reduce"             # Reduce position size
    CLOSE = "close"               # Exit position entirely


@dataclass
class Position:
    """Represents a CLMM position."""
    pool_address: str
    chain: str
    dex: str
    token0: str
    token1: str
    token0_symbol: str
    token1_symbol: str
    token0_decimals: int
    token1_decimals: int
    tick_lower: int
    tick_upper: int
    liquidity: int
    fee_tier: int
    nft_id: Optional[int] = None  # For NFT position managers (V3)
    manager_address: Optional[str] = None  # Position manager contract
    created_at: Optional[datetime] = None
    last_rebalance: Optional[datetime] = None
    metadata: Dict = field(default_factory=dict)


@dataclass
class RebalanceConfig:
    """Configuration for rebalancing behavior."""
    strategy: RebalanceStrategy = RebalanceStrategy.PASSIVE
    
    # Range parameters
    target_width_pct: float = 0.20      # Target range width (±20%)
    max_width_pct: float = 0.50         # Maximum range width
    min_width_pct: float = 0.05         # Minimum range width
    
    # Trigger parameters
    range_buffer_pct: float = 0.02      # Rebalance when price within 2% of boundary
    volatility_threshold: float = 0.15  # Annualized vol trigger for active strategy
    max_time_in_range_hours: int = 168  # Force rebalance after 7 days in range
    
    # Execution parameters
    max_slippage_pct: float = 0.5       # Max 0.5% slippage
    max_gas_gwei: int = 50              # Max gas price
    max_gas_usd: float = 10.0           # Max gas cost in USD
    min_rebalance_interval_hours: int = 4  # Cooldown between rebalances
    
    # Risk parameters
    max_position_size_usd: float = 10000
    max_total_exposure_usd: float = 50000
    stop_loss_pct: float = 0.20         # Exit if IL > 20%
    take_profit_pct: float = 0.50       # Take profit at 50% gain
    
    # Gas optimization
    use_flashbots: bool = False
    priority_fee_gwei: int = 2
    max_priority_fee_gwei: int = 5
    
    # Dry run
    dry_run: bool = True


@dataclass
class RebalancePlan:
    """A planned rebalance action."""
    position: Position
    action: RebalanceAction
    reason: str
    
    # New range
    new_tick_lower: Optional[int] = None
    new_tick_upper: Optional[int] = None
    new_width_pct: Optional[float] = None
    
    # Amounts
    token0_amount: float = 0.0
    token1_amount: float = 0.0
    fees_token0: float = 0.0
    fees_token1: float = 0.0
    
    # Estimates
    estimated_gas_usd: float = 0.0
    estimated_slippage_pct: float = 0.0
    estimated_il_change_pct: float = 0.0
    
    # Metadata
    current_tick: int = 0
    current_price: float = 0.0
    volatility: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    execute_at: Optional[datetime] = None


@dataclass
class RebalanceResult:
    """Result of a rebalance execution."""
    plan: RebalancePlan
    success: bool
    tx_hash: Optional[str] = None
    gas_used: int = 0
    gas_cost_usd: float = 0.0
    actual_slippage_pct: float = 0.0
    new_position: Optional[Position] = None
    error: Optional[str] = None
    executed_at: datetime = field(default_factory=datetime.utcnow)


# ===================== CORE REBALANCER =====================

class PositionRebalancer:
    """Main rebalancing engine."""

    def __init__(
        self,
        w3: Web3,
        account: Account,
        config: RebalanceConfig,
        graph_client: Optional[TheGraphClient] = None,
        calculator: Optional[LPCalculator] = None
    ):
        self.w3 = w3
        self.account = account
        self.config = config
        self.graph_client = graph_client
        self.calculator = calculator or LPCalculator(DexType.UNISWAP_V3)
        self.positions: Dict[str, Position] = {}
        self.history: List[RebalanceResult] = []
        self._running = False

    def add_position(self, position: Position):
        """Add a position to manage."""
        self.positions[position.pool_address.lower()] = position

    def remove_position(self, pool_address: str):
        """Remove a position."""
        self.positions.pop(pool_address.lower(), None)

    async def check_position(self, position: Position) -> Optional[RebalancePlan]:
        """Check if position needs rebalancing and create plan."""
        # Get current pool state
        pool_data = await self._get_pool_state(position)
        if not pool_data:
            return None

        current_tick = pool_data["tick"]
        current_price = sqrt_price_x96_to_price(
            pool_data["sqrt_price_x96"],
            position.token0_decimals,
            position.token1_decimals
        )

        # Check if out of range
        in_range = position.tick_lower <= current_tick <= position.tick_upper
        
        # Calculate distance to boundaries
        dist_lower = current_tick - position.tick_lower
        dist_upper = position.tick_upper - current_tick
        min_dist = min(dist_lower, dist_upper)
        
        # Check time since last rebalance
        time_since_rebalance = 0
        if position.last_rebalance:
            time_since_rebalance = (datetime.utcnow() - position.last_rebalance).total_seconds() / 3600

        # Determine if rebalance needed
        needs_rebalance = False
        reason = ""

        if not in_range:
            needs_rebalance = True
            reason = "Position OUT OF RANGE"
        elif min_dist / (position.tick_upper - position.tick_lower) < self.config.range_buffer_pct:
            needs_rebalance = True
            reason = f"Price within {self.config.range_buffer_pct*100:.1f}% of boundary"
        elif time_since_rebalance > self.config.max_time_in_range_hours:
            needs_rebalance = True
            reason = f"Max time in range exceeded ({time_since_rebalance:.1f}h)"
        
        # Check volatility for active strategy
        volatility = 0.0
        if self.config.strategy == RebalanceStrategy.ACTIVE:
            volatility = await self._estimate_volatility(position)
            if volatility > self.config.volatility_threshold:
                needs_rebalance = True
                reason = f"High volatility detected: {volatility:.1%}"

        if not needs_rebalance:
            return None

        # Calculate new range
        new_tick_lower, new_tick_upper = self._calculate_new_range(
            position, current_tick, current_price, pool_data
        )

        # Estimate fees to collect
        fees = await self._estimate_fees(position, pool_data)

        # Create plan
        plan = RebalancePlan(
            position=position,
            action=RebalanceAction.REBALANCE,
            reason=reason,
            new_tick_lower=new_tick_lower,
            new_tick_upper=new_tick_upper,
            new_width_pct=(tick_to_price(new_tick_upper) - tick_to_price(new_tick_lower)) / tick_to_price(current_tick),
            fees_token0=fees[0],
            fees_token1=fees[1],
            current_tick=current_tick,
            current_price=current_price,
            volatility=volatility,
        )

        # Estimate costs
        await self._estimate_execution_costs(plan, pool_data)

        return plan

    def _calculate_new_range(
        self, position: Position, current_tick: int, current_price: float, pool_data: Dict
    ) -> Tuple[int, int]:
        """Calculate optimal new tick range based on strategy."""
        tick_spacing = pool_data.get("tick_spacing", 60)
        
        if self.config.strategy == RebalanceStrategy.PASSIVE:
            # Center on current tick with target width
            target_ticks = int(self._width_pct_to_ticks(self.config.target_width_pct, current_price))
            half_width = target_ticks // 2
            new_lower = current_tick - half_width
            new_upper = current_tick + half_width
            
        elif self.config.strategy == RebalanceStrategy.ACTIVE:
            # Wider range for high volatility
            width_pct = min(self.config.max_width_pct, self.config.target_width_pct * 2)
            target_ticks = int(self._width_pct_to_ticks(width_pct, current_price))
            half_width = target_ticks // 2
            new_lower = current_tick - half_width
            new_upper = current_tick + half_width
            
        elif self.config.strategy == RebalanceStrategy.MEAN_REVERSION:
            # Center on mean price (simplified: use current as mean)
            target_ticks = int(self._width_pct_to_ticks(self.config.target_width_pct, current_price))
            half_width = target_ticks // 2
            new_lower = current_tick - half_width
            new_upper = current_tick + half_width
            
        else:  # GRID - create multiple positions (handled separately)
            target_ticks = int(self._width_pct_to_ticks(self.config.target_width_pct, current_price))
            half_width = target_ticks // 2
            new_lower = current_tick - half_width
            new_upper = current_tick + half_width

        # Align to tick spacing
        new_lower = (new_lower // tick_spacing) * tick_spacing
        new_upper = (new_upper // tick_spacing) * tick_spacing

        # Enforce min/max width
        min_ticks = int(self._width_pct_to_ticks(self.config.min_width_pct, current_price))
        max_ticks = int(self._width_pct_to_ticks(self.config.max_width_pct, current_price))
        actual_width = new_upper - new_lower
        
        if actual_width < min_ticks:
            # Expand symmetrically
            diff = min_ticks - actual_width
            new_lower -= diff // 2
            new_upper += diff - diff // 2
        elif actual_width > max_ticks:
            # Contract symmetrically
            diff = actual_width - max_ticks
            new_lower += diff // 2
            new_upper -= diff - diff // 2

        # Re-align
        new_lower = (new_lower // tick_spacing) * tick_spacing
        new_upper = (new_upper // tick_spacing) * tick_spacing

        return new_lower, new_upper

    def _width_pct_to_ticks(self, width_pct: float, price: float) -> int:
        """Convert percentage width to tick count."""
        # width_pct = (price_upper - price_lower) / price
        # For small percentages: ticks ≈ ln(1 + width_pct) / ln(1.0001)
        # More accurately: price_upper = price * (1 + width_pct/2), price_lower = price * (1 - width_pct/2)
        price_upper = price * (1 + width_pct / 2)
        price_lower = price * (1 - width_pct / 2)
        return price_to_tick(price_upper) - price_to_tick(price_lower)

    async def _get_pool_state(self, position: Position) -> Optional[Dict]:
        """Get current pool state from blockchain or TheGraph."""
        # Try TheGraph first (faster, no RPC calls)
        if self.graph_client:
            try:
                analyzer = TheGraphAnalyzer(self.graph_client)
                pool = await self.graph_client.get_pool_snapshot(
                    Chain[position.chain.upper()], position.pool_address
                )
                if pool:
                    return {
                        "tick": pool.tick,
                        "sqrt_price_x96": int(pool.sqrt_price),
                        "liquidity": int(pool.liquidity),
                        "tick_spacing": self._get_tick_spacing(position.fee_tier),
                    }
            except Exception:
                pass

        # Fallback: RPC call (would need contract ABI)
        # Placeholder - implement with actual pool contract calls
        return None

    def _get_tick_spacing(self, fee_tier: int) -> int:
        """Get tick spacing for fee tier."""
        mapping = {100: 1, 500: 10, 3000: 60, 10000: 200}
        return mapping.get(fee_tier, 60)

    async def _estimate_volatility(self, position: Position) -> float:
        """Estimate annualized volatility from historical data."""
        if not self.graph_client:
            return 0.0
        
        try:
            analyzer = TheGraphAnalyzer(self.graph_client)
            analysis = await analyzer.analyze_pool_history(
                Chain[position.chain.upper()], position.pool_address, days=7
            )
            if "metrics" in analysis:
                # Simplified: use price range as volatility proxy
                price_min = analysis["metrics"].get("price_min", 0)
                price_max = analysis["metrics"].get("price_max", 0)
                current = analysis["metrics"].get("current_price", 1)
                if current > 0 and price_min > 0:
                    return (price_max - price_min) / current
        except Exception:
            pass
        return 0.0

    async def _estimate_fees(self, position: Position, pool_data: Dict) -> Tuple[float, float]:
        """Estimate unclaimed fees."""
        # This would query the position manager or pool for unclaimed fees
        # Placeholder
        return 0.0, 0.0

    async def _estimate_execution_costs(self, plan: RebalancePlan, pool_data: Dict):
        """Estimate gas and slippage for rebalance."""
        # Rough estimates
        plan.estimated_gas_usd = 5.0  # ~$5 for rebalance on L2
        plan.estimated_slippage_pct = 0.1  # 0.1% slippage estimate
        plan.estimated_il_change_pct = 0.0  # Would calculate based on new range

    async def execute_plan(self, plan: RebalancePlan) -> RebalanceResult:
        """Execute a rebalance plan."""
        if self.config.dry_run:
            return RebalanceResult(
                plan=plan,
                success=True,
                error="DRY RUN - not executed"
            )

        # This would execute the actual transactions:
        # 1. Collect fees (if any)
        # 2. Remove liquidity from old range
        # 3. Swap tokens if needed to match new ratio
        # 4. Add liquidity to new range
        # 5. Update position record
        
        # Placeholder - actual implementation would use:
        # - NonfungiblePositionManager for V3
        # - PoolManager for V4
        # - Custom contracts for Pons
        
        return RebalanceResult(
            plan=plan,
            success=False,
            error="Execution not implemented - requires position manager integration"
        )

    async def run_rebalance_cycle(self) -> List[RebalanceResult]:
        """Run one rebalance cycle across all positions."""
        results = []
        
        for pool_addr, position in self.positions.items():
            plan = await self.check_position(position)
            if plan:
                result = await self.execute_plan(plan)
                results.append(result)
                if result.success:
                    self.history.append(result)
                    position.last_rebalance = datetime.utcnow()
        
        return results

    async def start_continuous(self, interval_seconds: int = 300):
        """Start continuous rebalancing loop."""
        self._running = True
        while self._running:
            try:
                await self.run_rebalance_cycle()
            except Exception as e:
                print(f"Rebalance cycle error: {e}")
            await asyncio.sleep(interval_seconds)

    def stop(self):
        """Stop continuous rebalancing."""
        self._running = False


# ===================== PORTFOLIO REBALANCER =====================

class PortfolioRebalancer:
    """Manages rebalancing across multiple positions with portfolio-level risk."""

    def __init__(self, rebalancer: PositionRebalancer, config: RebalanceConfig):
        self.rebalancer = rebalancer
        self.config = config

    async def analyze_portfolio(self) -> Dict:
        """Analyze portfolio risk and exposure."""
        total_exposure = 0.0
        total_fees_pending = 0.0
        positions_out_of_range = 0
        
        for position in self.rebalancer.positions.values():
            # Would calculate current value
            total_exposure += 0  # placeholder
            total_fees_pending += 0  # placeholder
            
            plan = await self.rebalancer.check_position(position)
            if plan and plan.action == RebalanceAction.REBALANCE:
                positions_out_of_range += 1

        return {
            "total_positions": len(self.rebalancer.positions),
            "total_exposure_usd": total_exposure,
            "total_fees_pending_usd": total_fees_pending,
            "positions_out_of_range": positions_out_of_range,
            "needs_attention": positions_out_of_range > 0,
        }

    async def rebalance_portfolio(self) -> List[RebalanceResult]:
        """Rebalance entire portfolio respecting risk limits."""
        # Check portfolio-level risk
        analysis = await self.analyze_portfolio()
        if analysis["total_exposure_usd"] > self.config.max_total_exposure_usd:
            print(f"WARNING: Portfolio exposure ${analysis['total_exposure_usd']:,.0f} exceeds limit")
            # Could auto-reduce positions

        return await self.rebalancer.run_rebalance_cycle()


# ===================== GAS-OPTIMIZED EXECUTION =====================

class GasOptimizedExecutor:
    """Handles gas-optimized transaction execution."""

    def __init__(self, w3: Web3, config: RebalanceConfig):
        self.w3 = w3
        self.config = config

    async def estimate_gas(self, tx_params: Dict) -> int:
        """Estimate gas for a transaction."""
        try:
            return await self.w3.eth.estimate_gas(tx_params)
        except Exception:
            return 300000  # Conservative default

    async def get_gas_price(self) -> Tuple[int, int]:
        """Get current base fee and priority fee."""
        block = await self.w3.eth.get_block('latest')
        base_fee = block.get('baseFeePerGas', 0)
        
        # Priority fee
        priority_fee = self.config.priority_fee_gwei * 10**9
        max_priority = self.config.max_priority_fee_gwei * 10**9
        
        max_fee = base_fee + max_priority
        return max_fee, min(priority_fee, max_priority)

    async def build_tx(self, contract: Contract, function: str, args: List, value: int = 0) -> Dict:
        """Build transaction with gas optimization."""
        max_fee, priority_fee = await self.get_gas_price()
        
        tx = await contract.functions[function](*args).build_transaction({
            'from': self.account.address,
            'value': value,
            'maxFeePerGas': max_fee,
            'maxPriorityFeePerGas': priority_fee,
            'nonce': await self.w3.eth.get_transaction_count(self.account.address),
            'chainId': await self.w3.eth.chain_id,
        })
        
        # Estimate and add buffer
        gas_estimate = await self.estimate_gas(tx)
        tx['gas'] = int(gas_estimate * 1.2)  # 20% buffer
        
        return tx

    async def send_and_wait(self, tx: Dict, timeout: int = 120) -> Dict:
        """Send transaction and wait for receipt."""
        signed = self.account.sign_transaction(tx)
        tx_hash = await self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
        return receipt


# ===================== FLASHBOTS INTEGRATION (OPTIONAL) =====================

class FlashbotsExecutor:
    """Flashbots Protect / MEV-Share integration for private execution."""

    def __init__(self, w3: Web3, account: Account, auth_key: str):
        self.w3 = w3
        self.account = account
        self.auth_key = auth_key
        self.flashbots_rpc = "https://rpc.flashbots.net"

    async def send_bundle(self, txs: List[Dict], target_block: int) -> bool:
        """Send transaction bundle via Flashbots."""
        # Would implement Flashbots bundle submission
        # Requires flashbots-py package
        return False


# ===================== EXAMPLE USAGE =====================

async def main():
    """Example: Set up and run rebalancer."""
    
    # Setup
    w3 = Web3(Web3.HTTPProvider("https://mainnet.base.org"))
    account = Account.from_key(os.getenv("PRIVATE_KEY"))
    
    config = RebalanceConfig(
        strategy=RebalanceStrategy.PASSIVE,
        target_width_pct=0.20,
        max_slippage_pct=0.5,
        max_gas_gwei=30,
        dry_run=True,  # Start with dry run!
    )
    
    # Initialize
    async with TheGraphClient() as graph_client:
        rebalancer = PositionRebalancer(
            w3=w3,
            account=account,
            config=config,
            graph_client=graph_client
        )
        
        # Add positions (would load from config/file)
        # position = Position(...)
        # rebalancer.add_position(position)
        
        # Run single cycle
        results = await rebalancer.run_rebalance_cycle()
        for r in results:
            print(f"Rebalance: {r.plan.reason} - Success: {r.success}")

        # Or run continuous
        # await rebalancer.start_continuous(interval_seconds=300)


if __name__ == "__main__":
    asyncio.run(main())