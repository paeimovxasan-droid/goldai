"""
GoldAI Ultra — Dynamic Risk Engine
$10 → $1,000,000 Capital Growth System
Dinamik risk — balans oshgani sayin kengayadi
"""

import numpy as np
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from core.config import config, MARKETS
from core.logger import logger


@dataclass
class DynamicRiskParams:
    tier: str
    balance: float
    risk_pct: float
    risk_amount: float
    daily_limit_pct: float
    daily_limit_amount: float
    max_positions: int
    active_symbols: list
    compound_multiplier: float


@dataclass
class PositionSize:
    lot: float
    risk_amount: float
    sl_distance: float
    tp_distance: float
    rr_ratio: float
    allowed: bool
    reason: str


@dataclass
class RiskStatus:
    is_safe: bool
    tier: str
    balance: float
    equity: float
    daily_loss_pct: float
    weekly_loss_pct: float
    drawdown_pct: float
    open_positions: int
    max_positions: int
    available_risk_pct: float
    capital_growth_pct: float
    message: str


class DynamicRiskEngine:
    """
    Kapital o'sishi tizimi ($10 → $1,000,000):
    - $10–100:     Micro   (0.3% risk, 1 pozitsiya)
    - $100–500:    Mini    (0.5% risk, 2 pozitsiya)
    - $500–2000:   Standard(0.7% risk, 3 pozitsiya)
    - $2000–5000:  Advanced(1.0% risk, 4 pozitsiya)
    - $5000–10000: Pro     (1.2% risk, 5 pozitsiya)
    - $10K–50K:    Elite   (1.5% risk, 6 pozitsiya)
    - $50K–200K:   Master  (1.8% risk, 8 pozitsiya)
    - $200K–1M:    Legend  (2.0% risk, 10 pozitsiya)
    """

    def __init__(self):
        self._start_balance: float = 0.0
        self._peak_balance: float = 0.0
        self._daily_start: float = 0.0
        self._weekly_start: float = 0.0
        self._last_day: int = -1
        self._last_week: int = -1
        self._trade_count: int = 0
        self._win_count: int = 0
        self._loss_count: int = 0

    def initialize(self, balance: float):
        self._start_balance = balance
        self._peak_balance = balance
        self._daily_start = balance
        self._weekly_start = balance
        logger.info(
            f"💰 Risk Engine: Boshlang'ich=${balance:.2f} | "
            f"Tier={self._get_tier(balance)}"
        )

    def _get_tier(self, balance: float) -> str:
        params = config.risk.get_for_balance(balance)
        return params["tier"]

    def get_dynamic_params(self, balance: float) -> DynamicRiskParams:
        """Balansga mos dinamik risk parametrlari"""
        params = config.risk.get_for_balance(balance)
        tier = params["tier"]
        risk_pct = params["risk_pct"]
        risk_amount = balance * risk_pct

        # Compound effect — balans o'sgani sayin compound multiplier
        if self._start_balance > 0:
            growth_factor = balance / self._start_balance
            # O'sish bo'lsa bir oz ko'proq risk (max 1.5x)
            compound_mult = min(1.5, 1.0 + (growth_factor - 1) * 0.1)
        else:
            compound_mult = 1.0

        return DynamicRiskParams(
            tier=tier,
            balance=balance,
            risk_pct=risk_pct,
            risk_amount=risk_amount * compound_mult,
            daily_limit_pct=params["daily_limit"],
            daily_limit_amount=balance * params["daily_limit"],
            max_positions=params["max_positions"],
            active_symbols=config.get_active_symbols(balance),
            compound_multiplier=round(compound_mult, 3)
        )

    def check_risk(self, balance: float, equity: float, open_positions_count: int = -1) -> RiskStatus:
        """Risk holatini tekshirish"""
        now = datetime.now()

        # Kunlik reset
        if now.day != self._last_day:
            self._daily_start = balance
            self._last_day = now.day

        # Haftalik reset (Dushanba)
        if now.weekday() == 0 and now.isocalendar()[1] != self._last_week:
            self._weekly_start = balance
            self._last_week = now.isocalendar()[1]

        # Peak yangilash
        if equity > self._peak_balance:
            self._peak_balance = equity

        params = config.risk.get_for_balance(balance)
        dyn = self.get_dynamic_params(balance)

        # Hisoblash
        daily_loss = (self._daily_start - equity) / (self._daily_start + 1e-10)
        weekly_loss = (self._weekly_start - equity) / (self._weekly_start + 1e-10)
        drawdown = (self._peak_balance - equity) / (self._peak_balance + 1e-10)
        capital_growth = (balance - self._start_balance) / (self._start_balance + 1e-10) * 100

        # Ochiq pozitsiyalar (tashqaridan berilishi mumkin yoki MT5'dan)
        if open_positions_count >= 0:
            open_count = open_positions_count
        else:
            try:
                if mt5 is None:
                    open_count = 0
                else:
                    positions = mt5.positions_get()
                    open_count = len(positions) if positions else 0
            except Exception:
                open_count = 0

        messages = []
        is_safe = True

        if daily_loss >= params["daily_limit"]:
            is_safe = False
            messages.append(f"❌ Kunlik limit {daily_loss*100:.1f}% (max {params['daily_limit']*100:.0f}%)")

        if weekly_loss >= config.risk.max_weekly_loss:
            is_safe = False
            messages.append(f"❌ Haftalik limit {weekly_loss*100:.1f}%")

        if drawdown >= config.risk.max_drawdown:
            is_safe = False
            messages.append(f"❌ Drawdown {drawdown*100:.1f}% (max 20%)")

        if open_count >= params["max_positions"]:
            is_safe = False
            messages.append(f"❌ Pozitsiya limiti {open_count}/{params['max_positions']}")

        available = max(0, params["daily_limit"] - daily_loss)

        tier = params["tier"]
        if not messages:
            messages.append(f"✅ {tier.upper()} tier | Kapital o'sishi: +{capital_growth:.1f}%")

        return RiskStatus(
            is_safe=is_safe,
            tier=tier,
            balance=balance,
            equity=equity,
            daily_loss_pct=round(daily_loss * 100, 2),
            weekly_loss_pct=round(weekly_loss * 100, 2),
            drawdown_pct=round(drawdown * 100, 2),
            open_positions=open_count,
            max_positions=params["max_positions"],
            available_risk_pct=round(available * 100, 2),
            capital_growth_pct=round(capital_growth, 2),
            message=" | ".join(messages)
        )

    def calculate_lot(
        self,
        symbol: str,
        balance: float,
        entry: float,
        stop_loss: float,
        take_profit: float,
        symbol_info: dict
    ) -> PositionSize:
        """Universal lot hisoblash — barcha bozorlar uchun"""
        dyn = self.get_dynamic_params(balance)
        risk_amount = dyn.risk_amount

        sl_distance = abs(entry - stop_loss)
        tp_distance = abs(entry - take_profit)

        if sl_distance < 1e-10:
            return PositionSize(0, 0, 0, 0, 0, False, "SL 0 bo'lmasin")

        rr = tp_distance / sl_distance
        if rr < config.risk.min_rr_ratio:
            return PositionSize(
                0, 0, sl_distance, tp_distance, round(rr, 2), False,
                f"R:R {rr:.2f} < minimum {config.risk.min_rr_ratio}"
            )

        market = MARKETS.get(symbol, {})
        market_type = market.get("type", "forex")

        # Lot hisoblash — bozor turiga qarab
        if market_type == "forex":
            # Forex: 1 pip = $10 per standard lot
            pip = market.get("pip", 0.0001)
            pip_value = 10.0  # Standard lot uchun
            sl_pips = sl_distance / pip
            lot = risk_amount / (sl_pips * pip_value)

        elif market_type == "commodity":
            # XAUUSD: 1 point = $1 per 0.01 lot
            tick_val = symbol_info.get("trade_tick_value", 0.01)
            tick_size = symbol_info.get("trade_tick_size", 0.01)
            if tick_val > 0 and tick_size > 0:
                lot = risk_amount / (sl_distance / tick_size * tick_val)
            else:
                lot = risk_amount / (sl_distance * 10)

        elif market_type == "crypto":
            # Crypto: direct
            contract = market.get("contract", 1)
            lot = risk_amount / (sl_distance * contract)

        elif market_type in ["index", "stock"]:
            # Index/Stock CFD
            tick_val = symbol_info.get("trade_tick_value", 0.1)
            tick_size = symbol_info.get("trade_tick_size", 0.1)
            if tick_val > 0 and tick_size > 0:
                lot = risk_amount / (sl_distance / tick_size * tick_val)
            else:
                lot = risk_amount / sl_distance

        else:
            lot = dyn.risk_amount / (sl_distance * 10)

        # Chegaralar
        min_lot = symbol_info.get("volume_min", market.get("min_lot", 0.01))
        max_lot = symbol_info.get("volume_max", 100.0)
        step = symbol_info.get("volume_step", 0.01)

        lot = round(lot / step) * step
        lot = max(min_lot, min(max_lot, lot))
        lot = round(lot, 2)

        logger.info(
            f"📐 Lot [{symbol}/{market_type}]: "
            f"${risk_amount:.2f} risk | SL:{sl_distance:.4f} | "
            f"Lot:{lot} | R:R:{rr:.2f}"
        )

        return PositionSize(
            lot=lot,
            risk_amount=round(risk_amount, 2),
            sl_distance=round(sl_distance, 5),
            tp_distance=round(tp_distance, 5),
            rr_ratio=round(rr, 2),
            allowed=True,
            reason=f"✅ Lot:{lot} | Risk:${risk_amount:.2f} | Tier:{dyn.tier} | R:R:{rr:.2f}"
        )

    def calculate_smart_sl(
        self,
        symbol: str,
        side: str,
        entry: float,
        raw_sl: float,
        df,
        atr: float
    ) -> float:
        """
        Stop-hunt bo'lmasin deb SL ni aqlli joylashtirish:
        1. Swing low/high dan nariroqqa qo'yish
        2. Yumaloq sonlardan qochish
        3. ATR ning oddiy ko'paytmasidan qochish
        4. Likvidlik zonasidan uzoqroqqa siljitish
        """
        if atr <= 0 or raw_sl <= 0:
            return raw_sl

        # ── 1. Swing Low/High dan strukturaviy SL ─────────────────
        try:
            if len(df) >= 10:
                lows  = df["low"].values[-20:]
                highs = df["high"].values[-20:]

                if side == "BUY":
                    # BUY: SL swing low dan pastda
                    swing_lows = []
                    for i in range(2, len(lows) - 2):
                        if lows[i] < lows[i-1] and lows[i] < lows[i+1] and \
                           lows[i] < lows[i-2] and lows[i] < lows[i+2]:
                            swing_lows.append(lows[i])
                    if swing_lows:
                        nearest_sw_low = max(sl for sl in swing_lows if sl < entry)
                        if nearest_sw_low:
                            structural_sl = nearest_sw_low - atr * 0.3
                            # Swing low'dan tashqarida bo'lsa — ishlatamiz
                            if structural_sl < raw_sl:
                                raw_sl = structural_sl
                else:
                    # SELL: SL swing high dan ustida
                    swing_highs = []
                    for i in range(2, len(highs) - 2):
                        if highs[i] > highs[i-1] and highs[i] > highs[i+1] and \
                           highs[i] > highs[i-2] and highs[i] > highs[i+2]:
                            swing_highs.append(highs[i])
                    if swing_highs:
                        nearest_sw_high = min(sh for sh in swing_highs if sh > entry)
                        if nearest_sw_high:
                            structural_sl = nearest_sw_high + atr * 0.3
                            if structural_sl > raw_sl:
                                raw_sl = structural_sl
        except Exception:
            pass

        # ── 2. Yumaloq sonlardan qochish ──────────────────────────
        raw_sl = self._avoid_round_number(raw_sl, entry, side, atr)

        # ── 3. ATR ko'paytmasidan qochish (1x, 1.5x, 2x) ─────────
        raw_sl = self._avoid_atr_multiple(raw_sl, entry, side, atr)

        # ── 4. Minimum buffer (spread + shlippage) ────────────────
        min_dist = atr * 0.4
        if side == "BUY" and entry - raw_sl < min_dist:
            raw_sl = entry - min_dist
        elif side == "SELL" and raw_sl - entry < min_dist:
            raw_sl = entry + min_dist

        return round(raw_sl, 5)

    def _avoid_round_number(self, sl: float, entry: float, side: str, atr: float) -> float:
        """SL yumaloq songa tushib qolsa, biroz siljitish"""
        # Yumaloq son ekanini tekshirish
        magnitudes = [1, 10, 100, 1000, 10000]
        for mag in magnitudes:
            rounded = round(sl / mag) * mag
            if abs(sl - rounded) < atr * 0.15:
                # Yumaloqdan uzoqlash — hunters bu darajani targetlaydi
                buffer = atr * 0.2
                if side == "BUY":
                    sl = rounded - buffer   # Yanada pastroq
                else:
                    sl = rounded + buffer   # Yanada yuqoriroq
                break
        return sl

    def _avoid_atr_multiple(self, sl: float, entry: float, side: str, atr: float) -> float:
        """ATR ning oddiy ko'paytmasidagi SL larni siljitish"""
        sl_dist = abs(entry - sl)
        atr_multiples = [1.0, 1.5, 2.0, 2.5, 3.0]
        buffer = atr * 0.12

        for mult in atr_multiples:
            target_dist = atr * mult
            if abs(sl_dist - target_dist) < buffer:
                # Obvious ATR multiple — siljitamiz
                extra = atr * 0.18
                if side == "BUY":
                    sl = entry - (sl_dist + extra)
                else:
                    sl = entry + (sl_dist + extra)
                break
        return sl

    def record_trade_result(self, profit: float):
        """Savdo natijasini yozish"""
        self._trade_count += 1
        if profit > 0:
            self._win_count += 1
        else:
            self._loss_count += 1

    def get_statistics(self, balance: float) -> dict:
        """Performance statistika"""
        win_rate = self._win_count / max(1, self._trade_count) * 100
        growth = (balance - self._start_balance) / max(1, self._start_balance) * 100

        return {
            "total_trades": self._trade_count,
            "wins": self._win_count,
            "losses": self._loss_count,
            "win_rate": round(win_rate, 1),
            "capital_growth_pct": round(growth, 2),
            "start_balance": self._start_balance,
            "peak_balance": self._peak_balance,
            "current_tier": self._get_tier(balance),
            "next_tier_target": self._next_tier_target(balance),
        }

    def _next_tier_target(self, balance: float) -> dict:
        """Keyingi bosqichga qancha kerak"""
        targets = {
            "micro":    100,
            "mini":     500,
            "standard": 2000,
            "advanced": 5000,
            "pro":      10000,
            "elite":    50000,
            "master":   200000,
            "legend":   1000000,
        }
        tier = self._get_tier(balance)
        target = targets.get(tier, 1000000)
        needed = max(0, target - balance)
        return {
            "current_tier": tier,
            "target_amount": target,
            "needed": round(needed, 2),
            "progress_pct": round(balance / target * 100, 1)
        }
