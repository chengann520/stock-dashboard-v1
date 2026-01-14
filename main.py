import os
import logging
import time
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 引入你原本寫好的模組
from src.extract import extract_data
from src.transform import transform_data
from src.load import load_data

# 設定 logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_stock_list_from_db():
    """從 dim_stock 資料表讀取所有要抓的股票"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL 未設定")
        
    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT stock_id FROM dim_stock"))
        # 轉換成列表 ['2330.TW', '2317.TW'...]
        return [row[0] for row in result]

def main():
    load_dotenv()
    
    try:
        # 1. 動態取得股票清單
        symbols = get_stock_list_from_db()
        logging.info(f"🎯 本次任務目標：共 {len(symbols)} 檔股票")
        
        if not symbols:
            logging.warning("⚠️ 資料庫中沒有股票清單，請先執行 seed_stocks.py")
            return

        # 2. 逐一處理
        success_count = 0
        for symbol in symbols:
            try:
                logging.info(f"🚀 處理中: {symbol} ...")
                
                # Extract
                df = extract_data(symbol)
                if df is None or df.empty:
                    logging.warning(f"⚠️ {symbol} 抓不到資料，跳過")
                    continue
                
                # Transform
                df = transform_data(df)
                
                # Load
                load_data(df)
                
                success_count += 1
                logging.info(f"✅ {symbol} 完成")
                
                # 😴 關鍵：休息 1 秒，避免被封鎖
                time.sleep(1)
                
            except Exception as e:
                logging.error(f"❌ {symbol} 發生錯誤: {e}")
                continue # 繼續做下一支，不要停

        logging.info(f"🎉 任務結束！成功處理 {success_count}/{len(symbols)} 檔")

    except Exception as e:
        logging.error(f"💥 系統嚴重錯誤: {e}")

if __name__ == "__main__":
    main()
