-- Database Schema for Market Pulse ETL

-- Table: dim_stock (Dimension Table for Stocks)
CREATE TABLE IF NOT EXISTS dim_stock (
    stock_id VARCHAR(20) PRIMARY KEY,
    stock_name VARCHAR(100),
    exchange VARCHAR(50),
    category VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: fact_price (Fact Table for Daily Stock Prices)
CREATE TABLE IF NOT EXISTS fact_price (
    stock_id VARCHAR(20) REFERENCES dim_stock(stock_id),
    date DATE,
    open_price DECIMAL(16, 4),
    high_price DECIMAL(16, 4),
    low_price DECIMAL(16, 4),
    close_price DECIMAL(16, 4),
    volume BIGINT,
    adj_close DECIMAL(16, 4),
    ma5 DECIMAL(16, 4),
    ma20 DECIMAL(16, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Composite primary key to prevent duplicate entries for the same stock and date
    PRIMARY KEY (stock_id, date)
);

-- Index for performance
CREATE INDEX IF NOT EXISTS idx_fact_price_date ON fact_price(date);
