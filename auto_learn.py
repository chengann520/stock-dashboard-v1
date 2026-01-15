import os
import pandas as pd
import pandas_ta as ta
from datetime import date, timedelta
from supabase import create_client
from FinMind.data import DataLoader
from tqdm import tqdm

# --- 連線設定 ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN")

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
    print(f"🏆 冠軍產生！策略 {strategy} 最佳參數: ({p1}, {p2})，近月回測 ROI: {best_roi:.2f}%")
    try:
        supabase.table('strategy_config').update({
            'param_1': int(p1),
            'param_2': int(p2),
            'updated_at': 'now()'
        }).eq('user_id', 'default_user').execute()
    except Exception as e:
        print(f"❌ 更新參數失敗: {e}")

# --- 快速回測函數 ---
def quick_backtest(df, strategy_name, p1, p2):
    """
    在歷史資料上跑一次策略，回傳總報酬率
    """
    df = df.copy()
    capital = 100000
    position = 0
    balance = capital
    
    try:
        # 計算指標
        if strategy_name == 'MA_CROSS':
            df['S'] = ta.sma(df['close'], length=p1)
            df['L'] = ta.sma(df['close'], length=p2)
            df['Signal'] = 0
            df.loc[(df['S'] > df['L']) & (df['S'].shift(1) <= df['L'].shift(1)), 'Signal'] = 1
            df.loc[(df['S'] < df['L']) & (df['S'].shift(1) >= df['L'].shift(1)), 'Signal'] = -1

        elif strategy_name == 'RSI_REVERSAL':
            df['RSI'] = ta.rsi(df['close'], length=p1)
            threshold = p2
            df['Signal'] = 0
            df.loc[(df['RSI'] < threshold) & (df['RSI'] > df['RSI'].shift(1)), 'Signal'] = 1
            df.loc[df['RSI'] > 70, 'Signal'] = -1
            
        elif strategy_name == 'KD_CROSS':
            kdf = ta.stoch(df['high'], df['low'], df['close'], k=p1, d=3, smooth_k=3)
            k_col, d_col = f"STOCHk_{p1}_3_3", f"STOCHd_{p1}_3_3"
            df['Signal'] = 0
            df.loc[(kdf[k_col] > kdf[d_col]) & (kdf[k_col].shift(1) <= kdf[d_col].shift(1)) & (kdf[k_col] < p2), 'Signal'] = 1
            df.loc[(kdf[k_col] < kdf[d_col]) & (kdf[k_col].shift(1) >= kdf[d_col].shift(1)) & (kdf[k_col] > 80), 'Signal'] = -1

        elif strategy_name == 'MACD_CROSS':
            macdf = ta.macd(df['close'], fast=p1, slow=p2, signal=9)
            hist_col = f"MACDh_{p1}_{p2}_9"
            df['Signal'] = 0
            df.loc[(macdf[hist_col] > 0) & (macdf[hist_col].shift(1) <= 0), 'Signal'] = 1
            df.loc[(macdf[hist_col] < 0) & (macdf[hist_col].shift(1) >= 0), 'Signal'] = -1

        # 簡單模擬交易
        for i in range(1, len(df)):
            price = df.iloc[i]['close']
            sig = df.iloc[i]['Signal']
            
            if sig == 1 and position == 0: # 買
                position = balance / price
                balance = 0
            elif sig == -1 and position > 0: # 賣
                balance = position * price
                position = 0
        
        # 結算最終價值
        final_val = balance + (position * df.iloc[-1]['close'])
        return (final_val - capital) / capital * 100

    except Exception as e:
        return -999 # 參數無效

def run_learning():
    print("🧠 AI 開始自我學習 (參數最佳化)...")
    
    # 1. 讀取目前使用的策略
    config = get_current_config()
    strategy = config.get('active_strategy', 'MA_CROSS')
    print(f"📚 正在優化策略: {strategy}")
    
    # 2. 準備訓練數據
    api = DataLoader()
    if FINMIND_TOKEN:
        api.login_by_token(api_token=FINMIND_TOKEN)
    
    # 使用 0050.TW 作為基準
    start_date = (date.today() - timedelta(days=60)).strftime('%Y-%m-%d')
    try:
        df = api.taiwan_stock_daily(stock_id='0050.TW', start_date=start_date, end_date=str(date.today()))
    except Exception as e:
        print(f"❌ 無法取得訓練數據: {e}")
        return
    
    if df.empty:
        print("❌ 無法取得訓練數據")
        return

    # 3. 定義搜索空間
    best_roi = -999
    best_p1 = config.get('param_1', 5)
    best_p2 = config.get('param_2', 20)
    
    combinations = []
    
    if strategy == 'MA_CROSS':
        for s in range(3, 11, 2):
            for l in range(10, 61, 10):
                if s < l: combinations.append((s, l))
                
    elif strategy == 'RSI_REVERSAL':
        for t in range(6, 15, 2):
            for th in range(20, 46, 5):
                combinations.append((t, th))
                
    elif strategy == 'KD_CROSS':
        for k in range(5, 15, 2):
            for th in range(15, 31, 5):
                combinations.append((k, th))

    elif strategy == 'MACD_CROSS':
        for f in range(8, 17, 2):
            for s in range(20, 41, 5):
                if f < s: combinations.append((f, s))

    # 4. 開始訓練 (Grid Search)
    print(f"🧪 準備測試 {len(combinations)} 種參數組合...")
    
    for p1, p2 in tqdm(combinations):
        roi = quick_backtest(df, strategy, p1, p2)
        
        if roi > best_roi:
            best_roi = roi
            best_p1 = p1
            best_p2 = p2
    
    # 5. 更新大腦
    if best_roi > 0:
        update_params(strategy, best_p1, best_p2, best_roi)
    else:
        print("📉 近期市場太差，所有參數都賠錢，維持原設定。")

if __name__ == "__main__":
    run_learning()
