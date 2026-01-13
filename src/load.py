import os
import pandas as pd
from sqlalchemy import create_engine, text
import logging

def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL 未設定")
    return create_engine(db_url)

def save_to_db(df: pd.DataFrame) -> bool:
    """
    將資料寫入資料庫 (與 main.py 的呼叫名稱一致)
    """
    if df.empty:
        logging.warning("沒有資料需要寫入")
        return False

    try:
        engine = get_db_connection()
        with engine.begin() as conn:
            for _, row in df.iterrows():
                # 1. 確保 dim_stock 有資料
                conn.execute(text("""
                    INSERT INTO dim_stock (stock_id) VALUES (:stock_id)
                    ON CONFLICT (stock_id) DO NOTHING;
                """), {"stock_id": row['stock_id']})

                # 2. Upsert 寫入股價
                conn.execute(text("""
                    INSERT INTO fact_price (stock_id, date, open, high, low, close, volume)
                    VALUES (:stock_id, :date, :open, :high, :low, :close, :volume)
                    ON CONFLICT (stock_id, date) 
                    DO UPDATE SET 
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low;
                """), {
                    "stock_id": row['stock_id'],
                    "date": row['date'],
                    "open": row['open'],
                    "high": row['high'],
                    "low": row['low'],
                    "close": row['close'],
                    "volume": row['volume']
                })
        
        logging.info("✅ 資料庫寫入成功")
        return True

    except Exception as e:
        logging.error(f"❌ 資料庫寫入失敗: {e}")
        return False
