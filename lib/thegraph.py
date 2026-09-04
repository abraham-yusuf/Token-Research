"""
TheGraph Subgraph Integration

Queries Uniswap V3/V4 subgraphs across multiple chains for:
- Pool historical data (liquidity, volume, fees)
- Token prices and volume
- Pool creation events
- Position snapshots
- Fee revenue tracking
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import aiohttp


class Chain(Enum):
    ETHEREUM = "ethereum"
    BASE = "base"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    POLYGON = "polygon"
    BSC = "bsc"
    AVALANCHE = "avalanche"


class SubgraphEndpoint(Enum):
    """Known Uniswap V3 subgraph endpoints."""
    ETHEREUM = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3"
    BASE = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3-base"
    ARBITRUM = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3-arbitrum"
    OPTIMISM = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3-optimism"
    POLYGON = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3-polygon"
    # Community deployments
    ETHEREUM_V2 = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v2"
    BASE_V2 = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v2-base"


# GraphQL Queries
POOL_DAY_DATA_QUERY = """
query PoolDayData($poolId: ID!, $startTime: Int!, $endTime: Int!) {
  poolDayDatas(
    where: { pool: $poolId, date_gte: $startTime, date_lte: $endTime }
    orderBy: date
    orderDirection: asc
    first: 1000
  ) {
    date
    sqrtPrice
    liquidity
    volumeUSD
    feesUSD
    tvlUSD
    token0Price
    token1Price
    txCount
    open
    high
    low
    close
  }
}
"""

POOL_HOURLY_DATA_QUERY = """
query PoolHourData($poolId: ID!, $startTime: Int!, $endTime: Int!) {
  poolHourDatas(
    where: { pool: $poolId, periodStartUnix_gte: $startTime, periodStartUnix_lte: $endTime }
    orderBy: periodStartUnix
    orderDirection: asc
    first: 1000
  ) {
    periodStartUnix
    sqrtPrice
    liquidity
    volumeUSD
    feesUSD
    tvlUSD
    token0Price
    token1Price
    txCount
    open
    high
    low
    close
  }
}
"""

POOL_SNAPSHOT_QUERY = """
query PoolSnapshot($poolId: ID!) {
  pool(id: $poolId) {
    id
    token0 { id symbol name decimals }
    token1 { id symbol name decimals }
    feeTier
    liquidity
    sqrtPrice
    tick
    token0Price
    token1Price
    volumeUSD
    feesUSD
    tvlUSD
    totalValueLockedToken0
    totalValueLockedToken1
    token0Volume
    token1Volume
    createdAtTimestamp
    poolDayData(first: 30, orderBy: date, orderDirection: desc) {
      date
      volumeUSD
      feesUSD
      tvlUSD
      liquidity
    }
  }
}
"""

POOLS_BY_TOKEN_QUERY = """
query PoolsByToken($token: ID!, $minTvl: Float!, $first: Int!) {
  pools(
    where: { token0: $token, tvlUSD_gt: $minTvl }
    orderBy: tvlUSD
    orderDirection: desc
    first: $first
  ) {
    id
    token0 { id symbol name decimals }
    token1 { id symbol name decimals }
    feeTier
    liquidity
    sqrtPrice
    tick
    volumeUSD
    feesUSD
    tvlUSD
    token0Price
    token1Price
    createdAtTimestamp
  }
}
"""

TOKEN_DAY_DATA_QUERY = """
query TokenDayData($tokenId: ID!, $startTime: Int!, $endTime: Int!) {
  tokenDayDatas(
    where: { token: $tokenId, date_gte: $startTime, date_lte: $endTime }
    orderBy: date
    orderDirection: asc
    first: 1000
  ) {
    date
    priceUSD
    volumeUSD
    totalLiquidity
    derivedETH
  }
}
"""

NEW_POOLS_QUERY = """
query NewPools($factory: ID!, $startTime: Int!, $minTvl: Float!, $first: Int!) {
  pools(
    where: { factory: $factory, createdAtTimestamp_gte: $startTime, tvlUSD_gt: $minTvl }
    orderBy: createdAtTimestamp
    orderDirection: desc
    first: $first
  ) {
    id
    token0 { id symbol name decimals }
    token1 { id symbol name decimals }
    feeTier
    liquidity
    sqrtPrice
    tick
    volumeUSD
    feesUSD
    tvlUSD
    token0Price
    token1Price
    createdAtTimestamp
  }
}
"""

SWAP_EVENTS_QUERY = """
query Swaps($poolId: ID!, $startTime: Int!, $endTime: Int!, $first: Int!) {
  swaps(
    where: { pool: $poolId, timestamp_gte: $startTime, timestamp_lte: $endTime }
    orderBy: timestamp
    orderDirection: asc
    first: $first
  ) {
    id
    timestamp
    amount0
    amount1
    amountUSD
    sqrtPriceX96
    tick
    sender
    to
  }
}
"""

MINT_EVENTS_QUERY = """
query Mints($poolId: ID!, $startTime: Int!, $first: Int!) {
  mints(
    where: { pool: $poolId, timestamp_gte: $startTime }
    orderBy: timestamp
    orderDirection: desc
    first: $first
  ) {
    id
    timestamp
    amount0
    amount1
    amountUSD
    tickLower
    tickUpper
    sender
    owner
  }
}
"""

BURN_EVENTS_QUERY = """
query Burns($poolId: ID!, $startTime: Int!, $first: Int!) {
  burns(
    where: { pool: $poolId, timestamp_gte: $startTime }
    orderBy: timestamp
    orderDirection: desc
    first: $first
  ) {
    id
    timestamp
    amount0
    amount1
    amountUSD
    tickLower
    tickUpper
    sender
    owner
  }
}
"""

COLLECT_EVENTS_QUERY = """
query Collects($poolId: ID!, $startTime: Int!, $first: Int!) {
  collects(
    where: { pool: $poolId, timestamp_gte: $startTime }
    orderBy: timestamp
    orderDirection: desc
    first: $first
  ) {
    id
    timestamp
    amount0
    amount1
    tickLower
    tickUpper
    sender
    owner
  }
}
"""


@dataclass
class PoolDayData:
    date: int
    sqrt_price: str
    liquidity: str
    volume_usd: float
    fees_usd: float
    tvl_usd: float
    token0_price: float
    token1_price: float
    tx_count: int
    open: float
    high: float
    low: float
    close: float


@dataclass
class PoolSnapshot:
    id: str
    token0: Dict
    token1: Dict
    fee_tier: int
    liquidity: str
    sqrt_price: str
    tick: int
    token0_price: float
    token1_price: float
    volume_usd: float
    fees_usd: float
    tvl_usd: float
    token0_volume: float
    token1_volume: float
    created_at: int
    day_data: List[PoolDayData]


@dataclass
class PoolInfo:
    id: str
    token0: Dict
    token1: Dict
    fee_tier: int
    liquidity: str
    sqrt_price: str
    tick: int
    volume_usd: float
    fees_usd: float
    tvl_usd: float
    token0_price: float
    token1_price: float
    created_at: int


@dataclass
class SwapEvent:
    id: str
    timestamp: int
    amount0: str
    amount1: str
    amount_usd: float
    sqrt_price_x96: str
    tick: int
    sender: str
    to: str


@dataclass
class PositionEvent:
    id: str
    timestamp: int
    amount0: str
    amount1: str
    amount_usd: float
    tick_lower: int
    tick_upper: int
    sender: str
    owner: str


class TheGraphClient:
    """Async client for querying TheGraph subgraphs."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("THEGRAPH_API_KEY")
        self.session: Optional[aiohttp.ClientSession] = None
        self.endpoints = {
            Chain.ETHEREUM: SubgraphEndpoint.ETHEREUM.value,
            Chain.BASE: SubgraphEndpoint.BASE.value,
            Chain.ARBITRUM: SubgraphEndpoint.ARBITRUM.value,
            Chain.OPTIMISM: SubgraphEndpoint.OPTIMISM.value,
            Chain.POLYGON: SubgraphEndpoint.POLYGON.value,
        }
        self._rate_limit_semaphore = asyncio.Semaphore(5)  # Max 5 concurrent

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Content-Type": "application/json"}
        )
        if self.api_key:
            self.session.headers["Authorization"] = f"Bearer {self.api_key}"
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    def _get_endpoint(self, chain: Chain) -> str:
        return self.endpoints.get(chain, SubgraphEndpoint.ETHEREUM.value)

    async def _query(self, chain: Chain, query: str, variables: Dict) -> Dict:
        """Execute a GraphQL query."""
        async with self._rate_limit_semaphore:
            endpoint = self._get_endpoint(chain)
            payload = {"query": query, "variables": variables}
            
            async with self.session.post(endpoint, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"TheGraph error {resp.status}: {text}")
                
                data = await resp.json()
                if "errors" in data:
                    raise Exception(f"GraphQL errors: {data['errors']}")
                
                return data.get("data", {})

    async def get_pool_snapshot(self, chain: Chain, pool_id: str) -> Optional[PoolSnapshot]:
        """Get current pool state + recent day data."""
        data = await self._query(chain, POOL_SNAPSHOT_QUERY, {"poolId": pool_id.lower()})
        pool = data.get("pool")
        if not pool:
            return None

        day_data = [
            PoolDayData(
                date=d["date"],
                sqrt_price=d["sqrtPrice"],
                liquidity=d["liquidity"],
                volume_usd=float(d["volumeUSD"]),
                fees_usd=float(d["feesUSD"]),
                tvl_usd=float(d["tvlUSD"]),
                token0_price=float(d["token0Price"]),
                token1_price=float(d["token1Price"]),
                tx_count=int(d.get("txCount", 0)),
                open=float(d.get("open", 0)),
                high=float(d.get("high", 0)),
                low=float(d.get("low", 0)),
                close=float(d.get("close", 0)),
            )
            for d in pool.get("poolDayData", [])
        ]

        return PoolSnapshot(
            id=pool["id"],
            token0=pool["token0"],
            token1=pool["token1"],
            fee_tier=int(pool["feeTier"]),
            liquidity=pool["liquidity"],
            sqrt_price=pool["sqrtPrice"],
            tick=int(pool["tick"]),
            token0_price=float(pool["token0Price"]),
            token1_price=float(pool["token1Price"]),
            volume_usd=float(pool["volumeUSD"]),
            fees_usd=float(pool["feesUSD"]),
            tvl_usd=float(pool["tvlUSD"]),
            token0_volume=float(pool.get("token0Volume", 0)),
            token1_volume=float(pool.get("token1Volume", 0)),
            created_at=int(pool["createdAtTimestamp"]),
            day_data=day_data,
        )

    async def get_pool_day_data(
        self, chain: Chain, pool_id: str, days: int = 30
    ) -> List[PoolDayData]:
        """Get historical daily data for a pool."""
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - (days * 86400)

        data = await self._query(chain, POOL_DAY_DATA_QUERY, {
            "poolId": pool_id.lower(),
            "startTime": start_time,
            "endTime": end_time,
        })

        return [
            PoolDayData(
                date=d["date"],
                sqrt_price=d["sqrtPrice"],
                liquidity=d["liquidity"],
                volume_usd=float(d["volumeUSD"]),
                fees_usd=float(d["feesUSD"]),
                tvl_usd=float(d["tvlUSD"]),
                token0_price=float(d["token0Price"]),
                token1_price=float(d["token1Price"]),
                tx_count=int(d.get("txCount", 0)),
                open=float(d.get("open", 0)),
                high=float(d.get("high", 0)),
                low=float(d.get("low", 0)),
                close=float(d.get("close", 0)),
            )
            for d in data.get("poolDayDatas", [])
        ]

    async def get_pool_hour_data(
        self, chain: Chain, pool_id: str, hours: int = 168
    ) -> List[Dict]:
        """Get hourly data for a pool (last 7 days default)."""
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - (hours * 3600)

        data = await self._query(chain, POOL_HOURLY_DATA_QUERY, {
            "poolId": pool_id.lower(),
            "startTime": start_time,
            "endTime": end_time,
        })

        return data.get("poolHourDatas", [])

    async def get_pools_by_token(
        self, chain: Chain, token_address: str, min_tvl: float = 10000, limit: int = 20
    ) -> List[PoolInfo]:
        """Find pools for a token with TVL > min_tvl."""
        data = await self._query(chain, POOLS_BY_TOKEN_QUERY, {
            "token": token_address.lower(),
            "minTvl": min_tvl,
            "first": limit,
        })

        return [
            PoolInfo(
                id=p["id"],
                token0=p["token0"],
                token1=p["token1"],
                fee_tier=int(p["feeTier"]),
                liquidity=p["liquidity"],
                sqrt_price=p["sqrtPrice"],
                tick=int(p["tick"]),
                volume_usd=float(p["volumeUSD"]),
                fees_usd=float(p["feesUSD"]),
                tvl_usd=float(p["tvlUSD"]),
                token0_price=float(p["token0Price"]),
                token1_price=float(p["token1Price"]),
                created_at=int(p["createdAtTimestamp"]),
            )
            for p in data.get("pools", [])
        ]

    async def get_new_pools(
        self, chain: Chain, factory_address: str, hours: int = 24,
        min_tvl: float = 10000, limit: int = 50
    ) -> List[PoolInfo]:
        """Get newly created pools from a factory."""
        start_time = int((datetime.utcnow() - timedelta(hours=hours)).timestamp())

        data = await self._query(chain, NEW_POOLS_QUERY, {
            "factory": factory_address.lower(),
            "startTime": start_time,
            "minTvl": min_tvl,
            "first": limit,
        })

        return [
            PoolInfo(
                id=p["id"],
                token0=p["token0"],
                token1=p["token1"],
                fee_tier=int(p["feeTier"]),
                liquidity=p["liquidity"],
                sqrt_price=p["sqrtPrice"],
                tick=int(p["tick"]),
                volume_usd=float(p["volumeUSD"]),
                fees_usd=float(p["feesUSD"]),
                tvl_usd=float(p["tvlUSD"]),
                token0_price=float(p["token0Price"]),
                token1_price=float(p["token1Price"]),
                created_at=int(p["createdAtTimestamp"]),
            )
            for p in data.get("pools", [])
        ]

    async def get_token_day_data(
        self, chain: Chain, token_address: str, days: int = 30
    ) -> List[Dict]:
        """Get historical token price/volume data."""
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - (days * 86400)

        data = await self._query(chain, TOKEN_DAY_DATA_QUERY, {
            "tokenId": token_address.lower(),
            "startTime": start_time,
            "endTime": end_time,
        })

        return data.get("tokenDayDatas", [])

    async def get_swaps(
        self, chain: Chain, pool_id: str, hours: int = 24, limit: int = 1000
    ) -> List[SwapEvent]:
        """Get recent swaps for a pool."""
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - (hours * 3600)

        data = await self._query(chain, SWAP_EVENTS_QUERY, {
            "poolId": pool_id.lower(),
            "startTime": start_time,
            "endTime": int(datetime.utcnow().timestamp()),
            "first": limit,
        })

        return [
            SwapEvent(
                id=s["id"],
                timestamp=int(s["timestamp"]),
                amount0=s["amount0"],
                amount1=s["amount1"],
                amount_usd=float(s["amountUSD"]),
                sqrt_price_x96=s["sqrtPriceX96"],
                tick=int(s["tick"]),
                sender=s["sender"],
                to=s["to"],
            )
            for s in data.get("swaps", [])
        ]

    async def get_mints(self, chain: Chain, pool_id: str, hours: int = 168, limit: int = 100) -> List[PositionEvent]:
        """Get recent mint events (LP additions)."""
        start_time = int((datetime.utcnow() - timedelta(hours=hours)).timestamp())

        data = await self._query(chain, MINT_EVENTS_QUERY, {
            "poolId": pool_id.lower(),
            "startTime": start_time,
            "first": limit,
        })

        return [
            PositionEvent(
                id=m["id"],
                timestamp=int(m["timestamp"]),
                amount0=m["amount0"],
                amount1=m["amount1"],
                amount_usd=float(m["amountUSD"]),
                tick_lower=int(m["tickLower"]),
                tick_upper=int(m["tickUpper"]),
                sender=m["sender"],
                owner=m["owner"],
            )
            for m in data.get("mints", [])
        ]

    async def get_burns(self, chain: Chain, pool_id: str, hours: int = 168, limit: int = 100) -> List[PositionEvent]:
        """Get recent burn events (LP removals)."""
        start_time = int((datetime.utcnow() - timedelta(hours=hours)).timestamp())

        data = await self._query(chain, BURN_EVENTS_QUERY, {
            "poolId": pool_id.lower(),
            "startTime": start_time,
            "first": limit,
        })

        return [
            PositionEvent(
                id=b["id"],
                timestamp=int(b["timestamp"]),
                amount0=b["amount0"],
                amount1=b["amount1"],
                amount_usd=float(b["amountUSD"]),
                tick_lower=int(b["tickLower"]),
                tick_upper=int(b["tickUpper"]),
                sender=b["sender"],
                owner=b["owner"],
            )
            for b in data.get("burns", [])
        ]

    async def get_collects(self, chain: Chain, pool_id: str, hours: int = 168, limit: int = 100) -> List[PositionEvent]:
        """Get recent fee collect events."""
        start_time = int((datetime.utcnow() - timedelta(hours=hours)).timestamp())

        data = await self._query(chain, COLLECT_EVENTS_QUERY, {
            "poolId": pool_id.lower(),
            "startTime": start_time,
            "first": limit,
        })

        return [
            PositionEvent(
                id=c["id"],
                timestamp=int(c["timestamp"]),
                amount0=c["amount0"],
                amount1=c["amount1"],
                amount_usd=0.0,  # Collects don't have USD in subgraph
                tick_lower=int(c["tickLower"]),
                tick_upper=int(c["tickUpper"]),
                sender=c["sender"],
                owner=c["owner"],
            )
            for c in data.get("collects", [])
        ]


