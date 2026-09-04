# Token Research Framework

A comprehensive toolkit for discovering, analyzing, and managing concentrated liquidity positions on Uniswap V3/V4, Pons, and other CLMM DEXes.

## Features

- 🔍 **Multi-chain Screener** - Scan Uniswap V3/V4, Pancake V3, Trader Joe, Pons across Ethereum, Base, Arbitrum, Optimism, Polygon, BSC, Avalanche
- 📋 **Research Framework** - Systematic 100-point scoring (contract safety, liquidity, tokenomics, fundamentals, technical)
- 🛡️ **Contract Safety** - Honeypot detection, mint/burn authority checks, fee manipulation detection
- 📐 **LP Range Calculator** - Optimal tick ranges for V3, V4, Pons with IL estimation and risk scoring
- 🔔 **Monitoring & Alerts** - Telegram, Discord, Slack, webhook alerts for range exit, fee collection, volume spikes
- ⚡ **Execution Helpers** - Forge/cast scripts for mint, collect, burn, rebalance
- 📊 **TheGraph Integration** - Historical pool data, volume, fees, swaps, mints, burns, fee APR calculation, new pool alerts

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy config template
cp config/config.json config/local.json
# Edit local.json with your API keys

# Run screener
python scripts/screener.py --chain base --dex uniswap_v3 --min-liq 50000 --output output/base_v3.json

# Use LP calculator
python -c "
from lib.lp_calculator import *
pool = PoolParams(fee_tier=3000, tick_spacing=60, current_tick=80067, ...)
calc = LPCalculator(DexType.UNISWAP_V3)
result = calc.calculate_range_from_price(pool, 3000, 0.20, 1000, 0.33)
print(format_result(result))
"
```

## Project Structure

```
token-research/
├── scripts/
│   └── screener.py           # Main multi-chain screener
├── lib/
│   ├── lp_calculator.py      # V3/V4/Pons range calculator
│   ├── monitor.py            # Alert & position monitoring
│   └── __init__.py
├── checklists/
│   ├── research_framework.md # 100-point scoring guide
│   └── schema.json           # JSON output schema
├── config/
│   ├── config.json           # Template config
│   └── local.json            # Your local config (gitignored)
├── output/                   # Screener results
└── requirements.txt
```

## Screener Usage

```bash
# Scan Base Uniswap V3 for new pools
python scripts/screener.py --chain base --dex uniswap_v3 --min-liq 50000

# Scan multiple chains/dexes
python scripts/screener.py --chain base arbitrum --dex uniswap_v3 pancake_v3 --min-score 75

# Custom config
python scripts/screener.py --config config/local.json --output output/my_results.json
```

## LP Calculator Usage

```python
from lib.lp_calculator import *

# Define pool
pool = PoolParams(
    fee_tier=3000,
    tick_spacing=60,
    current_tick=80067,
    current_sqrt_price_x96=price_to_sqrt_price_x96(3000, 6, 18),
    liquidity=1000000000000000000,
    token0_decimals=6,
    token1_decimals=18,
)

calc = LPCalculator(DexType.UNISWAP_V3)

# Calculate ±20% range
result = calc.calculate_range_from_price(pool, 3000, 0.20, 1000, 0.33)
print(format_result(result))

# Find optimal ranges
optimal = calc.find_optimal_range(pool, 1000, 0.33)
```

## Pons / V4 Calculators

```python
from lib.lp_calculator import PonsCalculator, UniswapV4Calculator, DexType

# Pons (CLMM on Base)
pons_calc = PonsCalculator()
result = pons_calc.calculate_pons_range(pool, 1000, 0.33, strategy="balanced")

# Uniswap V4 (hooks, dynamic fees)
v4_calc = UniswapV4Calculator()
result = v4_calc.calculate_v4_range(pool, 1000, 0.33, hook_data={"dynamic_fee": True})
```

## Monitoring & Alerts

```python
from lib.monitor import AlertManager, AlertLevel, PositionMonitor

config = {
    "alerts": {
        "enable_telegram": True,
        "telegram_bot_token": "YOUR_BOT_TOKEN",
        "telegram_chat_id": "YOUR_CHAT_ID",
        "enable_webhook": True,
        "webhook_url": "https://discord.com/api/webhooks/...",
        "webhook_template": "discord"
    }
}

manager = AlertManager(config)

# Send manual alerts
await manager.send_warning("Range Exit", "Position out of range", chain="base", dex="uniswap_v3")

# Monitor positions
monitor = PositionMonitor(manager, "https://mainnet.base.org")
monitor.add_position("0xpool...", "base", "uniswap_v3", 77820, 81840, "USDC", "WETH")
await monitor.start_monitoring(rpc_client, interval_seconds=60)
```

## TheGraph Integration

```python
from lib import TheGraphClient, TheGraphAnalyzer, Chain

async with TheGraphClient() as client:
    analyzer = TheGraphAnalyzer(client)

    # Analyze pool history (30 days)
    analysis = await analyzer.analyze_pool_history(
        Chain.BASE, 
        "0x...pool_address...", 
        days=30
    )
    print(f"Fee APR: {analysis['metrics']['fee_apr_pct']:.1f}%")
    print(f"7d Volume: ${analysis['metrics']['volume_7d_usd']:,.0f}")

    # Find profitable pools for a token
    pools = await analyzer.find_profitable_pools(
        Chain.BASE, 
        "0x...token_address...", 
        min_fee_apr=20, 
        min_tvl=50000
    )

    # Get new pool alerts (last 24h)
    new_pools = await analyzer.get_new_pool_alerts(Chain.BASE, hours=24)
```

## Research Checklist

See [checklists/research_framework.md](checklists/research_framework.md) for the full 100-point scoring system:

- **Contract Safety (25pts)** - Verified, no honeypot, no mint, fees ≤5%
- **Liquidity (25pts)** - >$100k, >80% locked, healthy vol/liq ratio
- **Tokenomics (20pts)** - Holder distribution, team allocation, supply dynamics
- **Fundamentals (15pts)** - Audit, docs, GitHub, community, narrative
- **Technical (15pts)** - Deployer history, whale accumulation, volume trends

**Auto-reject flags:** honeypot, unverified, mintable, fee>10%, liq<$20k, unlocked liq, top10>50%

## Output Format

Results saved as JSON matching [checklists/schema.json](checklists/schema.json):

```json
{
  "token": "TOKEN",
  "address": "0x...",
  "chain": "base",
  "dex": "uniswap_v3",
  "pair": "WETH/TOKEN",
  "score": 82,
  "tier": "A",
  "checks": {"contract_safety": 22, "liquidity": 20, ...},
  "liquidity_usd": 245000,
  "recommendation": "LP with 2% portfolio, range ±15% from current tick",
  "timestamp": "2026-09-04T14:30:00Z"
}
```

## Security Notes

- **Never commit API keys** - Use `config/local.json` (gitignored)
- **Never share private keys** - Execution scripts use your local keys only
- **Test on testnet first** - Verify scripts before mainnet
- **Position sizing** - Never exceed 10% portfolio in concentrated LP

## Next Steps

- [ ] Add TheGraph subgraph integration for historical data
- [ ] Add Tenderly/Forge simulation for honeypot detection
- [ ] Add automated rebalancing scripts
- [ ] Add dashboard (Streamlit/FastAPI)
- [ ] Add backtesting module for range strategies

## License

MIT - Use at your own risk. Not financial advice.