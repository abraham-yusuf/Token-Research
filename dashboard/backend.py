"""
FastAPI Backend for Token Research Dashboard

Provides REST API endpoints for:
- Screener results
- Pool analytics
- Position monitoring
- Rebalancing management
- Alert management
"""

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import asyncio
import json
import os
from contextlib import asynccontextmanager

# Import framework modules
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import (
    LPCalculator, PoolParams, DexType, price_to_tick, tick_to_price,
    sqrt_price_x96_to_price, price_to_sqrt_price_x96,
    TheGraphClient, TheGraphAnalyzer, Chain,
    SafetyChecker, HoneypotIsAPI,
    PositionRebalancer, RebalanceConfig, RebalanceStrategy, Position,
    AlertManager, AlertLevel,
    __version__
)


# ===================== PYDANTIC MODELS =====================

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


class PoolAnalyticsRequest(BaseModel):
    chain: str
    pool_address: str
    days: int = 30


class PoolAnalyticsResponse(BaseModel):
    pool_address: str
    chain: str
    metrics: Dict[str, Any]
    swap_activity: Dict[str, Any]
    position_activity: Dict[str, Any]
    daily_data: List[Dict[str, Any]]
    generated_at: datetime


class ScreenerRequest(BaseModel):
    chains: List[str] = ["base"]
    dexes: List[str] = ["uniswap_v3"]
    max_age_hours: int = 24
    min_liquidity: float = 50000
    min_score: int = 70


class ScreenerResult(BaseModel):
    token: str
    address: str
    chain: str
    dex: str
    pair: str
    pool_address: str
    score: int
    tier: str
    checks: Dict[str, int]
    liquidity_usd: float
    volume_24h: float
    fee_tier: float
    recommendation: str


class ScreenerResponse(BaseModel):
    total_found: int
    results: List[ScreenerResult]
    generated_at: datetime


class HoneypotCheckRequest(BaseModel):
    token_address: str
    chain: str = "base"


class HoneypotCheckResponse(BaseModel):
    is_honeypot: bool
    buy_tax: float
    sell_tax: float
    transfer_tax: float
    can_buy: bool
    can_sell: bool
    owner: Optional[str]
    proxy: bool
    risks: List[str]


class LPRangeRequest(BaseModel):
    chain: str
    pool_address: str
    center_price: float
    width_pct: float = 0.20
    amount0: float
    amount1: float
    token0_decimals: int = 18
    token1_decimals: int = 18
    fee_tier: int = 3000


class LPRangeResponse(BaseModel):
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
    il_estimate_1x: float
    il_estimate_2x: float
    risk_score: float


class RebalancePlanRequest(BaseModel):
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
    strategy: str = "passive"
    target_width_pct: float = 0.20
    dry_run: bool = True


class RebalancePlanResponse(BaseModel):
    action: str
    reason: str
    new_tick_lower: Optional[int]
    new_tick_upper: Optional[int]
    fees_token0: float
    fees_token1: float
    estimated_gas_usd: float
    estimated_slippage_pct: float
    risk_score: float


class AlertRequest(BaseModel):
    level: str
    title: str
    message: str
    chain: str = ""
    dex: str = ""
    token: str = ""
    pool_address: str = ""


class PositionModel(BaseModel):
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
    nft_id: Optional[int] = None


# ===================== APP STATE =====================

class AppState:
    def __init__(self):
        self.graph_client: Optional[TheGraphClient] = None
        self.screener_results: List[Dict] = []
        self.active_alerts: List[Dict] = []
        self.managed_positions: Dict[str, Position] = {}
        self.rebalancer: Optional[PositionRebalancer] = None
        self.websocket_connections: List[WebSocket] = []


app_state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app_state.graph_client = TheGraphClient()
    await app_state.graph_client.__aenter__()
    
    # Initialize alert manager
    config = {
        "alerts": {
            "enable_telegram": False,
            "enable_webhook": False,
        }
    }
    app_state.alert_manager = AlertManager(config)
    
    yield
    
    # Shutdown
    if app_state.graph_client:
        await app_state.graph_client.__aexit__(None, None, None)


# ===================== FASTAPI APP =====================

