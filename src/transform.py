import pandas as pd
import logging

def process_data(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    資料清洗與技術指標計算 (Transform Layer)
    """
    try:
        if df.empty:
            return pd.DataFrame()

        # Debug: 印出目前有的欄位，方便除錯
        # logging.info(f"轉換前欄位檢查: {df.columns.tolist()}")

        # 1. 確保資料按日期排序
        df = df.sort_values('date').copy()

        # 2. 關鍵修正：確保欄位名稱正確
        # 如果 extract.py 沒有轉成小寫，這裡做個防呆
        df.columns = [c.lower() for c in df.columns]

        # 檢查是否有 'close' 欄位 (之前報錯是因為找不到 close_price)
        if 'close' not in df.columns:
            logging.error(f"❌ 找不到 'close' 欄位！目前的欄位是: {df.columns.tolist()}")
            return pd.DataFrame()

        # 3. 計算移動平均線 (使用 'close')
        df['ma_5'] = df['close'].rolling(window=5).mean()
        df['ma_20'] = df['close'].rolling(window=20).mean()

        # 4. 處理 NaN (補 0)
        df['ma_5'] = df['ma_5'].fillna(0)
        df['ma_20'] = df['ma_20'].fillna(0)

        logging.info(f"✅ {symbol} 資料轉換完成，新增 MA5, MA20")
        return df

    except Exception as e:
        logging.error(f"❌ Transform 階段失敗: {e}")
        # 印出更多資訊以供除錯
        logging.error(f"錯誤發生時的 DataFrame 欄位: {df.columns.tolist()}")
        return pd.DataFrame()
