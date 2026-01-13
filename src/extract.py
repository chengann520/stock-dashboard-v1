import yfinance as yf
import pandas as pd
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fetch_stock_data(symbol: str, period: str = "1y") -> pd.DataFrame:
    """
    Fetch stock data from yfinance.
    
    Args:
        symbol: Stock ticker (e.g., '2330.TW', 'TSLA').
        period: Time period (e.g., '1y', 'max').
        
    Returns:
        pd.DataFrame: Fetched stock data or empty DataFrame on failure.
    """
    try:
        logger.info(f"Fetching data for {symbol} with period {period}...")
        stock = yf.Ticker(symbol)
        df: pd.DataFrame = stock.history(period=period)
        
        if df.empty:
            logger.warning(f"No data found for {symbol}.")
            return pd.DataFrame()
            
        return df
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {str(e)}")
        return pd.DataFrame()
