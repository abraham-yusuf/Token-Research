"""
Monitoring & Alert System

Supports:
- Telegram bot
- Webhook (Discord, Slack, custom)
- Console/logging
"""

import asyncio
import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
import aiohttp


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    SUCCESS = "success"


@dataclass
class Alert:
    level: AlertLevel
    title: str
    message: str
    chain: str = ""
    dex: str = ""
    token: str = ""
    pool_address: str = ""
    metadata: Dict = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}


class AlertChannel:
    """Base class for alert channels."""

    async def send(self, alert: Alert) -> bool:
        raise NotImplementedError


class ConsoleChannel(AlertChannel):
    """Print to console."""

    COLORS = {
        AlertLevel.INFO: "\033[94m",      # Blue
        AlertLevel.WARNING: "\033[93m",   # Yellow
        AlertLevel.CRITICAL: "\033[91m",  # Red
        AlertLevel.SUCCESS: "\033[92m",   # Green
    }
    RESET = "\033[0m"

    async def send(self, alert: Alert) -> bool:
        color = self.COLORS.get(alert.level, "")
        icon = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.CRITICAL: "🚨",
            AlertLevel.SUCCESS: "✅",
        }.get(alert.level, "📢")

        msg = f"{color}{icon} [{alert.level.value.upper()}] {alert.title}{self.RESET}\n"
        msg += f"  {alert.message}\n"
        if alert.chain:
            msg += f"  Chain: {alert.chain} | DEX: {alert.dex} | Token: {alert.token}\n"
        if alert.pool_address:
            msg += f"  Pool: {alert.pool_address}\n"
        print(msg)
        return True


