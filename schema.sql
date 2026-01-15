-- Database Schema for Market Pulse ETL

-- Table: dim_stock (Dimension Table for Stocks)
CREATE TABLE IF NOT EXISTS dim_stock (
    stock_id VARCHAR(20) PRIMARY KEY,
    company_name VARCHAR(100),
    exchange VARCHAR(50),
    category VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: fact_price (Fact Table for Daily Stock Prices)
CREATE TABLE IF NOT EXISTS fact_price (
    stock_id VARCHAR(20) REFERENCES dim_stock(stock_id),
    date DATE,
    open DECIMAL(16, 4),
    high DECIMAL(16, 4),
    low DECIMAL(16, 4),
    close DECIMAL(16, 4),
    volume BIGINT,
    adj_close DECIMAL(16, 4),
    ma_5 DECIMAL(16, 4),
    ma_20 DECIMAL(16, 4),
    foreign_net BIGINT DEFAULT 0,
    trust_net BIGINT DEFAULT 0,
    dealer_net BIGINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Composite primary key to prevent duplicate entries for the same stock and date
    PRIMARY KEY (stock_id, date)
);

-- Table: ai_analysis (AI Predictions and Analysis)
CREATE TABLE IF NOT EXISTS ai_analysis (
    id SERIAL PRIMARY KEY,
    stock_id VARCHAR(20) REFERENCES dim_stock(stock_id),
    date DATE,
    signal VARCHAR(10), -- 'Bull' or 'Bear'
    probability DECIMAL(5, 4),
    entry_price DECIMAL(16, 4),
    target_price DECIMAL(16, 4),
    stop_loss DECIMAL(16, 4),
    actual_close DECIMAL(16, 4),   -- 實際收盤價
    is_correct BOOLEAN,           -- AI 猜對了嗎？
    return_pct DECIMAL(8, 4),      -- 實際漲跌幅
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (stock_id, date)
);

-- Table: sim_account (Simulation Account)
CREATE TABLE IF NOT EXISTS sim_account (
    user_id VARCHAR(50) PRIMARY KEY,
    cash_balance DECIMAL(16, 4) DEFAULT 1000000,
    total_asset DECIMAL(16, 4) DEFAULT 1000000,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: sim_orders (Simulation Orders)
CREATE TABLE IF NOT EXISTS sim_orders (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) DEFAULT 'default_user',
    date DATE,
    stock_id VARCHAR(20) REFERENCES dim_stock(stock_id),
    action VARCHAR(10), -- 'BUY' or 'SELL'
    order_price DECIMAL(16, 4),
    shares INT,
    status VARCHAR(20) DEFAULT 'PENDING', -- 'PENDING', 'FILLED', 'CANCELLED'
    fee DECIMAL(16, 4) DEFAULT 0,
    tax DECIMAL(16, 4) DEFAULT 0,
    total_amount DECIMAL(16, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: sim_inventory (Simulation Inventory)
CREATE TABLE IF NOT EXISTS sim_inventory (
    user_id VARCHAR(50),
    stock_id VARCHAR(20) REFERENCES dim_stock(stock_id),
    shares INT,
    avg_cost DECIMAL(16, 4),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, stock_id)
);

-- Table: sim_transactions (Simulation Transaction History)
CREATE TABLE IF NOT EXISTS sim_transactions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) DEFAULT 'default_user',
    trade_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stock_id VARCHAR(20) REFERENCES dim_stock(stock_id),
    action VARCHAR(10), -- 'BUY' or 'SELL'
    price DECIMAL(16, 4),
    shares INT,
    fee DECIMAL(16, 4),
    tax DECIMAL(16, 4),
    total_amount DECIMAL(16, 4)
);

-- Table: sim_daily_assets (Simulation Daily Asset Snapshots)
CREATE TABLE IF NOT EXISTS sim_daily_assets (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) DEFAULT 'default_user',
    date DATE,
    cash_balance DECIMAL(16, 4),
    stock_value DECIMAL(16, 4),
    total_assets DECIMAL(16, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, date)
);

-- Table: strategy_config (AI Strategy Configuration)
CREATE TABLE IF NOT EXISTS strategy_config (
    user_id VARCHAR(50) PRIMARY KEY DEFAULT 'default_user',
    max_position_size DECIMAL(16, 4) DEFAULT 100000,
    stop_loss_pct DECIMAL(16, 4) DEFAULT 0.05,
    take_profit_pct DECIMAL(16, 4) DEFAULT 0.10,
    strategy_mode VARCHAR(20) DEFAULT 'CONSERVATIVE',
    ai_confidence_threshold DECIMAL(16, 4) DEFAULT 0.7,
    active_strategy VARCHAR(50) DEFAULT 'MA_CROSS',
    risk_preference VARCHAR(20) DEFAULT 'NEUTRAL',
    safe_asset_id VARCHAR(20) DEFAULT '00679B.TW',
    param_1 INTEGER DEFAULT 5,
    param_2 INTEGER DEFAULT 20,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Initial Data
INSERT INTO sim_account (user_id, cash_balance, total_asset)
VALUES ('default_user', 1000000, 1000000)
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO strategy_config (user_id) VALUES ('default_user')
ON CONFLICT (user_id) DO NOTHING;

-- Table: sim_daily_stats (Daily Performance Metrics)
CREATE TABLE IF NOT EXISTS sim_daily_stats (
    date DATE PRIMARY KEY,
    total_predictions INTEGER DEFAULT 0,
    correct_predictions INTEGER DEFAULT 0,
    win_rate DECIMAL(5, 4) DEFAULT 0,
    avg_return DECIMAL(8, 4) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for performance
CREATE INDEX IF NOT EXISTS idx_fact_price_date ON fact_price(date);
CREATE INDEX IF NOT EXISTS idx_ai_analysis_date ON ai_analysis(date);
CREATE INDEX IF NOT EXISTS idx_sim_daily_stats_date ON sim_daily_stats(date);
