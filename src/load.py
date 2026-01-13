import os
import pandas as pd
from sqlalchemy import create_engine, text
import logging

# 設定日誌
logging.basicConfig(level=logging.INFO)

def get_db_connection():
    """建立資料庫連線"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("❌ DATABASE_URL 未設定")
    return create_engine(db_url)

def load_stock_data(df: pd.DataFrame):
    """
    將股價資料存入資料庫 (支援 Upsert)。
    """
    if df.empty:
        logging.warning("⚠️ 傳入的 DataFrame 是空的，跳過寫入。")
        return

    engine = get_db_connection()
    
    try:
        with engine.begin() as conn:
            for _, row in df.iterrows():
                # 1. 確保 dim_stock 裡有這支股票 (如果沒有就先建立)
                # 這叫 "Reference Integrity" (參照完整性)
                stock_id = row['stock_id']
                conn.execute(text("""
                    INSERT INTO dim_stock (stock_id) 
                    VALUES (:stock_id)
                    ON CONFLICT (stock_id) DO NOTHING;
                """), {"stock_id": stock_id})

                # 2. 寫入股價 (Upsert: 如果重複就更新 close 和 volume)
                sql = text("""
                    INSERT INTO fact_price (stock_id, date, open, high, low, close, volume)
                    VALUES (:stock_id, :date, :open, :high, :low, :close, :volume)
                    ON CONFLICT (stock_id, date) 
                    DO UPDATE SET 
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low;
                """)
                
                conn.execute(sql, {
                    "stock_id": row['stock_id'],
                    "date": row['date'],
                    "open": row['open'],
                    "high": row['high'],
                    "low": row['low'],
                    "close": row['close'],
                    "volume": row['volume']
                })
            
            logging.info(f"✅ 成功寫入 {len(df)} 筆資料到資料庫。")

    except Exception as e:
        logging.error(f"❌ 寫入資料庫失敗: {e}")
        raise e
