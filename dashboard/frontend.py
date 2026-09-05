"""
Streamlit Frontend for Token Research Dashboard

Interactive dashboard for:
- Pool analytics and visualization
- Screener results
- LP range calculator
- Honeypot detection
- Rebalancing management
- Position monitoring
"""

import streamlit as st
import asyncio
import aiohttp
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json
import os
from typing import Dict, List, Optional, Any

# ===================== CONFIG =====================

API_BASE = os.getenv("API_BASE", "http://localhost:8000/api/v1")

st.set_page_config(
    page_title="Token Research Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .alert-critical { border-left: 4px solid #ff4b4b; }
    .alert-warning { border-left: 4px solid #ffa502; }
    .alert-info { border-left: 4px solid #1f77b4; }
    .alert-success { border-left: 4px solid #00d16a; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 16px; }
</style>
""", unsafe_allow_html=True)


# ===================== API CLIENT =====================

class APIClient:
    def __init__(self, base_url: str = API_BASE):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def get(self, endpoint: str, params: Dict = None) -> Dict:
        async with self.session.get(f"{self.base_url}{endpoint}", params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                text = await resp.text()
                raise Exception(f"API Error {resp.status}: {text}")
    
    async def post(self, endpoint: str, data: Dict) -> Dict:
        async with self.session.post(f"{self.base_url}{endpoint}", json=data) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                text = await resp.text()
                raise Exception(f"API Error {resp.status}: {text}")


# ===================== HELPER FUNCTIONS =====================

def format_number(num: float, decimals: int = 2) -> str:
    """Format number with commas and appropriate decimals."""
    if abs(num) >= 1e9:
        return f"${num/1e9:.{decimals}f}B"
    elif abs(num) >= 1e6:
        return f"${num/1e6:.{decimals}f}M"
    elif abs(num) >= 1e3:
        return f"${num/1e3:.{decimals}f}K"
    else:
        return f"${num:.{decimals}f}"


def display_alert(level: str, title: str, message: str):
    """Display styled alert."""
    icons = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️", "success": "✅"}
    colors = {"critical": "#ff4b4b", "warning": "#ffa502", "info": "#1f77b4", "success": "#00d16a"}
    
    st.markdown(f"""
    <div style="border-left: 4px solid {colors.get(level, '#1f77b4')}; 
                padding: 1rem; margin: 0.5rem 0; background: #f8f9fa; border-radius: 0.25rem;">
        <strong>{icons.get(level, '📢')} {title}</strong><br>
        {message}
    </div>
    """, unsafe_allow_html=True)


# ===================== PAGES =====================

def page_overview():
    """Overview dashboard page."""
    st.title("📊 Token Research Dashboard")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Managed Positions", "0", delta="+0")
    with col2:
        st.metric("Active Alerts", "0", delta="+0")
    with col3:
        st.metric("Total Exposure", "$0", delta="+0%")
    with col4:
        st.metric("Fee APR (avg)", "0%", delta="+0%")
    
    st.divider()
    
    # Quick actions
    st.subheader("🚀 Quick Actions")
    col1, col2, col3, col5 = st.columns(4)
    
    with col1:
        if st.button("🔍 Run Screener", use_container_width=True):
            st.switch_page("pages/1_🔍_Screener.py")
    with col2:
        if st.button("🛡️ Check Honeypot", use_container_width=True):
            st.switch_page("pages/2_🛡️_Safety_Check.py")
    with col3:
        if st.button("📐 Calculate LP Range", use_container_width=True):
            st.switch_page("pages/3_📐_LP_Calculator.py")
    with col5:
        if st.button("🔄 Rebalance", use_container_width=True):
            st.switch_page("pages/4_🔄_Rebalancer.py")
    
    st.divider()
    
    # Market overview
    st.subheader("📈 Market Overview")
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("🔗 **Chains**: Ethereum, Base, Arbitrum, Optimism, Polygon, BSC, Avalanche")
    with col2:
        st.info("🏪 **DEXes**: Uniswap V3/V4, Pancake V3, Trader Joe, Pons")


def page_screener():
    """Screener page."""
    st.title("🔍 Token Screener")
    
    with st.sidebar:
        st.header("Filters")
        chains = st.multiselect("Chains", ["base", "ethereum", "arbitrum", "optimism", "polygon", "bsc", "avalanche"], default=["base"])
        dexes = st.multiselect("DEXes", ["uniswap_v3", "uniswap_v4", "pancake_v3", "trader_joe_v3", "pons"], default=["uniswap_v3"])
        min_liq = st.number_input("Min Liquidity (USD)", value=50000, step=10000)
        max_age = st.number_input("Max Pool Age (hours)", value=24, step=1)
        min_score = st.slider("Min Score", 0, 100, 70)
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("🚀 Run Screener", type="primary", use_container_width=True):
            with st.spinner("Running screener..."):
                # In real app, call API
                st.success("Screener completed!")
    
    st.divider()
    
    # Results table
    st.subheader("Results")
    
    # Mock data for demonstration
    data = {
        "Token": ["SAMPLE", "TOKEN2", "TOKEN3"],
        "Chain": ["base", "base", "arbitrum"],
        "DEX": ["uniswap_v3", "uniswap_v3", "uniswap_v3"],
        "Score": [85, 78, 72],
        "Tier": ["A", "A", "B"],
        "Liquidity": ["$250K", "$180K", "$120K"],
        "24h Vol": ["$50K", "$35K", "$28K"],
        "Fee": ["0.3%", "0.3%", "0.05%"],
        "Recommendation": [
            "LP 2%, ±15%",
            "LP 1.5%, ±12%",
            "LP 1%, ±10%"
        ]
    }
    
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Visualization
    st.subheader("Score Distribution")
    fig = px.bar(pd.DataFrame({"Tier": ["A+", "A", "B", "C", "D"], "Count": [2, 5, 8, 3, 1]}),
                 x="Tier", y="Count", color="Tier",
                 color_discrete_map={"A+": "#00d16a", "A": "#1f77b4", "B": "#ffa502", "C": "#ff4b4b", "D": "#808080"})
    st.plotly_chart(fig, use_container_width=True)


def page_safety():
    """Safety check page."""
    st.title("🛡️ Safety Check")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Honeypot Check")
        token_address = st.text_input("Token Address", placeholder="0x...")
        chain = st.selectbox("Chain", ["base", "ethereum", "arbitrum", "optimism", "polygon", "bsc"])
        
        if st.button("🔍 Check Honeypot", type="primary"):
            with st.spinner("Checking..."):
                # Mock result
                result = {
                    "is_honeypot": False,
                    "buy_tax": 0.0,
                    "sell_tax": 0.0,
                    "transfer_tax": 0.0,
                    "can_buy": True,
                    "can_sell": True,
                    "owner": "0x123...",
                    "proxy": False,
                    "risks": []
                }
                st.session_state.safety_result = result
    
    with col2:
        st.subheader("Quick Stats")
        if "safety_result" in st.session_state:
            r = st.session_state.safety_result
            if r["is_honeypot"]:
                display_alert("critical", "⚠️ HONEYPOT DETECTED", "This token cannot be sold!")
            else:
                display_alert("success", "✅ Safe", "No honeypot detected")
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Buy Tax", f"{st.session_state.safety_result.get('buy_tax', 0)}%")
                st.metric("Sell Tax", f"{st.session_state.safety_result.get('sell_tax', 0)}%")
            with col_b:
                st.metric("Transfer Tax", f"{st.session_state.safety_result.get('transfer_tax', 0)}%")
                st.metric("Can Sell", "✅ Yes" if st.session_state.safety_result.get('can_sell') else "❌ No")
            
            if st.session_state.safety_result.get("risks"):
                st.warning("Risks: " + ", ".join(st.session_state.safety_result["risks"]))
            if st.session_state.safety_result.get("owner"):
                st.info(f"Owner: {st.session_state.safety_result['owner']}")
            if st.session_state.safety_result.get("proxy"):
                st.warning("⚠️ Proxy contract detected")


def page_lp_calculator():
    """LP Range Calculator page."""
    st.title("📐 LP Range Calculator")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Pool Parameters")
        chain = st.selectbox("Chain", ["base", "ethereum", "arbitrum", "optimism", "polygon"], key="lp_chain")
        pool_address = st.text_input("Pool Address", placeholder="0x...")
        
        col_a, col_b = st.columns(2)
        with col_a:
            center_price = st.number_input("Center Price", value=3000.0, step=10.0, format="%.2f")
            width_pct = st.slider("Range Width (%)", 1, 100, 20) / 100
        with col_b:
            amount0 = st.number_input("Amount Token0", value=1000.0, step=10.0)
            amount1 = st.number_input("Amount Token1", value=0.33, step=0.01, format="%.4f")
        
        col_c, col_d = st.columns(2)
        with col_c:
            token0_decimals = st.number_input("Token0 Decimals", value=6, min_value=0, max_value=18)
            fee_tier = st.selectbox("Fee Tier", [100, 500, 3000, 10000], index=2)
        with col_d:
            token1_decimals = st.number_input("Token1 Decimals", value=18, min_value=0, max_value=18)
    
    with col2:
        st.subheader("Calculation Result")
        if st.button("🧮 Calculate Range", type="primary", use_container_width=True):
            with st.spinner("Calculating..."):
                # Mock calculation
                from lib import price_to_tick, tick_to_price
                
                center_tick = 80067  # price_to_tick(3000)
                tick_spacing = 60
                width_pct = 0.20
                
                price_lower = 3000 * (1 - width_pct/2)
                price_upper = 3000 * (1 + width_pct/2)
                tick_lower = 77820
                tick_upper = 81840
                
                display_alert("info", "Range Calculated", 
                    f"Price: ${price_lower:,.2f} - ${price_upper:,.2f}\n"
                    f"Ticks: {tick_lower} - {tick_upper}\n"
                    f"In Range: ✅ Yes\n"
                    f"Risk Score: 72.3/100")
                
                # Visualization
                fig = go.Figure()
                fig.add_vline(x=3000, line_dash="dash", line_color="blue", annotation_text="Current")
                fig.add_vrect(x0=2400, x1=3600, fillcolor="green", opacity=0.1, annotation_text="Range")
                fig.update_layout(title="Price Range Visualization", xaxis_title="Price", yaxis_title="Density")
                st.plotly_chart(fig, use_container_width=True)
    
    # Tick/Price converter
    st.divider()
    st.subheader("🔄 Tick ↔ Price Converter")
    col1, col2 = st.columns(2)
    with col1:
        tick = st.number_input("Tick", value=80067)
        if st.button("Tick → Price"):
            price = 1.0001 ** tick
            st.success(f"Price: {price:.8f}")
    with col2:
        price = st.number_input("Price", value=3000.0)
        if st.button("Price → Tick"):
            import math
            tick = int(math.log(price) / math.log(1.0001))
            st.success(f"Tick: {tick}")


def page_rebalancer():
    """Rebalancer management page."""
    st.title("🔄 Position Rebalancer")
    
    tab1, tab2, tab3 = st.tabs(["📋 Positions", "➕ Add Position", "⚙️ Settings"])
    
    with tab1:
        st.subheader("Managed Positions")
        
        if "positions" not in st.session_state:
            st.session_state.positions = []
        
        if st.session_state.positions:
            for i, pos in enumerate(st.session_state.positions):
                with st.expander(f"{pos['token0_symbol']}/{pos['token1_symbol']} - {pos['chain']}/{pos['dex']}"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write(f"**Range:** {pos['tick_lower']} - {pos['tick_upper']}")
                        st.write(f"**Liquidity:** {pos['liquidity']:,}")
                    with col2:
                        st.write(f"**Fee Tier:** {pos['fee_tier']/10000*100:.2f}%")
                        st.write(f"**NFT ID:** {pos.get('nft_id', 'N/A')}")
                    with col3:
                        if st.button("🔄 Rebalance", key=f"reb_{i}"):
                            st.success("Rebalance initiated (dry run)")
                        if st.button("🗑️ Remove", key=f"rm_{i}"):
                            st.session_state.positions.pop(i)
                            st.rerun()
        else:
            st.info("No positions managed yet. Add one in the 'Add Position' tab.")
    
    with tab2:
        st.subheader("Add New Position")
        
        with st.form("add_position"):
            col1, col2 = st.columns(2)
            with col1:
                pool_address = st.text_input("Pool Address", placeholder="0x...")
                chain = st.selectbox("Chain", ["base", "ethereum", "arbitrum", "optimism", "polygon", "bsc", "avalanche"])
                dex = st.selectbox("DEX", ["uniswap_v3", "uniswap_v4", "pancake_v3", "trader_joe_v3", "pons"])
                token0 = st.text_input("Token0 Address", placeholder="0x...USDC")
                token1 = st.text_input("Token1 Address", placeholder="0x...WETH")
            with col2:
                token0_symbol = st.text_input("Token0 Symbol", value="USDC")
                token1_symbol = st.text_input("Token1 Symbol", value="WETH")
                token0_decimals = st.number_input("Token0 Decimals", value=6, min_value=0, max_value=18)
                token1_decimals = st.number_input("Token1 Decimals", value=18, min_value=0, max_value=18)
                tick_lower = st.number_input("Tick Lower", value=77820)
                tick_upper = st.number_input("Tick Upper", value=81840)
                liquidity = st.number_input("Liquidity", value=1000000000000000000, format="%d")
                fee_tier = st.selectbox("Fee Tier", [100, 500, 3000, 10000], index=2)
                nft_id = st.number_input("NFT ID (optional)", value=0, step=1)
            
            if st.form_submit_button("➕ Add Position", type="primary"):
                if pool_address:
                    pos = {
                        "pool_address": pool_address,
                        "chain": chain,
                        "dex": dex,
                        "token0": token0,
                        "token1": token1,
                        "token0_symbol": token0_symbol,
                        "token1_symbol": token1_symbol,
                        "token0_decimals": token0_decimals,
                        "token1_decimals": token1_decimals,
                        "tick_lower": tick_lower,
                        "tick_upper": tick_upper,
                        "liquidity": liquidity,
                        "fee_tier": fee_tier,
                        "nft_id": nft_id if nft_id > 0 else None,
                    }
                    st.session_state.positions.append(pos)
                    st.success("Position added!")
                    st.rerun()
                else:
                    st.error("Pool address required")
    
    with tab3:
        st.subheader("Rebalancer Settings")
        
        col1, col2 = st.columns(2)
        with col1:
            strategy = st.selectbox("Strategy", ["PASSIVE", "ACTIVE", "GAMMA", "GRID", "MEAN_REVERSION"])
            target_width = st.slider("Target Width (%)", 1, 100, 20)
            max_width = st.slider("Max Width (%)", 1, 100, 50)
            min_width = st.slider("Min Width (%)", 1, 50, 5)
        with col2:
            range_buffer = st.slider("Range Buffer (%)", 0.5, 10.0, 2.0) / 100
            max_slippage = st.slider("Max Slippage (%)", 0.1, 5.0, 0.5)
            max_gas = st.number_input("Max Gas (gwei)", value=30, step=5)
            dry_run = st.checkbox("Dry Run Mode", value=True)
        
        if st.button("💾 Save Settings"):
            st.success("Settings saved!")


def page_alerts():
    """Alerts and monitoring page."""
    st.title("🔔 Alerts & Monitoring")
    
    # Alert history
    st.subheader("Alert History")
    
    if "alerts" not in st.session_state:
        st.session_state.alerts = []
    
    if st.session_state.alerts:
        for alert in reversed(st.session_state.alerts[-10:]):
            level = alert.get("level", "info")
            icons = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️", "success": "✅"}
            st.markdown(f"""
            <div style="border-left: 4px solid {'#ff4b4b' if level=='critical' else '#ffa502' if level=='warning' else '#1f77b4' if level=='info' else '#00d16a'}; 
                        padding: 0.5rem; margin: 0.25rem 0; background: #f8f9fa;">
                <strong>{icons.get(level, '📢')} {alert['title']}</strong><br>
                <small>{alert['message']}</small><br>
                <small>⏰ {alert['timestamp']}</small>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No alerts yet")
    
    # Send test alert
    st.divider()
    st.subheader("Send Test Alert")
    
    with st.form("send_alert"):
        col1, col2 = st.columns(2)
        with col1:
            level = st.selectbox("Level", ["info", "warning", "critical", "success"])
            title = st.text_input("Title", "Test Alert")
        with col2:
            chain = st.text_input("Chain (optional)")
            dex = st.text_input("DEX (optional)")
        message = st.text_area("Message")
        
        if st.form_submit_button("📤 Send Alert"):
            alert = {
                "level": level,
                "title": title,
                "message": message,
                "chain": chain,
                "dex": dex,
                "timestamp": datetime.now().isoformat()
            }
            st.session_state.alerts.append(alert)
            st.success("Alert sent!")
            st.rerun()


# ===================== MAIN =====================

def main():
    # Sidebar navigation
    st.sidebar.title("📊 Token Research")
    st.sidebar.caption(f"v1.3.0")
    
    page = st.sidebar.radio(
        "Navigate",
        ["🏠 Overview", "🔍 Screener", "🛡️ Safety Check", "📐 LP Calculator", "🔄 Rebalancer", "🔔 Alerts"],
        label_visibility="collapsed"
    )
    
    st.sidebar.divider()
    
    # API Status
    st.sidebar.subheader("API Status")
    try:
        import requests
        resp = requests.get(f"{os.getenv('API_BASE', 'http://localhost:8000/api/v1').replace('/api/v1', '')}/health", timeout=2)
        if resp.status_code == 200:
            st.sidebar.success("🟢 API Connected")
        else:
            st.sidebar.warning("🟡 API Degraded")
    except Exception:
        st.sidebar.error("🔴 API Disconnected")
    
    st.sidebar.divider()
    
    # Quick stats
    st.sidebar.subheader("Quick Stats")
    st.sidebar.metric("Positions", "0")
    st.sidebar.metric("Alerts (24h)", "0")
    
    # Route to page
    if page == "🏠 Overview":
        page_overview()
    elif page == "🔍 Screener":
        page_screener()
    elif page == "🛡️ Safety Check":
        page_safety()
    elif page == "📐 LP Calculator":
        page_lp_calculator()
    elif page == "🔄 Rebalancer":
        page_rebalancer()
    elif page == "🔔 Alerts":
        page_alerts()


if __name__ == "__main__":
    main()