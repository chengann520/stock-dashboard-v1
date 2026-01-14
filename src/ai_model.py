import os
import pandas as pd
import numpy as np
import pandas_ta as ta
from sqlalchemy import create_engine, text
from xgboost import XGBClassifier
import logging
from dotenv import load_dotenv

# 載入環境變數 (本地測試用)
load_dotenv()

# 設定 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def fetch_data(stock_id, engine):
    """從資料庫讀取該股票的歷史數據"""
    query = text("""
        SELECT date, open, high, low, close, volume, foreign_net, trust_net 
        FROM fact_price 
        WHERE stock_id = :stock_id 
        ORDER BY date ASC
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"stock_id": stock_id})
    return df

def train_and_predict(stock_id):
    """訓練 AI 並預測明天的走勢"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logging.error("❌ DATABASE_URL 未設定")
        return

    engine = create_engine(db_url)
    
    # 1. 抓取數據
    df = fetch_data(stock_id, engine)
    if len(df) < 60: # 資料太少不訓練
        logging.warning(f"⚠️ {stock_id} 資料不足 (目前僅 {len(df)} 筆)，跳過 AI 訓練")
        return

    # 2. 特徵工程 (Feature Engineering)
    # 技術面
    df['RSI'] = ta.rsi(df['close'], length=14)
    macd_res = ta.macd(df['close'])
    # 適應不同版本的 pandas_ta 欄位名稱
    macd_col = 'MACD_12_26_9' if 'MACD_12_26_9' in macd_res.columns else macd_res.columns[0]
    df['MACD'] = macd_res[macd_col]
    
    # 籌碼面 (簡化版)
    df['Trust_Buy'] = np.where(df['trust_net'] > 0, 1, 0)
    
    # 滯後特徵 (讓 AI 看到過去 3 天的變化)
    for lag in [1, 2, 3]:
        df[f'Pct_Change_{lag}'] = df['close'].pct_change(lag)
    
    # 清除空值
    df.dropna(inplace=True)

    if df.empty:
        logging.warning(f"⚠️ {stock_id} 經過特徵工程後無有效數據")
        return

    # 3. 準備訓練資料
    # 目標: 預測「明天」收盤價是否 > 「今天」收盤價
    df['Target'] = np.where(df['close'].shift(-1) > df['close'], 1, 0)
    
    # 用來訓練的欄位
    features = ['RSI', 'MACD', 'Trust_Buy', 'Pct_Change_1', 'Pct_Change_2', 'Pct_Change_3']
    
    # 切分訓練集 (拿最新的那一筆當作「今天要預測明天」的題目)
    # 我們用過去的所有資料來訓練模型
    X = df[features][:-1]      # 排除最後一筆 (因為最後一筆沒有 Target)
    y = df['Target'][:-1]
    
    # 要預測的當下數據 (最新的那一筆)
    latest_data = df[features].iloc[[-1]]
    current_date = df['date'].iloc[-1]

    # 4. 訓練 XGBoost 模型
    model = XGBClassifier(n_estimators=100, learning_rate=0.05, max_depth=3, eval_metric='logloss')
    model.fit(X, y)
    
    # 5. 進行預測
    prediction = model.predict(latest_data)[0]       # 0 或 1
    proba = model.predict_proba(latest_data)[0][1]   # 看漲的機率 (0.0 ~ 1.0)
    
    signal = "Bull" if prediction == 1 else "Bear"
    
    logging.info(f"🤖 {stock_id} AI 預測: {signal} (看漲機率: {proba:.2f})")

    # 6. 存入資料庫
    save_prediction(engine, stock_id, current_date, signal, proba)

def save_prediction(engine, stock_id, date, signal, proba):
    """將預測結果寫入 ai_analysis 表"""
    try:
        with engine.begin() as conn:
            # 確保 ai_analysis 表格存在 (防呆)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_analysis (
                    stock_id VARCHAR(20),
                    date DATE,
                    signal VARCHAR(10),
                    probability DECIMAL(5, 4),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (stock_id, date)
                );
            """))
            
            sql = text("""
                INSERT INTO ai_analysis (stock_id, date, signal, probability)
                VALUES (:stock_id, :date, :signal, :proba)
                ON CONFLICT (stock_id, date) 
                DO UPDATE SET signal = :signal, probability = :proba, created_at = CURRENT_TIMESTAMP;
            """)
            conn.execute(sql, {
                "stock_id": stock_id,
                "date": date,
                "signal": signal,
                "proba": float(proba)
            })
    except Exception as e:
        logging.error(f"❌ 寫入 AI 預測資料庫失敗: {e}")

if __name__ == "__main__":
    # 本地測試用
    train_and_predict("2330.TW")
