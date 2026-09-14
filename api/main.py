"""
GoldAI Ultra — FastAPI Server
Multi-market REST API
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
import asyncio
import uvicorn

from core.config import config, MARKETS
from core.logger import logger
from core.orchestrator import UltraOrchestrator


orchestrator: Optional[UltraOrchestrator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    # run.py's combined mode injects the same orchestrator used by the bot.
    # The old code created a second instance and also forgot to await init().
    orchestrator = getattr(app.state, "orchestrator", None)
    owns_orchestrator = orchestrator is None
    if owns_orchestrator:
        orchestrator = UltraOrchestrator()
        app.state.orchestrator = orchestrator
        await orchestrator.initialize()
    yield
    if owns_orchestrator and orchestrator:
        await orchestrator.stop_async()


def _get_orchestrator() -> UltraOrchestrator:
    if orchestrator is None:
        raise HTTPException(503, "GoldAI hali ishga tushmagan")
    return orchestrator


app = FastAPI(
    title="GoldAI Ultra — Libertex Edition",
    description="Libertex (ForexClub) MT5 — Forex | Crypto | Stocks | Commodities | $10→$1M",
    version="2.2.0-libertex",
    lifespan=lifespan
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
async def root():
    return {
        "name": "GoldAI Ultra",
        "version": "2.2.0",
        "markets": len(MARKETS),
        "mt5_server": config.mt5.server,
        "ai_failover": ["deepseek", "gemini", "openai"],
    }


@app.get("/api/v2/health")
async def health():
    """Startup-safe health signal used by the launcher/monitoring."""
    if orchestrator is None:
        return {"status": "starting", "mt5_connected": False}
    return {
        "status": "ok" if orchestrator.market.mt5_connected else "degraded",
        "running": orchestrator._running,
        "mt5_connected": orchestrator.market.mt5_connected,
        "mt5_server": orchestrator.market.connected_server or config.mt5.server,
        "mt5_error": orchestrator.market.last_connection_error,
        "ai": orchestrator.ai.provider_status(),
    }


@app.get("/api/v2/dashboard")
async def dashboard():
    """To'liq dashboard ma'lumoti"""
    o = _get_orchestrator()
    account = o.market.get_account_info()
    balance = account.get("balance", 0)
    equity = account.get("equity", 0)

    risk_status = o.risk.check_risk(balance, equity)
    positions = o.market.get_all_positions()
    stats = o.risk.get_statistics(balance)
    dyn_params = o.risk.get_dynamic_params(balance)
    active_symbols = config.get_active_symbols(balance)

    return {
        "account": account,
        "positions": positions,
        "risk": {
            "tier": risk_status.tier,
            "is_safe": risk_status.is_safe,
            "daily_loss_pct": risk_status.daily_loss_pct,
            "drawdown_pct": risk_status.drawdown_pct,
            "open_positions": risk_status.open_positions,
            "max_positions": risk_status.max_positions,
            "capital_growth_pct": risk_status.capital_growth_pct,
            "message": risk_status.message
        },
        "performance": stats,
        "trading": {
            "risk_pct": dyn_params.risk_pct * 100,
            "risk_amount": dyn_params.risk_amount,
            "compound_mult": dyn_params.compound_multiplier,
            "active_markets": len(active_symbols),
            "active_symbols": active_symbols
        },
        "system": {
            "running": o._running,
            "cycles": o._cycle_count,
            "trades_today": o._trades_today,
            "mode": o._mode,
            "mt5_connected": o.market.mt5_connected,
            "mt5_server": o.market.connected_server or config.mt5.server,
        },
        "ai": o.ai.provider_status(),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/v2/markets")
async def get_markets():
    """Barcha bozorlar ro'yxati"""
    o = _get_orchestrator()
    account = o.market.get_account_info()
    balance = account.get("balance", 0)
    active = config.get_active_symbols(balance)

    return {
        "all_markets": MARKETS,
        "active_symbols": active,
        "tier": config.risk.get_for_balance(balance)["tier"],
        "tier_breakdown": config.market_tiers
    }


@app.get("/api/v2/market/{symbol}/tick")
async def get_tick(symbol: str):
    o = _get_orchestrator()
    tick = o.market.get_tick(symbol)
    if not tick:
        raise HTTPException(404, f"{symbol} tick olinmadi")
    return tick


@app.get("/api/v2/market/{symbol}/ohlc")
async def get_ohlc(symbol: str, timeframe: str = "M15", bars: int = 100):
    o = _get_orchestrator()
    df = await o.market.get_ohlc_async(symbol, timeframe, bars)
    if df is None:
        raise HTTPException(404, "OHLC olinmadi")
    return df.tail(bars).reset_index().to_dict(orient="records")


@app.get("/api/v2/whale/{symbol}")
async def get_whale(symbol: str):
    """Whale faoliyati"""
    o = _get_orchestrator()
    account = o.market.get_account_info()
    df = await o.market.get_ohlc_async(symbol, "M15", 100)
    if df is None:
        raise HTTPException(404, "Ma'lumot yo'q")
    activity = await o.whale.analyze_whale_activity(symbol, df)
    return {
        "symbol": symbol,
        "signal": activity.signal.value,
        "direction": activity.direction,
        "confidence": activity.confidence,
        "volume_spike": activity.volume_spike,
        "institutional": activity.institutional_flow,
        "description": activity.description,
        "summary": o.whale.get_whale_summary(symbol)
    }


@app.get("/api/v2/whale/orderflow/{symbol}")
async def get_orderflow(symbol: str):
    o = _get_orchestrator()
    flow = o.whale.get_order_flow(symbol)
    if not flow:
        raise HTTPException(404, "Order flow ma'lumoti yo'q")
    return vars(flow)


@app.get("/api/v2/scan")
async def scan_markets():
    """Barcha bozorlarni skanerlash"""
    o = _get_orchestrator()
    account = o.market.get_account_info()
    balance = account.get("balance", 0)
    market_data = await o.market.scan_all_markets(balance)
    scan = await o.scanner.scan_all(market_data, balance)

    return {
        "total_scanned": scan.total_scanned,
        "total_signals": scan.total_signals,
        "scan_time_ms": scan.scan_time_ms,
        "best_signals": [vars(s) for s in scan.best_signals],
        "market_overview": scan.market_overview
    }


@app.get("/api/v2/performance")
async def get_performance():
    o = _get_orchestrator()
    account = o.market.get_account_info()
    balance = account.get("balance", 0)
    stats = o.risk.get_statistics(balance)
    next_tier = o.risk._next_tier_target(balance)
    return {**stats, "next_tier": next_tier}


@app.post("/api/v2/trade/close-all")
async def close_all():
    o = _get_orchestrator()
    results = o.execution.close_all_positions("API Manual")
    return {"closed": len(results)}


@app.post("/api/v2/trade/close/{ticket}")
async def close_one(ticket: int):
    o = _get_orchestrator()
    r = o.execution.close_position(ticket)
    if not r.success:
        raise HTTPException(400, r.error)
    return vars(r)


@app.post("/api/v2/system/start")
async def start(background_tasks: BackgroundTasks):
    o = _get_orchestrator()
    background_tasks.add_task(o.start)
    return {"status": "started"}


@app.post("/api/v2/system/stop")
async def stop():
    o = _get_orchestrator()
    await o.stop_async()
    return {"status": "stopped"}


if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