class TelegramChannel(AlertChannel):
    """Send alerts via Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    async def send(self, alert: Alert) -> bool:
        icon = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.CRITICAL: "🚨",
            AlertLevel.SUCCESS: "✅",
        }.get(alert.level, "📢")

        text = f"{icon} <b>[{alert.level.value.upper()}] {alert.title}</b>\n\n"
        text += f"{alert.message}\n\n"
        if alert.chain:
            text += f"🔗 Chain: <code>{alert.chain}</code>\n"
        if alert.dex:
            text += f"📊 DEX: <code>{alert.dex}</code>\n"
        if alert.token:
            text += f"🪙 Token: <code>{alert.token}</code>\n"
        if alert.pool_address:
            text += f"🏊 Pool: <code>{alert.pool_address}</code>\n"
        text += f"🕐 Time: {alert.timestamp.isoformat()}Z"

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/sendMessage",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            print(f"Telegram send failed: {e}")
            return False


class WebhookChannel(AlertChannel):
    """Send alerts to custom webhook (Discord, Slack, etc.)."""

    def __init__(self, webhook_url: str, template: str = "discord"):
        self.webhook_url = webhook_url
        self.template = template

    def _format_discord(self, alert: Alert) -> Dict:
        color = {
            AlertLevel.INFO: 3447003,      # Blue
            AlertLevel.WARNING: 16776960,  # Yellow
            AlertLevel.CRITICAL: 15158332, # Red
            AlertLevel.SUCCESS: 3066993,   # Green
        }.get(alert.level, 0)

        embed = {
            "title": f"{alert.level.value.upper()}: {alert.title}",
            "description": alert.message,
            "color": color,
            "timestamp": alert.timestamp.isoformat() + "Z",
            "fields": []
        }

        if alert.chain:
            embed["fields"].append({"name": "Chain", "value": alert.chain, "inline": True})
        if alert.dex:
            embed["fields"].append({"name": "DEX", "value": alert.dex, "inline": True})
        if alert.token:
            embed["fields"].append({"name": "Token", "value": alert.token, "inline": True})
        if alert.pool_address:
            embed["fields"].append({"name": "Pool", "value": alert.pool_address, "inline": False})

        return {"embeds": [embed]}

    def _format_slack(self, alert: Alert) -> Dict:
        color = {
            AlertLevel.INFO: "#36a64f",
            AlertLevel.WARNING: "#ffcc00",
            AlertLevel.CRITICAL: "#ff0000",
            AlertLevel.SUCCESS: "#36a64f",
        }.get(alert.level, "#808080")

        fields = []
        for label, value in [
            ("Chain", alert.chain),
            ("DEX", alert.dex),
            ("Token", alert.token),
            ("Pool", alert.pool_address)
        ]:
            if value:
                fields.append({"title": label, "value": value, "short": True})

        return {
            "attachments": [{
                "color": color,
                "title": f"{alert.level.value.upper()}: {alert.title}",
                "text": alert.message,
                "fields": fields,
                "ts": int(alert.timestamp.timestamp())
            }]
        }

    def _format_generic(self, alert: Alert) -> Dict:
        return {
            "level": alert.level.value,
            "title": alert.title,
            "message": alert.message,
            "chain": alert.chain,
            "dex": alert.dex,
            "token": alert.token,
            "pool_address": alert.pool_address,
            "timestamp": alert.timestamp.isoformat() + "Z",
            "metadata": alert.metadata
        }

    async def send(self, alert: Alert) -> bool:
        if self.template == "discord":
            payload = self._format_discord(alert)
        elif self.template == "slack":
            payload = self._format_slack(alert)
        else:
            payload = self._format_generic(alert)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    return resp.status in (200, 201, 204)
        except Exception as e:
            print(f"Webhook send failed: {e}")
            return False


class AlertManager:
    """Central alert manager with multiple channels."""

    def __init__(self, config: Dict):
        self.channels: List[AlertChannel] = []
        self._setup_channels(config)

    def _setup_channels(self, config: Dict):
        # Always add console
        self.channels.append(ConsoleChannel())

        # Telegram
        if config.get("alerts", {}).get("enable_telegram"):
            token = config.get("alerts", {}).get("telegram_bot_token")
            chat_id = config.get("alerts", {}).get("telegram_chat_id")
            if token and chat_id:
                self.channels.append(TelegramChannel(token, chat_id))

        # Webhook
        if config.get("alerts", {}).get("enable_webhook"):
            url = config.get("alerts", {}).get("webhook_url")
            template = config.get("alerts", {}).get("webhook_template", "discord")
            if url:
                self.channels.append(WebhookChannel(url, template))

    async def send(self, alert: Alert):
        """Send alert to all configured channels."""
        tasks = [channel.send(alert) for channel in self.channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return all(r is True for r in results)

    async def send_info(self, title: str, message: str, **kwargs):
        await self.send(Alert(AlertLevel.INFO, title, message, **kwargs))

    async def send_warning(self, title: str, message: str, **kwargs):
        await self.send(Alert(AlertLevel.WARNING, title, message, **kwargs))

    async def send_critical(self, title: str, message: str, **kwargs):
        await self.send(Alert(AlertLevel.CRITICAL, title, message, **kwargs))

    async def send_success(self, title: str, message: str, **kwargs):
        await self.send(Alert(AlertLevel.SUCCESS, title, message, **kwargs))


# ===================== POSITION MONITOR =====================

class PositionMonitor:
    """Monitor LP positions for range exit, fee collection, etc."""

    def __init__(self, alert_manager: AlertManager, rpc_url: str):
        self.alert_manager = alert_manager
        self.rpc_url = rpc_url
        self.monitored_positions: Dict[str, Dict] = {}
        self.running = False

    def add_position(self, pool_address: str, chain: str, dex: str,
                     tick_lower: int, tick_upper: int,
                     token0: str, token1: str):
        """Add a position to monitor."""
        self.monitored_positions[pool_address] = {
            "chain": chain,
            "dex": dex,
            "tick_lower": tick_lower,
            "tick_upper": tick_upper,
            "token0": token0,
            "token1": token1,
            "last_alert_tick": None,
        }

    async def check_positions(self, rpc_client):
        """Check all monitored positions."""
        for pool_addr, pos in self.monitored_positions.items():
            try:
                # Fetch current tick from pool
                current_tick = await rpc_client.get_pool_tick(pool_addr)

                if current_tick is None:
                    continue

                # Check if out of range
                if current_tick < pos["tick_lower"] or current_tick > pos["tick_upper"]:
                    # Only alert once per exit
                    if pos["last_alert_tick"] != current_tick:
                        await self.alert_manager.send_warning(
                            title="Position Out of Range",
                            message=f"Position {pool_addr[:10]}... is now OUT OF RANGE. "
                                    f"Current tick: {current_tick}, "
                                    f"Range: {pos['tick_lower']} - {pos['tick_upper']}",
                            chain=pos["chain"],
                            dex=pos["dex"],
                            pool_address=pool_addr,
                            metadata={"current_tick": current_tick}
                        )
                        pos["last_alert_tick"] = current_tick
                else:
                    # Back in range - clear alert state
                    if pos["last_alert_tick"] is not None:
                        await self.alert_manager.send_success(
                            title="Position Back in Range",
                            message=f"Position {pool_addr[:10]}... is back IN RANGE. "
                                    f"Current tick: {current_tick}",
                            chain=pos["chain"],
                            dex=pos["dex"],
                            pool_address=pool_addr,
                        )
                        pos["last_alert_tick"] = None

            except Exception as e:
                print(f"Error checking position {pool_addr}: {e}")

    async def start_monitoring(self, rpc_client, interval_seconds: int = 60):
        """Start monitoring loop."""
        self.running = True
        while self.running:
            await self.check_positions(rpc_client)
            await asyncio.sleep(interval_seconds)

    def stop_monitoring(self):
        self.running = False


# ===================== EXAMPLE USAGE =====================

async def main():
    config = {
        "alerts": {
            "enable_telegram": False,
            "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
            "enable_webhook": False,
            "webhook_url": os.getenv("WEBHOOK_URL"),
            "webhook_template": "discord"
        }
    }

    manager = AlertManager(config)

    # Test alerts
    await manager.send_info("System Started", "Token research monitor is running")
    await manager.send_success("Test Complete", "All systems operational")

    print("Alert system test complete")


if __name__ == "__main__":
    asyncio.run(main())