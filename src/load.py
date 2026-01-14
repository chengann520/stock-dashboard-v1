import os
import pandas as pd
from sqlalchemy import create_engine, text
import logging
from dotenv import load_dotenv

# 0. 載入環境變數 (本地測試用)
load_dotenv()

def load_data(df: pd.DataFrame):
    """
    將資料寫入 Supabase 資料庫 (Load Layer)
    """
    try:
        if df.empty:
            logging.warning("沒有資料需要寫入")
            return

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            logging.error("❌ DATABASE_URL 未設定")
            return

        engine = create_engine(db_url)
        
        # 建立連線並寫入
        with engine.begin() as conn:
            # 💡 這裡使用了 'upsert' 技巧：
            # 如果資料已存在 (ON CONFLICT)，則更新 (DO UPDATE) 數值
            # 1. 準備 SQL 指令 (加入了 ma_5 和 ma_20)
            sql = text("""
                INSERT INTO fact_price (stock_id, date, open, high, low, close, volume, ma_5, ma_20)
                VALUES (:stock_id, :date, :open, :high, :low, :close, :volume, :ma_5, :ma_20)
                ON CONFLICT (stock_id, date) 
                DO UPDATE SET 
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    ma_5 = EXCLUDED.ma_5,   -- 這裡關鍵！強制更新 MA
                    ma_20 = EXCLUDED.ma_20; -- 這裡關鍵！強制更新 MA
            """)

            # 2. 將 DataFrame 轉為字典列表以便寫入
            data_to_insert = df.to_dict(orient='records')
            
            # 3. 執行寫入
            conn.execute(sql, data_to_insert)
            
        logging.info(f"✅ 成功寫入/更新 {len(df)} 筆資料到資料庫")

    except Exception as e:
        logging.error(f"❌ 資料庫寫入失敗: {e}")
