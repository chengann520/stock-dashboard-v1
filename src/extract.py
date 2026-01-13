import yfinance as yf
import pandas as pd
import logging
from datetime import datetime

# 設定日誌 (這是專業專案必備的，不要只用 print)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def fetch_stock_data(stock_id: str, period: str = "1mo") -> pd.DataFrame:
    """
    從 Yahoo Finance 抓取指定股票的最新日資料。
    
    Args:
        stock_id (str): 股票代號 (e.g., "2330.TW", "TSLA")
        period (str): 抓取區間 (e.g., '1d', '5d', '1mo', '1y', 'max')
        
    Returns:
        pd.DataFrame: 包含 OHLCV 數據的 DataFrame，若失敗則回傳空的 DataFrame
    """
    logging.info(f"🚀 開始抓取 {stock_id}，區間: {period}...")
    
    try:
        # 1. 使用 yfinance 抓取
        ticker = yf.Ticker(stock_id)
        df = ticker.history(period=period)
        
        if df.empty:
            logging.warning(f"⚠️ 找不到 {stock_id} 的資料，可能是休市或代號錯誤。")
            return pd.DataFrame()

        # 2. 資料清洗 (Data Cleaning)
        # reset_index 以便把 Date 變成一個正常的欄位
        df = df.reset_index()
        
        # 3. 欄位標準化：將欄位名稱改成全小寫，符合資料庫 SQL 習慣
        # yfinance 給的是: Date, Open, High, Low, Close, Volume
        df.columns = [c.lower() for c in df.columns]
        
        # 4. 加上 stock_id 欄位 (資料庫需要知道這是哪支股票)
        df['stock_id'] = stock_id
        
        # 5. 確保日期格式是乾淨的字串 (YYYY-MM-DD)
        df['date'] = df['date'].dt.date
        
        # 選取我們需要的欄位
        target_columns = ['stock_id', 'date', 'open', 'high', 'low', 'close', 'volume']
        # 檢查是否所有欄位都存在 (有些股票可能沒有 volume)
        final_df = df[[c for c in target_columns if c in df.columns]]
        
        logging.info(f"✅ 成功抓取 {stock_id}，日期: {final_df.iloc[0]['date']}")
        return final_df

    except Exception as e:
        logging.error(f"❌ 抓取 {stock_id} 時發生嚴重錯誤: {e}")
        return pd.DataFrame()

# --- 簡單的自我測試區塊 (當這個檔案被單獨執行時會跑) ---
if __name__ == "__main__":
    # 測試抓台積電
    data = fetch_stock_data("2330.TW")
    print("\n--- 測試結果 ---")
    print(data)
