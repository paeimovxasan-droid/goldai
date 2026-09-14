"""
GoldAI Ultra — Trade Log (odam o'qiydigan TXT jurnal)
Barcha savdo hodisalarini logs/trades.txt ga yozadi:
  - Ochilgan orderlar
  - Yopilgan orderlar (SL / TP / Manual)
  - SL tekshiruv natijalari
  - Balans bosqichlari
"""

import os
from datetime import datetime, timezone


class TradeLog:
    """Savdo jurnali — oddiy TXT fayl"""

    def __init__(self, log_dir: str = None):
        if log_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_dir = os.path.join(base, "logs")
        os.makedirs(log_dir, exist_ok=True)
        self._path = os.path.join(log_dir, "trades.txt")
        self._write_header()

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def _write(self, line: str):
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _write_header(self):
        if not os.path.exists(self._path):
            self._write("=" * 70)
            self._write("  GoldAI Ultra — Savdo Jurnali (Trade Log)")
            self._write("  $10 → $1,000,000 Capital Growth System")
            self._write("=" * 70)

    # ─── PUBLIC METODLAR ──────────────────────────────────────────

    def log_start(self, balance: float, mode: str, tier: str):
        self._write("")
        self._write("=" * 70)
        self._write(f"[{self._now()}] BOT ISHGA TUSHDI")
        self._write(f"  Rejim   : {mode}")
        self._write(f"  Balans  : ${balance:,.2f}")
        self._write(f"  Tier    : {tier.upper()}")
        self._write("=" * 70)

    def log_stop(self, reason: str = ""):
        self._write("")
        self._write(f"[{self._now()}] BOT TO'XTATILDI  {reason}")
        self._write("-" * 70)

    def log_open(self, ticket: int, symbol: str, side: str, lot: float,
                 entry: float, sl: float, tp: float, tier: str,
                 confidence: float, rr: float, source: str = ""):
        tag = f"[{source.upper()}]" if source else ""
        self._write("")
        self._write(f"[{self._now()}] OCHILDI {tag}")
        self._write(f"  Ticket  : #{ticket}")
        self._write(f"  Symbol  : {symbol}  ({side})")
        self._write(f"  Lot     : {lot}")
        self._write(f"  Entry   : {entry:,.5f}")
        self._write(f"  SL      : {sl:,.5f}")
        self._write(f"  TP      : {tp:,.5f}")
        self._write(f"  R:R     : {rr:.2f}  |  Ishonch: {confidence:.1f}%")
        self._write(f"  Tier    : {tier.upper()}")

    def log_close(self, ticket: int, symbol: str, side: str,
                  entry: float, close_price: float, profit: float,
                  reason: str):
        sign = "+" if profit >= 0 else ""
        result = "WIN" if profit > 0 else ("LOSS" if profit < 0 else "BREAKEVEN")
        self._write("")
        self._write(f"[{self._now()}] YOPILDI — {reason}  [{result}]")
        self._write(f"  Ticket  : #{ticket}")
        self._write(f"  Symbol  : {symbol}  ({side})")
        self._write(f"  Entry   : {entry:,.5f}")
        self._write(f"  Yopildi : {close_price:,.5f}")
        self._write(f"  Foyda   : {sign}{profit:,.2f} $")
        self._write(f"  Sabab   : {reason}")

    def log_sl_hit(self, ticket: int, symbol: str, price: float, loss: float):
        self._write("")
        self._write(f"[{self._now()}] *** STOP LOSS URILDI ***")
        self._write(f"  Ticket  : #{ticket}  {symbol}")
        self._write(f"  SL narx : {price:,.5f}")
        self._write(f"  Zarar   : -{abs(loss):,.2f} $")

    def log_tp_hit(self, ticket: int, symbol: str, price: float, profit: float):
        self._write("")
        self._write(f"[{self._now()}] *** TAKE PROFIT OLINDI ***")
        self._write(f"  Ticket  : #{ticket}  {symbol}")
        self._write(f"  TP narx : {price:,.5f}")
        self._write(f"  Foyda   : +{profit:,.2f} $")

    def log_sl_missing(self, symbol: str, ticket: int, action: str):
        self._write("")
        self._write(f"[{self._now()}] !!! SL YO'Q — HIMOYA FAOLLASHDI !!!")
        self._write(f"  Symbol  : {symbol}  #{ticket}")
        self._write(f"  Harakat : {action}")

    def log_balance(self, balance: float, equity: float, tier: str, growth_pct: float):
        self._write("")
        self._write(f"[{self._now()}] BALANS YANGILANDI")
        self._write(f"  Balans  : ${balance:,.2f}")
        self._write(f"  Equity  : ${equity:,.2f}")
        self._write(f"  Tier    : {tier.upper()}")
        self._write(f"  O'sish  : {growth_pct:+.2f}%")

    def log_tier_up(self, old_tier: str, new_tier: str, balance: float):
        self._write("")
        self._write("=" * 70)
        self._write(f"[{self._now()}] *** YANGI BOSQICH! ***")
        self._write(f"  {old_tier.upper()} => {new_tier.upper()}")
        self._write(f"  Balans  : ${balance:,.2f}")
        self._write("=" * 70)

    def log_risk_breach(self, reason: str, daily_loss: float, drawdown: float):
        self._write("")
        self._write(f"[{self._now()}] !!! RISK LIMITI URILDI !!!")
        self._write(f"  Sabab      : {reason}")
        self._write(f"  Kunlik zarar: {daily_loss:.2f}%")
        self._write(f"  Drawdown   : {drawdown:.2f}%")


# Global instance
trade_log = TradeLog()