# ===================== FACTORY ADDRESSES =====================

UNISWAP_V3_FACTORIES = {
    Chain.ETHEREUM: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    Chain.BASE: "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
    Chain.ARBITRUM: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    Chain.OPTIMISM: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    Chain.POLYGON: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
}

UNISWAP_V2_FACTORIES = {
    Chain.ETHEREUM: "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
    Chain.BASE: "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6",
    Chain.ARBITRUM: "0xFA61Ab25b8C03A4f9aA5dA4C0f46059d1A8C87d3",
}


# ===================== HIGH-LEVEL HELPERS =====================

class TheGraphAnalyzer:
    """High-level analysis helpers using TheGraph."""

    def __init__(self, client: TheGraphClient):
        self.client = client

    async def analyze_pool_history(
        self, chain: Chain, pool_address: str, days: int = 30
    ) -> Dict:
        """Comprehensive pool analysis."""
        pool = await self.client.get_pool_snapshot(chain, pool_address)
        if not pool:
            return {"error": "Pool not found"}

        day_data = await self.client.get_pool_day_data(chain, pool_address, days)
        swaps = await self.client.get_swaps(chain, pool_address, hours=24*7)
        mints = await self.client.get_mints(chain, pool_address, hours=24*7)
        burns = await self.client.get_burns(chain, pool_address, hours=24*7)
        collects = await self.client.get_collects(chain, pool_address, hours=24*7)

        # Calculate metrics
        total_volume_7d = sum(d.volume_usd for d in day_data[-7:])
        total_fees_7d = sum(d.fees_usd for d in day_data[-7:])
        avg_tvl_7d = sum(d.tvl_usd for d in day_data[-7:]) / max(len(day_data[-7:]), 1)
        fee_apr = (total_fees_7d / avg_tvl_7d * 365 / 7 * 100) if avg_tvl_7d > 0 else 0

        # Price range
        prices = [d.close for d in day_data if d.close > 0]
        price_min = min(prices) if prices else 0
        price_max = max(prices) if prices else 0
        price_change = ((prices[-1] - prices[0]) / prices[0] * 100) if len(prices) >= 2 else 0

        # Swap analysis
        total_swaps = len(swaps)
        buy_volume = sum(s.amount_usd for s in swaps if float(s.amount1) > 0)  # token1 bought
        sell_volume = sum(s.amount_usd for s in swaps if float(s.amount0) > 0)  # token0 bought

        # Position activity
        total_mints = len(mints)
        total_burns = len(burns)
        total_collects = len(collects)
        mint_volume = sum(m.amount_usd for m in mints)
        burn_volume = sum(b.amount_usd for b in burns)
        collect_fees = sum(c.amount_usd for c in collects)  # This is 0 in subgraph

        return {
            "pool": asdict(pool),
            "period_days": len(day_data),
            "metrics": {
                "volume_7d_usd": total_volume_7d,
                "fees_7d_usd": total_fees_7d,
                "avg_tvl_7d_usd": avg_tvl_7d,
                "fee_apr_pct": fee_apr,
                "price_change_pct": price_change,
                "price_min": price_min,
                "price_max": price_max,
                "current_price": pool.token1_price,
            },
            "swap_activity": {
                "total_swaps_7d": total_swaps,
                "buy_volume_usd": buy_volume,
                "sell_volume_usd": sell_volume,
                "buy_sell_ratio": buy_volume / sell_volume if sell_volume > 0 else 0,
            },
            "position_activity": {
                "mints": total_mints,
                "burns": total_burns,
                "collects": total_collects,
                "mint_volume_usd": mint_volume,
                "burn_volume_usd": burn_volume,
                "net_liquidity_usd": mint_volume - burn_volume,
            },
            "daily_data": [asdict(d) for d in day_data],
        }

    async def find_profitable_pools(
        self, chain: Chain, token_address: str,
        min_fee_apr: float = 20, min_tvl: float = 50000
    ) -> List[Dict]:
        """Find pools for a token with good fee APR."""
        pools = await self.client.get_pools_by_token(chain, token_address, min_tvl=min_tvl)
        
        results = []
        for pool in pools:
            analysis = await self.analyze_pool_history(chain, pool.id, days=7)
            if "error" not in analysis:
                apr = analysis["metrics"]["fee_apr_pct"]
                if apr >= min_fee_apr:
                    results.append({
                        "pool": pool.id,
                        "fee_tier": pool.fee_tier,
                        "tvl_usd": pool.tvl_usd,
                        "volume_7d": analysis["metrics"]["volume_7d_usd"],
                        "fee_apr": apr,
                        "price_change_7d": analysis["metrics"]["price_change_pct"],
                    })
        
        return sorted(results, key=lambda x: x["fee_apr"], reverse=True)

    async def get_new_pool_alerts(
        self, chain: Chain, hours: int = 24, min_tvl: float = 20000
    ) -> List[Dict]:
        """Get newly deployed pools with decent TVL."""
        factory = UNISWAP_V3_FACTORIES.get(chain)
        if not factory:
            return []
        
        pools = await self.client.get_new_pools(chain, factory, hours, min_tvl)
        
        return [
            {
                "pool": p.id,
                "token0": p.token0["symbol"],
                "token1": p.token1["symbol"],
                "fee_tier": p.fee_tier / 10000,
                "tvl_usd": p.tvl_usd,
                "created_at": datetime.fromtimestamp(p.created_at).isoformat(),
                "age_hours": (datetime.utcnow().timestamp() - p.created_at) / 3600,
            }
            for p in pools
        ]


# ===================== EXAMPLE USAGE =====================

async def main():
    # Requires THEGRAPH_API_KEY in env
    async with TheGraphClient() as client:
        analyzer = TheGraphAnalyzer(client)

        # Example: Analyze USDC/WETH 0.3% pool on Base
        # Pool: 0x... (get from Uniswap UI or factory)
        # pool_address = "0x..."
        # analysis = await analyzer.analyze_pool_history(Chain.BASE, pool_address, days=30)
        # print(json.dumps(analysis, indent=2))

        # Find new pools on Base
        # new_pools = await analyzer.get_new_pool_alerts(Chain.BASE, hours=24)
        # print(json.dumps(new_pools, indent=2))

        print("TheGraph client ready. Set THEGRAPH_API_KEY and run queries.")


if __name__ == "__main__":
    asyncio.run(main())