import pandas as pd
import logging

logger = logging.getLogger(__name__)

def process_data(df: pd.DataFrame, stock_id: str) -> pd.DataFrame:
    """
    Clean and transform raw stock data.
    
    Args:
        df: Raw DataFrame from yfinance.
        stock_id: Repository ID for the stock.
        
    Returns:
        pd.DataFrame: Processed DataFrame ready for database insertion.
    """
    if df.empty:
        return df

    try:
        # 1. Reset index to move 'Date' from index to column
        df = df.reset_index()

        # 2. Rename columns to match database schema
        # yfinance columns usually: Date, Open, High, Low, Close, Volume, Dividends, Stock Splits
        rename_map: dict[str, str] = {
            'Date': 'date',
            'Open': 'open_price',
            'High': 'high_price',
            'Low': 'low_price',
            'Close': 'close_price',
            'Volume': 'volume',
            'Adj Close': 'adj_close'
        }
        df = df.rename(columns=rename_map)

        # Ensure adj_close exists (history() sometimes doesn't have it if use_pep440=True or depending on version)
        if 'adj_close' not in df.columns and 'close_price' in df.columns:
            df['adj_close'] = df['close_price']

        # 3. Handle missing values (NaN)
        # Use forward fill then backward fill for any remaining holes
        df = df.ffill().bfill()

        # 4. Calculate Indicators (MA5, MA20)
        df['ma5'] = df['close_price'].rolling(window=5).mean()
        df['ma20'] = df['close_price'].rolling(window=20).mean()

        # 5. Add stock_id column
        df['stock_id'] = stock_id

        # 6. Select relevant columns
        cols: list[str] = ['stock_id', 'date', 'open_price', 'high_price', 'low_price', 'close_price', 'volume', 'adj_close', 'ma5', 'ma20']
        df = df[cols]
        
        # Ensure date is just DATE (not datetime with timezone)
        df['date'] = pd.to_datetime(df['date']).dt.date

        return df
    except Exception as e:
        logger.error(f"Error transforming data: {str(e)}")
        return pd.DataFrame()
