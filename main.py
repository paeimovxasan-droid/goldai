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
    orchestrator = UltraOrchestrator()
    orchestrator.initialize()
    yield
    if orchestrator:
        orchestrator.stop()


app = FastAPI(
    title="GoldAI Ultra — Libertex Edition",
    description="Libertex (ForexClub) MT5 — Forex | Crypto | Stocks | Commodities | $10→$1M",
    version="2.1.0-libertex",
    lifespan=lifespan
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
async def root():
    return {"name": "GoldAI Ultra", "version": "2.0.0", "markets": len(MARKETS)}


@app.get("/api/v2/dashboard")
async def dashboard():
    """To'liq dashboard ma'lumoti"""
    account = orchestrator.market.get_account_info()
    balance = account.get("balance", 0)
    equity = account.get("equity", 0)

    risk_status = orchestrator.risk.check_risk(balance, equity)
    positions = orchestrator.market.get_all_positions()
    stats = orchestrator.risk.get_statistics(balance)
    dyn_params = orchestrator.risk.get_dynamic_params(balance)
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
            "running": orchestrator._running,
            "cycles": orchestrator._cycle_count,
            "trades_today": orchestrator._trades_today,
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/v2/markets")
async def get_markets():
    """Barcha bozorlar ro'yxati"""
    account = orchestrator.market.get_account_info()
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
    tick = orchestrator.market.get_tick(symbol)
    if not tick:
        raise HTTPException(404, f"{symbol} tick olinmadi")
    return tick


@app.get("/api/v2/market/{symbol}/ohlc")
async def get_ohlc(symbol: str, timeframe: str = "M15", bars: int = 100):
    df = await orchestrator.market.get_ohlc_async(symbol, timeframe, bars)
    if df is None:
        raise HTTPException(404, "OHLC olinmadi")
    return df.tail(bars).reset_index().to_dict(orient="records")


@app.get("/api/v2/whale/{symbol}")
async def get_whale(symbol: str):
    """Whale faoliyati"""
    account = orchestrator.market.get_account_info()
    df = await orchestrator.market.get_ohlc_async(symbol, "M15", 100)
    if df is None:
        raise HTTPException(404, "Ma'lumot yo'q")
    activity = await orchestrator.whale.analyze_whale_activity(symbol, df)
    return {
        "symbol": symbol,
        "signal": activity.signal.value,
        "direction": activity.direction,
        "confidence": activity.confidence,
        "volume_spike": activity.volume_spike,
        "institutional": activity.institutional_flow,
        "description": activity.description,
        "summary": orchestrator.whale.get_whale_summary(symbol)
    }


@app.get("/api/v2/whale/orderflow/{symbol}")
async def get_orderflow(symbol: str):
    flow = orchestrator.whale.get_order_flow(symbol)
    if not flow:
        raise HTTPException(404, "Order flow ma'lumoti yo'q")
    return vars(flow)


@app.get("/api/v2/scan")
async def scan_markets():
    """Barcha bozorlarni skanerlash"""
    account = orchestrator.market.get_account_info()
    balance = account.get("balance", 0)
    market_data = await orchestrator.market.scan_all_markets(balance)
    scan = await orchestrator.scanner.scan_all(market_data, balance)

    return {
        "total_scanned": scan.total_scanned,
        "total_signals": scan.total_signals,
        "scan_time_ms": scan.scan_time_ms,
        "best_signals": [vars(s) for s in scan.best_signals],
        "market_overview": scan.market_overview
    }


@app.get("/api/v2/performance")
async def get_performance():
    account = orchestrator.market.get_account_info()
    balance = account.get("balance", 0)
    stats = orchestrator.risk.get_statistics(balance)
    next_tier = orchestrator.risk._next_tier_target(balance)
    return {**stats, "next_tier": next_tier}


@app.post("/api/v2/trade/close-all")
async def close_all():
    results = orchestrator.execution.close_all_positions("API Manual")
    return {"closed": len(results)}


@app.post("/api/v2/trade/close/{ticket}")
async def close_one(ticket: int):
    r = orchestrator.execution.close_position(ticket)
    if not r.success:
        raise HTTPException(400, r.error)
    return vars(r)


@app.post("/api/v2/system/start")
async def start(background_tasks: BackgroundTasks):
    background_tasks.add_task(orchestrator.start)
    return {"status": "started"}


@app.post("/api/v2/system/stop")
async def stop():
    orchestrator.stop()
    return {"status": "stopped"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
