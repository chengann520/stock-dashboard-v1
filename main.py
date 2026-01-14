import os
import logging
import time
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 引入你的模組 (假設檔案結構沒變)
from src.extract import extract_data
from src.transform import transform_data
from src.load import load_data
from src.ai_model import train_and_predict

# 設定 logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_stock_list_from_db():
    """
    從 dim_stock 資料表取得所有股票代碼
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logging.error("❌ DATABASE_URL 未設定")
        return []
        
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            # 只要抓 stock_id 就好
            result = conn.execute(text("SELECT stock_id FROM dim_stock"))
            # 將結果轉換成一個 list，例如 ['2330.TW', '0050.TW', ...]
            stock_list = [row[0] for row in result]
            return stock_list
    except Exception as e:
        logging.error(f"❌ 無法從資料庫讀取股票清單: {e}")
        return []

def main():
    load_dotenv()
    
    logging.info("🚀 ETL 程式啟動...")

    # 1. 改成從資料庫動態取得清單
    symbols = get_stock_list_from_db()
    
    if not symbols:
        logging.warning("⚠️ 警告：資料庫回傳的股票清單是空的！(請確認 dim_stock 有資料)")
        # 如果資料庫沒資料，這裡可以放一個保險的預設名單，或直接結束
        return

    logging.info(f"🎯 本次任務目標：共 {len(symbols)} 檔股票")

    # 2. 開始逐一處理
    success_count = 0
    for i, symbol in enumerate(symbols, 1):
        try:
            logging.info(f"[{i}/{len(symbols)}] 正在處理: {symbol} ...")
            
            # Extract
            df = extract_data(symbol)
            if df is None or df.empty:
                logging.warning(f"⚠️ {symbol} 抓不到資料 (可能是下市或代碼錯誤)，跳過")
                continue
            
            # Transform
            df = transform_data(df)
            
            # Load
            load_data(df)
            
            # 🤖 AI Analysis
            logging.info(f"🤖 啟動 AI 分析: {symbol} ...")
            train_and_predict(symbol)
            
            success_count += 1
            logging.info(f"✅ {symbol} 處理完成 (ETL + AI)")
            
            # 😴 關鍵：每一支股票抓完休息 1~2 秒，避免被 Yahoo Finance 封鎖 IP
            time.sleep(1.5)
            
        except Exception as e:
            logging.error(f"❌ {symbol} 處理失敗: {e}")
            continue # 失敗就換下一支，不要讓整個程式停掉

    logging.info(f"🎉 所有任務結束！成功處理 {success_count}/{len(symbols)} 檔")

if __name__ == "__main__":
    main()
