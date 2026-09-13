-- GoldAI Ultra — Multi-Market PostgreSQL Schema

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── SAVDOLAR (barcha bozorlar) ───────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    id              BIGSERIAL PRIMARY KEY,
    ticket          BIGINT UNIQUE,
    symbol          VARCHAR(20) NOT NULL,
    market_type     VARCHAR(20) NOT NULL,       -- forex | crypto | commodity | stock | index
    category        VARCHAR(30),                -- major | alt | tech | energy...
    side            VARCHAR(10) NOT NULL,
    lot             NUMERIC(12, 3),
    entry_price     NUMERIC(20, 8),
    stop_loss       NUMERIC(20, 8),
    take_profit     NUMERIC(20, 8),
    close_price     NUMERIC(20, 8),
    profit          NUMERIC(15, 2) DEFAULT 0,
    status          VARCHAR(20) DEFAULT 'OPEN',
    close_reason    VARCHAR(50),
    ai_confidence   NUMERIC(5, 2),
    tier            VARCHAR(20),               -- micro | mini | standard | advanced | pro
    whale_signal    BOOLEAN DEFAULT FALSE,
    comment         TEXT,
    open_time       TIMESTAMP DEFAULT NOW(),
    close_time      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_market_type ON trades(market_type);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);

-- ─── SIGNALLAR ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS signals (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL,
    market_type     VARCHAR(20),
    signal          VARCHAR(10) NOT NULL,
    confidence      NUMERIC(5, 2),
    entry_price     NUMERIC(20, 8),
    stop_loss       NUMERIC(20, 8),
    take_profit     NUMERIC(20, 8),
    rr_ratio        NUMERIC(6, 2),
    tier            VARCHAR(20),
    -- Agent balllari
    technical_score NUMERIC(6, 2),
    liquidity_score NUMERIC(6, 2),
    smc_score       NUMERIC(6, 2),
    whale_score     NUMERIC(6, 2),
    -- Whale
    whale_signal    VARCHAR(30),
    institutional   BOOLEAN DEFAULT FALSE,
    volume_spike    NUMERIC(8, 2),
    executed        BOOLEAN DEFAULT FALSE,
    reason          TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ─── WHALE FAOLIYATI ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS whale_activity (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL,
    signal          VARCHAR(30),               -- ACCUMULATION | DISTRIBUTION | STOP_HUNT
    direction       VARCHAR(10),
    confidence      NUMERIC(5, 2),
    volume_spike    NUMERIC(8, 2),
    order_size_usd  NUMERIC(20, 2),
    exchange        VARCHAR(30),
    institutional   BOOLEAN DEFAULT FALSE,
    open_interest_change NUMERIC(8, 4),
    description     TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_whale_symbol ON whale_activity(symbol);
CREATE INDEX IF NOT EXISTS idx_whale_created ON whale_activity(created_at);

-- ─── BALANS TARIXI ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS balance_history (
    id              BIGSERIAL PRIMARY KEY,
    balance         NUMERIC(15, 2),
    equity          NUMERIC(15, 2),
    tier            VARCHAR(20),
    capital_growth  NUMERIC(8, 4),
    recorded_at     TIMESTAMP DEFAULT NOW()
);

-- ─── KUNLIK STATISTIKA ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_stats (
    id              BIGSERIAL PRIMARY KEY,
    date            DATE UNIQUE,
    start_balance   NUMERIC(15, 2),
    end_balance     NUMERIC(15, 2),
    daily_pnl       NUMERIC(15, 2),
    trades_total    INTEGER DEFAULT 0,
    trades_win      INTEGER DEFAULT 0,
    win_rate        NUMERIC(5, 2),
    max_drawdown    NUMERIC(5, 2),
    tier            VARCHAR(20),
    -- Bozor bo'yicha taqsimot
    forex_trades    INTEGER DEFAULT 0,
    crypto_trades   INTEGER DEFAULT 0,
    commodity_trades INTEGER DEFAULT 0,
    stock_trades    INTEGER DEFAULT 0,
    index_trades    INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ─── VIEW: Multi-market performance ───────────────────────────
CREATE OR REPLACE VIEW market_performance AS
SELECT
    market_type,
    symbol,
    COUNT(*) AS total,
    SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) AS wins,
    ROUND(SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END)::NUMERIC / COUNT(*) * 100, 1) AS win_rate,
    ROUND(SUM(profit), 2) AS total_profit,
    ROUND(AVG(profit), 2) AS avg_profit
FROM trades
WHERE status = 'CLOSED'
GROUP BY market_type, symbol
ORDER BY total_profit DESC;

-- ─── VIEW: Tier progress ──────────────────────────────────────
CREATE OR REPLACE VIEW tier_progress AS
SELECT
    tier,
    COUNT(*) AS trades,
    ROUND(SUM(profit), 2) AS profit,
    ROUND(AVG(ai_confidence), 1) AS avg_confidence,
    ROUND(SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END)::NUMERIC / COUNT(*) * 100, 1) AS win_rate
FROM trades
WHERE status = 'CLOSED' AND tier IS NOT NULL
GROUP BY tier;

-- ─── VIEW: Whale summary ──────────────────────────────────────
CREATE OR REPLACE VIEW whale_summary AS
SELECT
    symbol,
    COUNT(*) AS total_alerts,
    SUM(CASE WHEN direction = 'BUY' THEN 1 ELSE 0 END) AS buy_alerts,
    SUM(CASE WHEN direction = 'SELL' THEN 1 ELSE 0 END) AS sell_alerts,
    ROUND(AVG(confidence), 1) AS avg_confidence,
    SUM(CASE WHEN institutional THEN 1 ELSE 0 END) AS institutional_count,
    MAX(created_at) AS last_alert
FROM whale_activity
GROUP BY symbol
ORDER BY total_alerts DESC;