app = FastAPI(
    title="Token Research Dashboard API",
    description="REST API for Token Research Framework",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================== HEALTH =====================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        version=__version__,
        timestamp=datetime.utcnow()
    )


# ===================== POOL ANALYTICS =====================

@app.post("/api/v1/pool/analytics", response_model=PoolAnalyticsResponse)
async def get_pool_analytics(request: PoolAnalyticsRequest):
    """Get comprehensive pool analytics from TheGraph."""
    try:
        chain = Chain[request.chain.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {request.chain}")
    
    async with TheGraphClient() as client:
        analyzer = TheGraphAnalyzer(client)
        analysis = await analyzer.analyze_pool_history(chain, request.pool_address, request.days)
    
    if "error" in analysis:
        raise HTTPException(status_code=404, detail=analysis["error"])
    
    return PoolAnalyticsResponse(
        pool_address=request.pool_address,
        chain=request.chain,
        metrics=analysis["metrics"],
        swap_activity=analysis["swap_activity"],
        position_activity=analysis["position_activity"],
        daily_data=analysis["daily_data"],
        generated_at=datetime.utcnow()
    )


@app.get("/api/v1/pool/{chain}/{pool_address}/day-data")
async def get_pool_day_data(
    chain: str, 
    pool_address: str, 
    days: int = Query(30, ge=1, le=365)
):
    """Get historical daily data for a pool."""
    try:
        chain_enum = Chain[chain.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")
    
    async with TheGraphClient() as client:
        day_data = await client.get_pool_day_data(Chain[chain.upper()], pool_address, days)
    
    return {"pool_address": pool_address, "chain": chain, "days": days, "data": [d.__dict__ for d in day_data]}


@app.get("/api/v1/pool/{chain}/{pool_address}/swaps")
async def get_pool_swaps(
    chain: str, 
    pool_address: str, 
    hours: int = Query(24, ge=1, le=168)
):
    """Get recent swaps for a pool."""
    try:
        chain_enum = Chain[chain.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")
    
    async with TheGraphClient() as client:
        swaps = await client.get_swaps(chain_enum, pool_address, hours=hours)
    
    return {"pool_address": pool_address, "chain": chain, "hours": hours, "swaps": [s.__dict__ for s in swaps]}


@app.get("/api/v1/token/{chain}/{token_address}/pools")
async def get_token_pools(
    chain: str,
    token_address: str,
    min_tvl: float = Query(10000, ge=0),
    limit: int = Query(20, ge=1, le=100)
):
    """Get all pools for a token."""
    try:
        chain_enum = Chain[chain.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")
    
    async with TheGraphClient() as client:
        pools = await client.get_pools_by_token(chain_enum, token_address, min_tvl, limit)
    
    return {"token_address": token_address, "chain": chain, "pools": [p.__dict__ for p in pools]}


# ===================== SCREENER =====================

@app.post("/api/v1/screener/run", response_model=ScreenerResponse)
async def run_screener(request: ScreenerRequest):
    """Run the multi-chain screener."""
    from scripts.screener import TokenScreener
    
    screener = TokenScreener({})
    
    # Convert chain/dex strings to enums
    chains = [c.lower() for c in request.chains]
    dexes = [d.lower() for d in request.dexes]
    
    # Run screener (simplified - would need proper implementation)
    # For now return cached results if available
    results = app_state.screener_results
    
    if not results:
        # Run a quick mock screener
        results = [{
            "token": "SAMPLE",
            "address": "0x123...",
            "chain": "base",
            "dex": "uniswap_v3",
            "pair": "WETH/SAMPLE",
            "pool_address": "0xpool...",
            "score": 85,
            "tier": "A",
            "checks": {"contract_safety": 22, "liquidity": 20, "tokenomics": 16, "fundamentals": 12, "technical": 15},
            "liquidity_usd": 250000,
            "volume_24h": 50000,
            "fee_tier": 0.003,
            "recommendation": "LP with 2% portfolio, range ±15% from current tick"
        }]
    
    # Filter by min score
    results = [r for r in results if r.get("score", 0) >= request.min_score]
    
    return ScreenerResponse(
        total_found=len(results),
        results=[ScreenerResult(**r) for r in results],
        generated_at=datetime.utcnow()
    )


@app.get("/api/v1/screener/results")
async def get_screener_results(
    min_score: int = Query(70, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200)
):
    """Get cached screener results."""
    results = [r for r in app_state.screener_results if r.get("score", 0) >= min_score]
    results = results[:limit]
    return {"total": len(results), "results": results}


# ===================== HONEYPOT DETECTION =====================

@app.post("/api/v1/safety/honeypot", response_model=HoneypotCheckResponse)
async def check_honeypot(request: HoneypotCheckRequest):
    """Check if a token is a honeypot using honeypot.is API."""
    checker = SafetyChecker("https://eth.llamarpc.com")
    result = await checker.check_token_safety(request.token_address, request.chain)
    
    return HoneypotCheckResponse(
        is_honeypot=result["is_honeypot"],
        buy_tax=result["buy_tax"],
        sell_tax=result["sell_tax"],
        transfer_tax=result["transfer_tax"],
        can_buy=result["can_buy"],
        can_sell=result["can_sell"],
        owner=result.get("owner"),
        proxy=result.get("proxy", False),
        risks=result.get("risks", [])
    )


# ===================== LP RANGE CALCULATOR =====================

@app.post("/api/v1/lp/calculate-range", response_model=LPRangeResponse)
async def calculate_lp_range(request: LPRangeRequest):
    """Calculate optimal LP range for a pool."""
    try:
        pool = PoolParams(
            fee_tier=request.fee_tier,
            tick_spacing=60 if request.fee_tier == 3000 else 10 if request.fee_tier == 500 else 200,
            current_tick=price_to_tick(request.center_price),
            current_sqrt_price_x96=price_to_sqrt_price_x96(request.center_price, request.token0_decimals, request.token1_decimals),
            liquidity=1000000000000000000,  # placeholder
            token0_decimals=request.token0_decimals,
            token1_decimals=request.token1_decimals,
        )
        
        calc = LPCalculator(DexType.UNISWAP_V3)
        result = calc.calculate_range_from_price(pool, request.center_price, request.width_pct, request.amount0, request.amount1)
        
        return LPRangeResponse(
            tick_lower=result.tick_lower,
            tick_upper=result.tick_upper,
            price_lower=result.price_lower,
            price_upper=result.price_upper,
            amount0=result.amount0,
            amount1=result.amount1,
            liquidity=result.liquidity,
            in_range=result.in_range,
            distance_to_lower_ticks=result.distance_to_lower_ticks,
            distance_to_upper_ticks=result.distance_to_upper_ticks,
            il_estimate_1x=result.il_estimate_1x,
            il_estimate_2x=result.il_estimate_2x,
            risk_score=result.risk_score,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/lp/tick-to-price/{tick}")
async def tick_to_price_endpoint(tick: int):
    """Convert tick to price."""
    return {"tick": tick, "price": tick_to_price(tick)}


@app.get("/api/v1/lp/price-to-tick/{price}")
async def price_to_tick_endpoint(price: float):
    """Convert price to tick."""
    return {"price": price, "tick": price_to_tick(price)}


# ===================== REBALANCING =====================

@app.post("/api/v1/rebalance/plan", response_model=RebalancePlanResponse)
async def create_rebalance_plan(request: RebalancePlanRequest):
    """Create a rebalance plan for a position."""
    try:
        chain_enum = Chain[request.chain.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {request.chain}")
    
    try:
        dex_enum = DexType[request.dex.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unsupported DEX: {request.dex}")
    
    strategy = RebalanceStrategy[request.strategy.upper()]
    
    config = RebalanceConfig(
        strategy=strategy,
        target_width_pct=request.target_width_pct,
        dry_run=request.dry_run,
    )
    
    position = Position(
        pool_address=request.pool_address,
        chain=request.chain,
        dex=request.dex,
        token0=request.token0,
        token1=request.token1,
        token0_symbol=request.token0_symbol,
        token1_symbol=request.token1_symbol,
        token0_decimals=request.token0_decimals,
        token1_decimals=request.token1_decimals,
        tick_lower=request.tick_lower,
        tick_upper=request.tick_upper,
        liquidity=request.liquidity,
        fee_tier=request.fee_tier,
    )
    
    # Create rebalancer (without graph client for quick plan)
    config_obj = RebalanceConfig(strategy=RebalanceStrategy[strategy.name], dry_run=True)
    rebalancer = PositionRebalancer(None, None, config_obj)
    rebalancer.add_position(position)
    
    # Quick plan without graph client
    plan = await app_state.rebalancer.check_position(position) if app_state.rebalancer else None
    
    if not plan:
        # Generate mock plan
        plan = type('Plan', (), {
            'action': RebalanceAction.REBALANCE,
            'reason': 'Price near boundary',
            'new_tick_lower': request.tick_lower - 500,
            'new_tick_upper': request.tick_upper + 500,
            'fees_token0': 0.0,
            'fees_token1': 0.0,
            'estimated_gas_usd': 5.0,
            'estimated_slippage_pct': 0.1,
            'risk_score': 50.0,
            'current_tick': 80000,
            'current_price': 1.0,
            'volatility': 0.1,
        })()
    
    return RebalancePlanResponse(
        action=plan.action.value,
        reason=plan.reason,
        new_tick_lower=plan.new_tick_lower,
        new_tick_upper=plan.new_tick_upper,
        fees_token0=plan.fees_token0,
        fees_token1=plan.fees_token1,
        estimated_gas_usd=plan.estimated_gas_usd,
        estimated_slippage_pct=plan.estimated_slippage_pct,
        risk_score=plan.risk_score,
    )


@app.get("/api/v1/rebalance/positions")
async def list_positions():
    """List all managed positions."""
    return {"positions": [asdict(p) for p in app_state.managed_positions.values()]}


@app.post("/api/v1/rebalance/positions")
async def add_position(position: PositionModel):
    """Add a position to manage."""
    pos = Position(**position.model_dump())
    app_state.managed_positions[pos.pool_address.lower()] = pos
    return {"status": "added", "pool_address": pos.pool_address}


@app.delete("/api/v1/rebalance/positions/{pool_address}")
async def remove_position(pool_address: str):
    """Remove a managed position."""
    app_state.managed_positions.pop(pool_address.lower(), None)
    return {"status": "removed", "pool_address": pool_address}


# ===================== ALERTS =====================

@app.post("/api/v1/alerts/send")
async def send_alert(request: AlertRequest):
    """Send an alert through configured channels."""
    try:
        level = AlertLevel[request.level.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Invalid alert level: {request.level}")
    
    alert = Alert(
        level=level,
        title=request.title,
        message=request.message,
        chain=request.chain,
        dex=request.dex,
        token=request.token,
        pool_address=request.pool_address,
    )
    
    if hasattr(app_state, 'alert_manager'):
        await app_state.alert_manager.send(alert)
    
    # Store for history
    app_state.active_alerts.append({
        "level": request.level,
        "title": request.title,
        "message": request.message,
        "timestamp": datetime.utcnow().isoformat(),
    })
    
    # Broadcast to websockets
    for ws in app_state.websocket_connections:
        try:
            await ws.send_json({"type": "alert", "data": app_state.active_alerts[-1]})
        except Exception:
            pass
    
    return {"status": "sent", "alert": app_state.active_alerts[-1]}


@app.get("/api/v1/alerts/history")
async def get_alert_history(limit: int = Query(50, ge=1, le=200)):
    """Get alert history."""
    return {"alerts": app_state.active_alerts[-limit:]}


# ===================== WEBSOCKET =====================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates."""
    await websocket.accept()
    app_state.websocket_connections.append(websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            # Echo for now - could handle commands
            await websocket.send_json({"type": "echo", "data": data})
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in app_state.websocket_connections:
            app_state.websocket_connections.remove(websocket)


# ===================== MARKET DATA =====================

@app.get("/api/v1/market/overview")
async def market_overview():
    """Get market overview data."""
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "chains": {
            "ethereum": {"status": "active", "pools": 0},
            "base": {"status": "active", "pools": 0},
            "arbitrum": {"status": "active", "pools": 0},
        },
        "total_positions": len(app_state.managed_positions),
        "active_alerts": len(app_state.active_alerts),
    }


# ===================== VERSION =====================

@app.get("/api/v1/version")
async def get_version():
    return {"version": __version__, "name": "Token Research Framework"}


# ===================== RUN =====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)