import logging
import sys
from src.extract import fetch_stock_data
from src.transform import process_data
from src.load import load_data
from dotenv import load_dotenv
import os

# 0. 載入環境變數 (本地測試用)
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

WATCHLIST = ['2330.TW', '0050.TW', 'TSLA', 'AAPL']

def main():
    # 設定策略：
    # 如果你想補歷史資料，這裡改成 "1y" 或 "max"
    # 如果是日常跑，建議用 "5d" (包含週末和例假日緩衝)
    TARGET_PERIOD = "1mo" 
    
    logging.info(f"🎯 本次任務設定：抓取過去 {TARGET_PERIOD} 的資料")

    for symbol in WATCHLIST:
        try:
            # 1. Extract (帶入參數)
            raw_df = fetch_stock_data(symbol, period=TARGET_PERIOD)
            
            if raw_df.empty:
                logging.warning(f"⚠️ {symbol} 抓不到資料 (可能休市)，跳過。")
                continue

            # 2. Transform
            processed_df = process_data(raw_df, symbol)
            
            # 3. Load
            save_to_db(processed_df)
            
        except Exception as e:
            logging.error(f"❌ 處理 {symbol} 時發生未預期錯誤: {e}")

if __name__ == "__main__":
    main()
