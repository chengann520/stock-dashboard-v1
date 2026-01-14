import os
import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

def update_market_close():
    db_url = os.getenv("DATABASE_URL")
    if not db_url: 
        logging.error("❌ DATABASE_URL 未設定")
        return
    engine = create_engine(db_url)

    # 1. 抓取資料庫中「還沒驗證 (is_correct IS NULL)」的預測
    # 我們驗證的是日期小於今天的資料
    with engine.connect() as conn:
        query = text("""
            SELECT id, stock_id, date, signal, entry_price 
            FROM ai_analysis 
            WHERE is_correct IS NULL AND date < CURRENT_DATE
        """)
        predictions = pd.read_sql(query, conn)

    if predictions.empty:
        logging.info("😴 沒有需要驗證的歷史預測")
        return

    logging.info(f"📝 準備驗證 {len(predictions)} 筆歷史預測...")

    # 2. 逐一比對
    for _, row in predictions.iterrows():
        stock_id = row['stock_id']
        pred_date = row['date'] # 這是預測產生的日期
        signal = row['signal']
        db_id = row['id']
        
        try:
            # 抓取該股票「預測日期當天與隔天」的股價
            stock = yf.Ticker(stock_id)
            # 抓取較長一點的日期範圍以確保包含所需資料
            hist = stock.history(start=str(pred_date), period="5d")
            
            if len(hist) < 2:
                logging.warning(f"⚠️ {stock_id} 數據不足，暫時無法驗證")
                continue
            
            # hist 的 index 0 是預測當天，index 1 是隔天(驗證目標日)
            yesterday_close = float(hist['Close'].iloc[0])
            today_close = float(hist['Close'].iloc[1])
            
            # 計算實際漲跌
            actual_return = (today_close - yesterday_close) / yesterday_close
            
            # 判定勝負
            is_correct = False
            if signal == "Bull" and actual_return > 0:
                is_correct = True
            elif signal == "Bear" and actual_return < 0:
                is_correct = True
            
            # 3. 寫回資料庫
            with engine.begin() as conn:
                sql = text("""
                    UPDATE ai_analysis 
                    SET actual_close = :close, 
                        return_pct = :ret, 
                        is_correct = :correct
                    WHERE id = :id
                """)
                conn.execute(sql, {
                    "close": today_close,
                    "ret": float(actual_return),
                    "correct": is_correct,
                    "id": db_id
                })
                
            logging.info(f"✅ {stock_id}: 預測 {signal}, 實際漲幅 {actual_return:.2%}, 結果: {'猜對' if is_correct else '猜錯'}")

        except Exception as e:
            logging.error(f"❌ {stock_id} 驗證失敗: {e}")

if __name__ == "__main__":
    update_market_close()
