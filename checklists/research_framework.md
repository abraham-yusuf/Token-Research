# Token Research Framework — Checklist & Scoring

**Version:** 1.0  
**Target:** New token LP opportunities (Uniswap V3/V4, Pons, etc.)  
**Philosophy:** "Research first, ape later" — systematic due diligence before capital deployment.

---

## Scoring System (0-100)

| Tier | Score | Action |
|------|-------|--------|
| **A+ (Elite)** | 90-100 | Full size, immediate LP |
| **A (Strong)** | 80-89 | Standard size, LP |
| **B (Decent)** | 70-79 | Small size, monitor |
| **C (Speculative)** | 60-69 | Tiny size / skip |
| **D (Avoid)** | <60 | Hard pass |

**Minimum threshold for LP: 70 (B-tier)**

---

## 1. Contract Safety (0-25 pts) — **HARD GATE**

| Check | Tool/Method | Points | Pass Criteria |
|-------|-------------|--------|---------------|
| **Verified on explorer** | Etherscan/Basescan/Robinhoodscan | 5 | ✅ Verified source code |
| **No honeypot** | honeypot.is, rugscreen, custom script | 8 | ✅ Buy & sell work, no hidden tax |
| **No mint/burn authority** (or timelocked) | Read contract `mint`, `burn`, `setMinter` | 5 | ✅ No mint / timelocked > 48h / DAO |
| **Ownership renounced / timelocked** | `owner()`, `renounceOwnership`, timelock | 4 | ✅ Renounced OR timelock > 48h |
| **No hidden fees / tax manipulation** | Simulate buy/sell 1%, 5%, 10% | 3 | ✅ Fee ≤ 5%, consistent |

**🛑 AUTO-REJECT if: honeypot, unverified, mintable without timelock, fee > 10%**

---

## 2. Liquidity & Market Structure (0-25 pts)

| Metric | Tool/Method | Points | Good Threshold |
|--------|-------------|--------|----------------|
| **Total liquidity (USD)** | DEX API / subgraph | 5 | > $100k (V3/V4), > $50k (Pons) |
| **Liquidity locked / burned** | Team.finance, Unicrypt, custom lock check | 8 | ✅ > 80% locked > 1 year OR burned |
| **Pool type & version** | Identify V2/V3/V4/Pons | 3 | V3/V4 concentrated, Pons CLMM |
| **Fee tier** | 0.01%, 0.05%, 0.3%, 1% | 3 | Matches volatility (stable=0.01%, volatile=1%) |
| **Volume / Liquidity ratio (24h)** | DEX screener / subgraph | 3 | > 0.1 (healthy), > 0.5 (hot) |
| **Price impact (1% depth)** | DEX quote API | 3 | < 2% for $10k swap |

---

## 3. Tokenomics & Distribution (0-20 pts)

| Metric | Tool/Method | Points | Good Threshold |
|--------|-------------|--------|----------------|
| **Holder count** | Etherscan / holder API | 3 | > 500 (new), > 2000 (established) |
| **Top 10 holders %** | Holder analysis | 5 | < 50% (excl. LP, CEX, burn) |
| **Deployer / team allocation** | Track deployer wallet + team multisig | 5 | < 10% team, vested |
| **CEX listings** | CoinGecko/CMC + API | 3 | None (pure DEX) = higher risk/alpha |
| **Supply dynamics** | Max supply, circulating, emission | 4 | Low inflation, no massive unlocks soon |

---

## 4. Project Fundamentals (0-15 pts)

| Check | Tool/Method | Points | Good Signal |
|--------|-------------|--------|-------------|
| **Website / docs exist** | Manual visit | 2 | Professional, clear token utility |
| **GitHub / open source** | GitHub org + repo activity | 3 | Active commits, audits |
| **Audit reports** | Certik, PeckShield, Trail of Bits, etc. | 5 | ≥ 1 reputable audit, no critical unfixed |
| **Community / socials** | Twitter, Discord, Telegram | 3 | Organic engagement, not botted |
| **Narrative fit** | Sector trend (AI, DePIN, RWA, etc.) | 2 | Aligns with current meta |

---

## 5. Technical & On-Chain Signals (0-15 pts)

| Signal | Tool/Method | Points | Good Signal |
|--------|-------------|--------|-------------|
| **Deployer history** | Check deployer's past tokens | 5 | Previous successful launches |
| **Whale accumulation** | Nansen / Arkham / custom whale track | 4 | Smart money accumulating |
| **Volume trend (7d/30d)** | DEX volume chart | 3 | Sustainable growth, not wash trade |
| **Price vs launch** | Chart analysis | 3 | Not -90% from ATH (dead) |

---

## Quick-Reference: RED FLAGS (Auto-Reject)

- [ ] Honeypot / can't sell
- [ ] Contract not verified
- [ ] Mint function accessible (no timelock)
- [ ] Fee > 10% or dynamic/hidden
- [ ] Liquidity < $20k
- [ ] Liquidity not locked / ruggable
- [ ] Top 1 holder > 50% (excl. LP/burn)
- [ ] Deployer rugged previous tokens
- [ ] No website / dead socials / obvious scam
- [ ] Wash trading obvious (volume = liquidity * 100+)

---

## Research Workflow

```
1. SCREENER OUTPUT → raw candidates
2. QUICK FILTER (auto-reject red flags) → ~20% survive
3. DEEP DIVE (checklist above) → score each
3. TOP 3-5 → LP range calc + position sizing
4. EXECUTE → manual or script with own keys
5. MONITOR → alerts for range exit, fees, volume spike
```

---

## Position Sizing Guide (per opportunity)

| Tier | Max % Portfolio | Max Single LP |
|------|----------------|---------------|
| A+ | 5-10% | 3-5% |
| A | 3-5% | 2-3% |
| B | 1-3% | 1-2% |
| C | 0.5-1% | 0.5% |

**Never exceed 10% total in concentrated LP positions.**

---

## Output Format (JSON for automation)

```json
{
  "token": "SYMBOL",
  "address": "0x...",
  "chain": "base|ethereum|robinhood|...",
  "dex": "uniswap_v3|uniswap_v4|pons|...",
  "pair": "WETH/TOKEN",
  "score": 82,
  "tier": "A",
  "checks": {
    "contract_safety": 22,
    "liquidity": 20,
    "tokenomics": 16,
    "fundamentals": 12,
    "technical": 12
  },
  "flags": [],
  "liquidity_usd": 245000,
  "locked_liquidity_pct": 95,
  "volume_24h": 180000,
  "fee_tier": 0.003,
  "holder_count": 1240,
  "top10_pct": 38,
  "recommendation": "LP with 2% portfolio, range ±15% from current tick",
  "timestamp": "2026-09-04T14:30:00Z"
}
```

---

## Next Steps (Implementation Order)

1. ✅ This checklist (markdown + JSON schema)
2. 🔄 Screener script (multi-DEX, multi-chain)
3. 🔄 Contract safety module (honeypot, mint, fee sim)
4. 🔄 LP range calculator (V3/V4/Pons)
5. 🔄 Monitor/alert system (Telegram/webhook)
6. 🔄 Execution helper scripts (forge/cast)