import os
import pandas as pd
import pandas_ta as ta
from datetime import date, timedelta
from supabase import create_client
from tqdm import tqdm
import yfinance as yf

# --- 連線設定 ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ 錯誤: 未設定 SUPABASE_URL 或 SUPABASE_KEY")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_current_config():
    """從資料庫讀取目前的 AI 大腦設定"""
    try:
        data = supabase.table('strategy_config').select('*').eq('user_id', 'default_user').execute().data
        return data[0] if data else {}
    except Exception as e:
        print(f"⚠️ 讀取設定失敗: {e}")
        return {}

def update_params(strategy, p1, p2, best_roi):
    """將最佳參數寫入資料庫"""
    print(f"🏆 冠軍產生！策略 {strategy} 最佳參數: ({p1}, {p2})，ROI: {best_roi:.2f}%")
    try:
        supabase.table('strategy_config').update({
            'param_1': int(p1),
            'param_2': int(p2),
            'updated_at': 'now()'
        }).eq('user_id', 'default_user').execute()
    except Exception as e:
        print(f"❌ 更新參數失敗: {e}")

# --- 強化版資料抓取函數 ---
def fetch_training_data(stock_id='0050.TW', days=120):
    """
    嘗試從 Supabase 抓取，失敗則自動切換到 yfinance
    """
    start_date = (date.today() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    # 1. 優先嘗試 Supabase (fact_price)
    try:
        print(f"📥 嘗試從 Supabase 讀取 {stock_id} 歷史資料...")
        res = supabase.table('fact_price').select('*').eq('stock_id', stock_id).gte('date', start_date).order('date').execute()
        df = pd.DataFrame(res.data)
        
        if not df.empty:
            print(f"✅ Supabase 資料讀取成功 ({len(df)} 筆)")
            return df
        else:
            print("⚠️ Supabase 無資料，切換備用方案...")
    except Exception as e:
        print(f"⚠️ Supabase 讀取錯誤: {e}")

    # 2. 備用方案：Yahoo Finance (yfinance)
    try:
        print(f"🌍 切換至 Yahoo Finance 下載 {stock_id}...")
        end_date = date.today().strftime('%Y-%m-%d')
        df = yf.download(stock_id, start=start_date, end=end_date, progress=False)
        
        if not df.empty:
            df = df.reset_index()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            # 確保欄位名稱對齊 (Open, High, Low, Close)
            df = df.rename(columns={'Date': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
            # 確保 Close 欄位存在
            if 'close' not in df.columns and 'Close' in df.columns:
                df['close'] = df['Close']
            
            print("✅ Yahoo Finance 資料下載成功")
            return df
    except Exception as e:
        print(f"❌ Yahoo Finance 也失敗: {e}")

    return pd.DataFrame()

def quick_backtest(df, strategy_name, p1, p2):
    """快速回測邏輯"""
    df = df.copy()
    # 確保 Close 是數值
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    
    try:
        if strategy_name == 'MA_CROSS':
            df['S'] = ta.sma(df['close'], length=p1)
            df['L'] = ta.sma(df['close'], length=p2)
            df['Signal'] = 0
            cond_buy = (df['S'].shift(1) < df['L'].shift(1)) & (df['S'] > df['L'])
            cond_sell = (df['S'].shift(1) > df['L'].shift(1)) & (df['S'] < df['L'])
            df.loc[cond_buy, 'Signal'] = 1
            df.loc[cond_sell, 'Signal'] = -1

        elif strategy_name == 'RSI_REVERSAL':
            df['RSI'] = ta.rsi(df['close'], length=p1)
            threshold = p2
            df['Signal'] = 0
            cond_buy = (df['RSI'].shift(1) < threshold) & (df['RSI'] > df['RSI'].shift(1))
            cond_sell = df['RSI'] > 70
            df.loc[cond_buy, 'Signal'] = 1
            df.loc[cond_sell, 'Signal'] = -1
            
        elif strategy_name == 'KD_CROSS':
            kdf = ta.stoch(df['high'], df['low'], df['close'], k=p1, d=3, smooth_k=3)
            k_col = f"STOCHk_{p1}_3_3"
            d_col = f"STOCHd_{p1}_3_3"
            df['Signal'] = 0
            cond_buy = (kdf[k_col].shift(1) < kdf[d_col].shift(1)) & (kdf[k_col] > kdf[d_col]) & (kdf[k_col] < p2)
            cond_sell = (kdf[k_col].shift(1) > kdf[d_col].shift(1)) & (kdf[k_col] < kdf[d_col])
            df.loc[cond_buy, 'Signal'] = 1
            df.loc[cond_sell, 'Signal'] = -1

        elif strategy_name == 'MACD_CROSS':
            macdf = ta.macd(df['close'], fast=p1, slow=p2, signal=9)
            hist_col = f"MACDh_{p1}_{p2}_9"
            df['Signal'] = 0
            df.loc[(macdf[hist_col] > 0) & (macdf[hist_col].shift(1) <= 0), 'Signal'] = 1
            df.loc[(macdf[hist_col] < 0) & (macdf[hist_col].shift(1) >= 0), 'Signal'] = -1

        elif strategy_name == 'N1_MOMENTUM':
            # 單標的回測邏輯：動能向上 + RSI 未過熱 + 站上 MA20
            df['MA20'] = ta.sma(df['close'], length=20)
            df['RSI'] = ta.rsi(df['close'], length=14)
            df['Momentum'] = df['close'].pct_change(periods=p1)
            df['Signal'] = 0
            # 買入條件：動能 > 0 且 RSI < p2 且 價格 > MA20
            cond_buy = (df['Momentum'] > 0) & (df['RSI'] < p2) & (df['close'] > df['MA20'])
            # 賣出條件：RSI > p2 或 價格 < MA20
            cond_sell = (df['RSI'] >= p2) | (df['close'] < df['MA20'])
            df.loc[cond_buy, 'Signal'] = 1
            df.loc[cond_sell, 'Signal'] = -1

        elif strategy_name == 'BEST_OF_3':
            # 單標的回測邏輯：跌深 (Drawdown) + 長線保護 (MA p2)
            df['MA_L'] = ta.sma(df['close'], length=p2)
            df['Recent_High'] = df['high'].rolling(window=p1).max()
            df['Drawdown'] = (df['close'] - df['Recent_High']) / df['Recent_High']
            df['Signal'] = 0
            # 買入條件：跌幅超過 5% (模擬跌深) 且 價格 > MA_L
            cond_buy = (df['Drawdown'] < -0.05) & (df['close'] > df['MA_L'])
            # 賣出條件：價格回升或跌破 MA_L
            cond_sell = (df['Drawdown'] > -0.01) | (df['close'] < df['MA_L'])
            df.loc[cond_buy, 'Signal'] = 1
            df.loc[cond_sell, 'Signal'] = -1

        # 計算損益
        capital = 100000
        balance = capital
        position = 0
        
        for i in range(len(df)):
            price = df.iloc[i]['close']
            sig = df.iloc[i]['Signal']
            
            if sig == 1 and position == 0: # 買
                position = balance / price
                balance = 0
            elif sig == -1 and position > 0: # 賣
                balance = position * price
                position = 0
                
        final_val = balance + (position * df.iloc[-1]['close'])
        return (final_val - capital) / capital * 100
        
    except Exception as e:
        return -999

def run_learning():
    print("🧠 AI 開始自我學習 (參數最佳化)...")
    config = get_current_config()
    strategy = config.get('active_strategy', 'MA_CROSS')
    
    # 1. 取得訓練數據 (改用強化版函數)
    df = fetch_training_data('0050.TW', days=120)
    
    if df.empty:
        print("❌ 無法取得訓練數據 (Supabase & Yahoo 都失敗)，請檢查網路或代號")
        return

    # 2. 定義參數範圍
    print(f"📚 正在為 {strategy} 尋找最佳參數...")
    combinations = []
    
    if strategy == 'MA_CROSS':
        for s in range(3, 15, 2):
            for l in range(10, 60, 5):
                if s < l: combinations.append((s, l))
                
    elif strategy == 'RSI_REVERSAL':
        for t in range(5, 15, 1):
            for th in range(20, 50, 5):
                combinations.append((t, th))

    elif strategy == 'KD_CROSS':
        for t in range(5, 15, 1):
            for th in range(15, 40, 5):
                combinations.append((t, th))

    elif strategy == 'MACD_CROSS':
        for f in range(8, 17, 2):
            for s in range(20, 41, 5):
                if f < s: combinations.append((f, s))

    elif strategy == 'N1_MOMENTUM':
        # p1: 動能週期 (20~120), p2: RSI 門檻 (70~90)
        for p1 in range(20, 121, 20):
            for p2 in range(70, 91, 5):
                combinations.append((p1, p2))

    elif strategy == 'BEST_OF_3':
        # p1: 回撤觀察期 (10~60), p2: MA 天數 (100~250)
        for p1 in range(10, 61, 10):
            for p2 in range(100, 251, 50):
                combinations.append((p1, p2))
    
    else:
        print("⚠️ 未知的策略，跳過訓練")
        return

    # 3. 訓練
    best_roi = -999
    best_p1, best_p2 = config.get('param_1', 5), config.get('param_2', 20)
    
    for p1, p2 in tqdm(combinations): 
        roi = quick_backtest(df, strategy, p1, p2)
        if roi > best_roi:
            best_roi = roi
            best_p1 = p1
            best_p2 = p2
            
    # 4. 更新
    if best_roi > -10:
        update_params(strategy, best_p1, best_p2, best_roi)
    else:
        print(f"📉 最佳 ROI ({best_roi:.2f}%) 太低，不更新參數")

if __name__ == "__main__":
    run_learning()
