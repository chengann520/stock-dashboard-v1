# Entry point for Market Pulse ETL
import logging
from src.extract import fetch_stock_data
from src.transform import process_data
from src.load import save_to_db

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_pipeline(symbol: str):
    logger.info(f"--- Starting ETL for {symbol} ---")
    
    # 1. Extract
    raw_df = fetch_stock_data(symbol)
    if raw_df.empty:
        logger.error(f"Failed to fetch data for {symbol}, stopping.")
        return

    # 2. Transform
    processed_df = process_data(raw_df, symbol)
    if processed_df.empty:
        logger.error(f"Failed to transform data for {symbol}, stopping.")
        return

    # 3. Load
    success = save_to_db(processed_df)
    if success:
        logger.info(f"ETL completed successfully for {symbol}")
    else:
        logger.error(f"ETL failed during load stage for {symbol}")

def main():
    # Example stock list - this could be moved to config or database later
    stocks = ["2330.TW", "2317.TW", "TSLA", "AAPL"]
    
    for stock in stocks:
        run_pipeline(stock)

if __name__ == "__main__":
    main()
