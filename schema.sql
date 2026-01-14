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

-- Index for performance
CREATE INDEX IF NOT EXISTS idx_fact_price_date ON fact_price(date);
