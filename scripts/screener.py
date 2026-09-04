#!/usr/bin/env python3
"""
Token Screener — Multi-chain, Multi-DEX New Pair Discovery

Usage:
  python screener.py --chain base --dex uniswap_v3 --min-liq 50000 --max-age 24h
  python screener.py --chain robinhood --dex uniswap_v4 --output output/base_v4.json
  python screener.py --all-chains --min-score 70
"""

import asyncio
import json
import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

import aiohttp
import aiofiles

# ===================== CONFIG =====================

CHAIN_CONFIG = {
    "ethereum": {
        "rpc": "https://eth.llamarpc.com",
        "explorer_api": "https://api.etherscan.io/api",
        "native": "WETH",
        "weth": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "uniswap_v3_factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "uniswap_v3_quoter": "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
    },
    "base": {
        "rpc": "https://mainnet.base.org",
        "explorer_api": "https://api.basescan.org/api",
        "native": "WETH",
        "weth": "0x4200000000000000000000000000000000000006",
        "uniswap_v3_factory": "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
        "uniswap_v3_quoter": "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
    },
    "arbitrum": {
        "rpc": "https://arb1.arbitrum.io/rpc",
        "explorer_api": "https://api.arbiscan.io/api",
        "native": "WETH",
        "weth": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "uniswap_v3_factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    },
    "optimism": {
        "rpc": "https://mainnet.optimism.io",
        "explorer_api": "https://api-optimistic.etherscan.io/api",
        "native": "WETH",
        "weth": "0x4200000000000000000000000000000000000006",
        "uniswap_v3_factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    },
    "polygon": {
        "rpc": "https://polygon-rpc.com",
        "explorer_api": "https://api.polygonscan.com/api",
        "native": "WMATIC",
        "weth": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
        "uniswap_v3_factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    },
    "robinhood": {
        "rpc": "https://rpc.robinhood.com",  # placeholder - needs real endpoint
        "explorer_api": "https://api.robinhoodscan.com/api",
        "native": "WETH",
        "weth": "0x...",
        "uniswap_v4_factory": "0x...",  # Uniswap V4 uses PoolManager
    },
    "bsc": {
        "rpc": "https://bsc-dataseed.binance.org",
        "explorer_api": "https://api.bscscan.com/api",
        "native": "WBNB",
        "weth": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        "pancake_v3_factory": "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
    },
    "avalanche": {
        "rpc": "https://api.avax.network/ext/bc/C/rpc",
        "explorer_api": "https://api.snowtrace.io/api",
        "native": "WAVAX",
        "weth": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7",
        "trader_joe_v3_factory": "0x...",
    },
}

DEX_CONFIG = {
    "uniswap_v3": {
        "factory_abi": [
            {"inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
             "name": "getPool", "outputs": [{"internalType": "address", "name": "", "type": "address"}],
             "stateMutability": "view", "type": "function"},
            {"anonymous": False, "inputs": [
                {"indexed": True, "internalType": "address", "name": "token0", "type": "address"},
                {"indexed": True, "internalType": "address", "name": "token1", "type": "address"},
                {"indexed": True, "internalType": "uint24", "name": "fee", "type": "uint24"},
                {"indexed": False, "internalType": "int24", "name": "tickSpacing", "type": "int24"},
                {"indexed": False, "internalType": "address", "name": "pool", "type": "address"}],
             "name": "PoolCreated", "type": "event"}
        ],
        "pool_abi": [
            {"inputs": [], "name": "slot0", "outputs": [
                {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
                {"internalType": "int24", "name": "tick", "type": "int24"},
                {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
                {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
                {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
                {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
                {"internalType": "bool", "name": "unlocked", "type": "bool"}],
             "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "liquidity", "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
             "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "token0", "outputs": [{"internalType": "address", "name": "", "type": "address"}],
             "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "token1", "outputs": [{"internalType": "address", "name": "", "type": "address"}],
             "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "fee", "outputs": [{"internalType": "uint24", "name": "", "type": "uint24"}],
             "stateMutability": "view", "type": "function"},
        ],
        "fee_tiers": [100, 500, 3000, 10000],  # 0.01%, 0.05%, 0.3%, 1%
    },
    "uniswap_v4": {
        # Uniswap V4 uses PoolManager + hooks, different architecture
        # Placeholder for when V4 is live on target chains
    },
    "pancake_v3": {
        "factory_abi": [],  # Similar to Uniswap V3
        "pool_abi": [],
    },
}

# ===================== DATA CLASSES =====================

@dataclass
class PoolInfo:
    address: str
    token0: str
    token1: str
    fee: int
    tick_spacing: int
    liquidity: int
    sqrt_price_x96: int
    tick: int
    token0_symbol: str = ""
    token1_symbol: str = ""
    token0_decimals: int = 18
    token1_decimals: int = 18
    volume_24h: float = 0.0
    tvl_usd: float = 0.0
    created_at: Optional[datetime] = None

@dataclass
class TokenInfo:
    address: str
    symbol: str
    name: str
    decimals: int
    total_supply: int
    holder_count: int
    top_holders: List[Dict]  # [{"address": "", "balance": "", "pct": 0.0}]

@dataclass
class ScreenerResult:
    token: str
    address: str
    chain: str
    dex: str
    pair: str
    pool_address: str
    score: int
    tier: str
    checks: Dict[str, int]
    flags: List[str]
    liquidity_usd: float
    locked_liquidity_pct: float
    volume_24h: float
    fee_tier: float
    holder_count: int
    top10_pct: float
    recommendation: str
    timestamp: str
    tick_lower: int
    tick_upper: int
    current_tick: int

# ===================== UTILITIES =====================

def load_env():
    from dotenv import load_dotenv
    load_dotenv()

def get_rpc_url(chain: str) -> str:
    return CHAIN_CONFIG.get(chain, {}).get("rpc", "")

def get_explorer_api(chain: str) -> str:
    return CHAIN_CONFIG.get(chain, {}).get("explorer_api", "")

async def rpc_call(session: aiohttp.ClientSession, rpc_url: str, method: str, params: List) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    async with session.post(rpc_url, json=payload) as resp:
        data = await resp.json()
        if "error" in data:
            raise Exception(f"RPC error: {data['error']}")
        return data["result"]

async def eth_call(session: aiohttp.ClientSession, rpc_url: str, to: str, data: str, block: str = "latest") -> str:
    return await rpc_call(session, rpc_url, "eth_call", [{"to": to, "data": data}, block])

def encode_function_call(function_signature: str, args: List) -> str:
    from eth_abi import encode
    from eth_utils import function_signature_to_4byte_selector
    selector = function_signature_to_4byte_selector(function_signature)
    encoded = encode([t for t in function_signature.split("(")[1].split(")")[0].split(",") if t], args)
    return "0x" + selector.hex() + encoded.hex()

# ===================== CORE SCREENER =====================

class TokenScreener:
    def __init__(self, config: Dict):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.results: List[ScreenerResult] = []

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def get_pool_info(self, chain: str, pool_address: str) -> Optional[PoolInfo]:
        """Fetch pool state from blockchain."""
        rpc = get_rpc_url(chain)
        if not rpc:
            return None

        try:
            # slot0: sqrtPriceX96, tick, etc.
            slot0_data = await eth_call(self.session, rpc, pool_address,
                "0x3850c7bd")  # slot0()
            if not slot0_data or slot0_data == "0x":
                return None

            # liquidity()
            liq_data = await eth_call(self.session, rpc, pool_address,
                "0x1a686502")
            # token0()
            token0_data = await eth_call(self.session, rpc, pool_address,
                "0x0dfe1681")
            # token1()
            token1_data = await eth_call(self.session, rpc, pool_address,
                "0xd21220a7")
            # fee()
            fee_data = await eth_call(self.session, rpc, pool_address,
                "0x9775fa39")

            # Decode (simplified - in production use proper ABI decode)
            # This is a placeholder - real implementation needs eth_abi decode
            return PoolInfo(
                address=pool_address,
                token0="0x" + token0_data[-40:] if token0_data != "0x" else "",
                token1="0x" + token1_data[-40:] if token1_data != "0x" else "",
                fee=int(fee_data, 16) if fee_data != "0x" else 3000,
                tick_spacing=60,  # default for 0.3%
                liquidity=0,
                sqrt_price_x96=0,
                tick=0,
            )
        except Exception as e:
            print(f"Error fetching pool {pool_address}: {e}")
            return None

    async def get_token_info(self, chain: str, token_address: str) -> Optional[TokenInfo]:
        """Fetch token metadata and holder distribution."""
        rpc = get_rpc_url(chain)
        if not rpc:
            return None

        try:
            # name()
            name_data = await eth_call(self.session, rpc, token_address, "0x06fdde03")
            # symbol()
            symbol_data = await eth_call(self.session, rpc, token_address, "0x95d89b41")
            # decimals()
            decimals_data = await eth_call(self.session, rpc, token_address, "0x313ce567")
            # totalSupply()
            supply_data = await eth_call(self.session, rpc, token_address, "0x18160ddd")

            return TokenInfo(
                address=token_address,
                symbol="UNKNOWN",
                name="Unknown",
                decimals=18,
                total_supply=0,
                holder_count=0,
                top_holders=[],
            )
        except Exception as e:
            print(f"Error fetching token {token_address}: {e}")
            return None

    async def check_honeypot(self, chain: str, token_address: str) -> Dict:
        """
        Simulate buy & sell to detect honeypot.
        Returns: {"is_honeypot": bool, "buy_tax": float, "sell_tax": float, "details": str}
        """
        # Placeholder - real implementation needs:
        # 1. Find a pool with this token (WETH/TOKEN)
        # 2. Simulate buy 1% of liquidity
        # 3. Simulate sell same amount
        # 4. Calculate effective tax
        # Use tenderly/forge simulation or fork RPC
        return {
            "is_honeypot": False,
            "buy_tax": 0.0,
            "sell_tax": 0.0,
            "details": "Not implemented - use honeypot.is API or fork simulation"
        }

    async def check_contract_safety(self, chain: str, token_address: str) -> Dict:
        """Comprehensive contract safety check."""
        rpc = get_rpc_url(chain)
        results = {
            "verified": False,
            "honeypot": False,
            "mintable": False,
            "fee_manipulation": False,
            "owner_renounced": False,
            "max_tx_limit": False,
            "blacklist": False,
        }

        # Check if verified on explorer (would need explorer API)
        # Check mint/burn functions
        # Check fee functions
        # Check owner

        return results

    def calculate_score(self, data: Dict) -> tuple[int, str, Dict[str, int]]:
        """Calculate total score from individual checks."""
        checks = {
            "contract_safety": data.get("contract_safety", 0),
            "liquidity": data.get("liquidity", 0),
            "tokenomics": data.get("tokenomics", 0),
            "fundamentals": data.get("fundamentals", 0),
            "technical": data.get("technical", 0),
        }
        total = sum(checks.values())

        if total >= 90: tier = "A+"
        elif total >= 80: tier = "A"
        elif total >= 70: tier = "B"
        elif total >= 60: tier = "C"
        else: tier = "D"

        return total, tier, checks

    def passes_auto_reject(self, data: Dict) -> tuple[bool, List[str]]:
        """Check for auto-reject red flags."""
        flags = []

        if data.get("honeypot"):
            flags.append("HONEYPOT")
        if not data.get("verified"):
            flags.append("UNVERIFIED_CONTRACT")
        if data.get("mintable_no_timelock"):
            flags.append("MINTABLE_NO_TIMELOCK")
        if data.get("fee_pct", 0) > 10:
            flags.append("FEE_GT_10PCT")
        if data.get("liquidity_usd", 0) < 20000:
            flags.append("LIQ_UNDER_20K")
        if data.get("locked_liquidity_pct", 0) < 50:
            flags.append("LIQ_NOT_LOCKED")
        if data.get("top10_pct", 100) > 50:
            flags.append("TOP10_GT_50PCT")

        return len(flags) > 0, flags

    async def screen_pair(self, chain: str, dex: str, pool_address: str) -> Optional[ScreenerResult]:
        """Screen a single pool/pair."""
        print(f"Screening {pool_address} on {chain}/{dex}...")

        pool = await self.get_pool_info(chain, pool_address)
        if not pool:
            return None

        # Get token info for both tokens
        token0_info = await self.get_token_info(chain, pool.token0)
        token1_info = await self.get_token_info(chain, pool.token1)

        # Identify which is the "new" token (not WETH)
        weth = CHAIN_CONFIG[chain].get("weth", "").lower()
        token_address = pool.token1 if pool.token0.lower() == weth else pool.token0
        token_symbol = token1_info.symbol if pool.token0.lower() == weth else token0_info.symbol

        # Safety checks
        safety = await self.check_contract_safety(chain, token_address)
        honeypot = await self.check_honeypot(chain, token_address)

        # Build data for scoring
        score_data = {
            "contract_safety": 20 if not safety.get("honeypot") and safety.get("verified") else 5,
            "liquidity": min(25, int(pool.tvl_usd / 10000)),  # rough
            "tokenomics": 15,
            "fundamentals": 10,
            "technical": 10,
        }

        auto_reject, flags = self.passes_auto_reject({
            "honeypot": safety.get("honeypot"),
            "verified": safety.get("verified"),
            "mintable_no_timelock": safety.get("mintable") and not safety.get("timelocked"),
            "fee_pct": 0,
            "liquidity_usd": pool.tvl_usd,
            "locked_liquidity_pct": 0,
            "top10_pct": 100,
        })

        if auto_reject:
            print(f"  -> AUTO REJECT: {flags}")
            return None

        score, tier, checks = self.calculate_score(score_data)

        return ScreenerResult(
            token=token_symbol,
            address=token_address,
            chain=chain,
            dex=dex,
            pair=f"WETH/{token_symbol}",
            pool_address=pool_address,
            score=score,
            tier=tier,
            checks=checks,
            flags=flags,
            liquidity_usd=pool.tvl_usd,
            locked_liquidity_pct=0,
            volume_24h=pool.volume_24h,
            fee_tier=pool.fee / 10000,
            holder_count=0,
            top10_pct=0,
            recommendation=f"LP with {self._position_size(tier)} portfolio, range ±10% from tick {pool.tick}",
            timestamp=datetime.utcnow().isoformat() + "Z",
            tick_lower=pool.tick - 5000,
            tick_upper=pool.tick + 5000,
            current_tick=pool.tick,
        )

    def _position_size(self, tier: str) -> str:
        sizes = {"A+": "3-5%", "A": "2-3%", "B": "1-2%", "C": "0.5%", "D": "0%"}
        return sizes.get(tier, "0%")

    async def scan_new_pools(self, chain: str, dex: str, max_age_hours: int = 24,
                             min_liquidity: float = 50000) -> List[ScreenerResult]:
        """
        Scan for new pools created in the last max_age_hours.
        Uses factory PoolCreated events or subgraph.
        """
        print(f"Scanning {chain}/{dex} for pools created in last {max_age_hours}h...")

        # This would typically use:
        # 1. Factory contract PoolCreated event logs (eth_getLogs)
        # 2. Subgraph (TheGraph) for historical data
        # 3. DEX-specific APIs (Uniswap info API, etc.)

        # Placeholder: return mock results for demo
        mock_pools = [
            "0x1234567890123456789012345678901234567890",
            "0x2345678901234567890123456789012345678901",
        ]

        results = []
        for pool_addr in mock_pools:
            result = await self.screen_pair(chain, dex, pool_addr)
            if result and result.liquidity_usd >= min_liquidity:
                results.append(result)

        return results

    async def run(self, chains: List[str], dexes: List[str],
                  max_age_hours: int = 24, min_liquidity: float = 50000,
                  min_score: int = 70) -> List[ScreenerResult]:
        """Main entry point."""
        all_results = []

        for chain in chains:
            for dex in dexes:
                if chain not in CHAIN_CONFIG:
                    print(f"Unknown chain: {chain}")
                    continue

                pools = await self.scan_new_pools(chain, dex, max_age_hours, min_liquidity)
                for pool in pools:
                    if pool.score >= min_score:
                        all_results.append(pool)

        # Sort by score descending
        all_results.sort(key=lambda x: x.score, reverse=True)
        self.results = all_results
        return all_results

    def save_results(self, output_path: str):
        """Save results to JSON file."""
        data = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "total_found": len(self.results),
            "results": [asdict(r) for r in self.results]
        }
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved {len(self.results)} results to {output_path}")


# ===================== CLI =====================

def parse_args():
    parser = argparse.ArgumentParser(description="Token Screener - Multi-chain DEX Pair Discovery")
    parser.add_argument("--chain", nargs="+", default=["base"],
                        choices=list(CHAIN_CONFIG.keys()),
                        help="Chains to scan")
    parser.add_argument("--dex", nargs="+", default=["uniswap_v3"],
                        choices=["uniswap_v3", "uniswap_v4", "pancake_v3", "trader_joe_v3"],
                        help="DEXes to scan")
    parser.add_argument("--max-age", type=int, default=24,
                        help="Max pool age in hours")
    parser.add_argument("--min-liq", type=float, default=50000,
                        help="Minimum liquidity USD")
    parser.add_argument("--min-score", type=int, default=70,
                        help="Minimum score to include in output")
    parser.add_argument("--output", type=str, default="output/screener_results.json",
                        help="Output JSON file")
    parser.add_argument("--config", type=str, help="Config file path")
    return parser.parse_args()

async def main():
    args = parse_args()

    if args.config:
        with open(args.config) as f:
            config = json.load(f)
    else:
        config = {}

    async with TokenScreener(config) as screener:
        results = await screener.run(
            chains=args.chain,
            dexes=args.dex,
            max_age_hours=args.max_age,
            min_liquidity=args.min_liq,
            min_score=args.min_score
        )

    if results:
        screener.save_results(args.output)
        print(f"\n=== TOP RESULTS ===")
        for r in results[:10]:
            print(f"  {r.token} ({r.chain}/{r.dex}) - Score: {r.score} ({r.tier}) - Liq: ${r.liquidity_usd:,.0f}")
    else:
        print("No results meeting criteria.")

if __name__ == "__main__":
    asyncio.run(main())