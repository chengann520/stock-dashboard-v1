import os
import requests
import pandas as pd
import numpy as np
import pandas_ta as ta
from sqlalchemy import create_engine, text
from xgboost import XGBClassifier
import logging
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 通知函式 ---
def send_line_message(msg):
    token = os.getenv("LINE_CHANNEL_TOKEN")
    user_id = os.getenv("LINE_USER_ID")
    if not token or not user_id: return
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": user_id, "messages": [{"type": "text", "text": msg}]}
    try:
        requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
        logging.info("📤 LINE 通知已發送")
    except Exception as e: 
        logging.warning(f"⚠️ LINE 通知發送失敗: {e}")

# --- 主程式 ---
def fetch_data(stock_id, engine):
    query = text("""
        SELECT date, open, high, low, close, volume, foreign_net, trust_net 
        FROM fact_price WHERE stock_id = :stock_id ORDER BY date ASC
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"stock_id": stock_id})
    return df

def train_and_predict(stock_id):
    db_url = os.getenv("DATABASE_URL")
    if not db_url: 
        logging.error("❌ DATABASE_URL 未設定")
        return
    engine = create_engine(db_url)
    
    # 1. 抓取數據
    df = fetch_data(stock_id, engine)
    if len(df) < 60: 
        logging.warning(f"⚠️ {stock_id} 資料不足，跳過 AI 訓練")
        return

    # 2. 特徵工程 (加入 ATR)
    df['RSI'] = ta.rsi(df['close'], length=14)
    macd_res = ta.macd(df['close'])
    macd_col = 'MACD_12_26_9' if 'MACD_12_26_9' in macd_res.columns else macd_res.columns[0]
    df['MACD'] = macd_res[macd_col]
    
    # 🟢 新增：ATR (計算波動率)
    df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    df['Trust_Buy'] = np.where(df['trust_net'] > 0, 1, 0)
    for lag in [1, 2, 3]:
        df[f'Pct_Change_{lag}'] = df['close'].pct_change(lag)
    df.dropna(inplace=True)

    if df.empty: return

    # 3. 訓練模型
    df['Target'] = np.where(df['close'].shift(-1) > df['close'], 1, 0)
    features = ['RSI', 'MACD', 'Trust_Buy', 'Pct_Change_1', 'Pct_Change_2', 'Pct_Change_3']
    
    X = df[features][:-1]
    y = df['Target'][:-1]
    latest_data = df[features].iloc[[-1]]
    
    # 取得最新價格數據 (用來算策略)
    last_close = float(df['close'].iloc[-1])
    # 處理 ATR 可能為 NaN 的情況
    last_atr = float(df['ATR'].iloc[-1]) if pd.notnull(df['ATR'].iloc[-1]) else last_close * 0.02
    current_date = df['date'].iloc[-1]

    model = XGBClassifier(n_estimators=100, learning_rate=0.05, max_depth=3, eval_metric='logloss')
    model.fit(X, y)
    
    prediction = model.predict(latest_data)[0]
    proba = float(model.predict_proba(latest_data)[0][1])
    signal = "Bull" if prediction == 1 else "Bear"
    
    # 🟢 4. 計算進出場價格 (策略生成)
    entry_price = 0.0
    target_price = 0.0
    stop_loss = 0.0

    if signal == "Bull":
        # 根據信心度調整策略
        if proba > 0.8: 
            # 信心高：積極進攻
            entry_price = last_close
            target_price = last_close + (2.0 * last_atr)
            stop_loss = last_close - (1.0 * last_atr)
        else:
            # 信心低：保守操作
            entry_price = last_close - (0.5 * last_atr)
            target_price = last_close + (1.0 * last_atr)
            stop_loss = last_close - (1.0 * last_atr)
            
    elif signal == "Bear":
        # 預測會跌，在支撐處等
        entry_price = last_close - (2.0 * last_atr)
        target_price = last_close
        stop_loss = entry_price * 0.95

    logging.info(f"🤖 {stock_id} 預測: {signal} ({proba:.2f}) | 建議買: {entry_price:.1f} 賣: {target_price:.1f}")

    # 5. 存入資料庫 (包含價格)
    save_prediction(engine, stock_id, current_date, signal, proba, entry_price, target_price, stop_loss)

    # 6. 發送通知 (只通知高信心的)
    if signal == "Bull" and proba >= 0.80:
        msg = (
            f"🚀 【AI 飆股訊號】\n"
            f"股票：{stock_id}\n"
            f"信心：{proba:.1%}\n"
            f"------------------\n"
            f"💰 建議買入：{entry_price:.1f}\n"
            f"🎯 目標獲利：{target_price:.1f}\n"
            f"🛑 停損價格：{stop_loss:.1f}\n"
            f"------------------\n"
            f"(基於 ATR 波動率計算)"
        )
        send_line_message(msg)

def save_prediction(engine, stock_id, date, signal, proba, entry, target, stop):
    try:
        with engine.begin() as conn:
            # 確保欄位存在 (防呆)
            sql_check = text("""
                ALTER TABLE ai_analysis ADD COLUMN IF NOT EXISTS entry_price DECIMAL(16, 4);
                ALTER TABLE ai_analysis ADD COLUMN IF NOT EXISTS target_price DECIMAL(16, 4);
                ALTER TABLE ai_analysis ADD COLUMN IF NOT EXISTS stop_loss DECIMAL(16, 4);
            """)
            conn.execute(sql_check)

            sql = text("""
                INSERT INTO ai_analysis (stock_id, date, signal, probability, entry_price, target_price, stop_loss)
                VALUES (:sid, :dt, :sig, :prob, :entry, :target, :stop)
                ON CONFLICT (stock_id, date) 
                DO UPDATE SET 
                    signal = :sig, probability = :prob, 
                    entry_price = :entry, target_price = :target, stop_loss = :stop,
                    created_at = CURRENT_TIMESTAMP;
            """)
            conn.execute(sql, {
                "sid": stock_id, "dt": date, "sig": signal, "prob": float(proba),
                "entry": float(entry), "target": float(target), "stop": float(stop)
            })
    except Exception as e:
        logging.error(f"❌ 寫入資料庫失敗: {e}")

if __name__ == "__main__":
    train_and_predict("2330.TW")
