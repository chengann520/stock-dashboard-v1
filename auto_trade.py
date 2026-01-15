import os
import argparse
import pandas as pd
import pandas_ta as ta
from datetime import datetime, date, timedelta
from supabase import create_client
from FinMind.data import DataLoader
import random

# --- 1. 初始化設定 ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ 錯誤: 未設定 SUPABASE_URL 或 SUPABASE_KEY")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 交易參數
FEE_RATE = 0.001425
TAX_RATE = 0.003

def calculate_cost(price, shares):
    amount = price * shares
    fee = int(amount * FEE_RATE)
    fee = max(20, fee)
    return int(amount + fee), fee

def calculate_revenue(price, shares):
    amount = price * shares
    fee = int(amount * FEE_RATE)
    fee = max(20, fee)
    tax = int(amount * TAX_RATE)
    return int(amount - fee - tax), fee, tax

# --- 2. 定義功能函數 ---

def get_strategy_config():
    """從資料庫讀取使用者設定"""
    try:
        data = supabase.table('strategy_config').select('*').eq('user_id', 'default_user').execute().data
        if data:
            return data[0]
    except Exception as e:
        print(f"⚠️ 讀取策略設定失敗，使用預設值: {e}")
    
    return {
        'max_position_size': 100000,
        'stop_loss_pct': 0.05,
        'take_profit_pct': 0.10,
        'ai_confidence_threshold': 0.7,
        'active_strategy': 'MA_CROSS',
        'risk_preference': 'NEUTRAL',
        'param_1': 5,
        'param_2': 20
    }

def check_technical_exit(stock_id, strategy_name, p1, p2):
    """
    輔助函數：檢查這支股票是否出現「賣出訊號」
    Returns: (bool 是否賣出, str 原因)
    """
    try:
        api = DataLoader()
        if FINMIND_TOKEN:
            api.login_by_token(api_token=FINMIND_TOKEN)
        
        start_date = (date.today() - timedelta(days=100)).strftime('%Y-%m-%d')
        df = api.taiwan_stock_daily(
            stock_id=stock_id,
            start_date=start_date,
            end_date=date.today().strftime('%Y-%m-%d')
        )
        
        if df.empty or len(df) < max(p1, p2, 30):
            return False, "資料不足"
        
        df = df.sort_values('date')
        
        if strategy_name == 'MA_CROSS':
            # 賣點：死亡交叉 (短線跌破長線)
            df['MA_Short'] = ta.sma(df['close'], length=p1)
            df['MA_Long'] = ta.sma(df['close'], length=p2)
            curr_short, curr_long = df.iloc[-1]['MA_Short'], df.iloc[-1]['MA_Long']
            prev_short, prev_long = df.iloc[-2]['MA_Short'], df.iloc[-2]['MA_Long']
            if prev_short > prev_long and curr_short < curr_long:
                return True, f"均線死亡交叉 (MA{p1} < MA{p2})"

        elif strategy_name == 'RSI_REVERSAL':
            # 賣點：RSI 進入超買區 (>70) 並且掉頭向下
            df['RSI'] = ta.rsi(df['close'], length=p1)
            curr_rsi, prev_rsi = df.iloc[-1]['RSI'], df.iloc[-2]['RSI']
            if prev_rsi > 70 and curr_rsi < prev_rsi:
                return True, f"RSI 超買區反轉 (RSI={curr_rsi:.1f})"

        elif strategy_name == 'KD_CROSS':
            # 賣點：KD 高檔死亡交叉 (K < D 且 K > 80)
            kdf = ta.stoch(df['high'], df['low'], df['close'], k=p1, d=3, smooth_k=3)
            k_col, d_col = f"STOCHk_{p1}_3_3", f"STOCHd_{p1}_3_3"
            curr_k, curr_d = kdf.iloc[-1][k_col], kdf.iloc[-1][d_col]
            prev_k, prev_d = kdf.iloc[-2][k_col], kdf.iloc[-2][d_col]
            if prev_k > prev_d and curr_k < curr_d and curr_k > 80:
                return True, f"KD 高檔死亡交叉 (K={curr_k:.1f})"
                
    except Exception as e:
        print(f"❌ 計算賣出指標失敗 {stock_id}: {e}")
    
    return False, ""

def run_prediction():
    print(f"🤖 [盤前] 開始 AI 策略運算... {date.today()}")
    config = get_strategy_config()
    strategy_name = config.get('active_strategy', 'MA_CROSS')
    p1, p2 = int(config.get('param_1', 5)), int(config.get('param_2', 20))
    risk_pref = config.get('risk_preference', 'NEUTRAL')
    base_size = float(config.get('max_position_size', 100000))
    base_threshold = float(config.get('ai_confidence_threshold', 0.7))
    
    size_multiplier, threshold_adj = 1.0, 0.0
    if risk_pref == 'AVERSE': size_multiplier, threshold_adj = 0.8, 0.05
    elif risk_pref == 'SEEKING': size_multiplier, threshold_adj = 1.2, -0.05

    final_trade_size = base_size * size_multiplier
    final_threshold = base_threshold + threshold_adj
    
    print(f"🧠 邏輯: {strategy_name}, 信心門檻: {final_threshold:.2f}")
    
    target_stocks = ['2330.TW', '2317.TW', '2454.TW', '2881.TW', '2603.TW']
    api = DataLoader()
    if FINMIND_TOKEN: api.login_by_token(api_token=FINMIND_TOKEN)
    
    start_date = (date.today() - timedelta(days=100)).strftime('%Y-%m-%d')
    try:
        df_history = api.taiwan_stock_daily(stock_id=target_stocks, start_date=start_date, end_date=date.today().strftime('%Y-%m-%d'))
    except: return

    if df_history.empty: return

    orders_data = []
    try:
        account = supabase.table('sim_account').select('*').eq('user_id', 'default_user').execute().data[0]
        current_cash = float(account['cash_balance'])
    except: return
    
    for stock_id in target_stocks:
        df = df_history[df_history['stock_id'] == stock_id].copy()
        if len(df) < max(p1, p2, 30): continue
        df = df.sort_values('date')
        signal, limit_price = False, float(df.iloc[-1]['close'])
        
        try:
            if strategy_name == 'MA_CROSS':
                df['MA_Short'], df['MA_Long'] = ta.sma(df['close'], length=p1), ta.sma(df['close'], length=p2)
                if df.iloc[-2]['MA_Short'] < df.iloc[-2]['MA_Long'] and df.iloc[-1]['MA_Short'] > df.iloc[-1]['MA_Long']: signal = True
            elif strategy_name == 'RSI_REVERSAL':
                df['RSI'] = ta.rsi(df['close'], length=p1)
                if df.iloc[-2]['RSI'] < p2 and df.iloc[-1]['RSI'] > df.iloc[-2]['RSI']: signal, limit_price = True, limit_price * 0.99
            elif strategy_name == 'KD_CROSS':
                kdf = ta.stoch(df['high'], df['low'], df['close'], k=p1, d=3, smooth_k=3)
                k_col, d_col = f"STOCHk_{p1}_3_3", f"STOCHd_{p1}_3_3"
                if kdf.iloc[-2][k_col] < kdf.iloc[-2][d_col] and kdf.iloc[-1][k_col] > kdf.iloc[-1][d_col] and kdf.iloc[-1][k_col] < p2: signal = True
        except: continue

        if signal:
            shares = int(final_trade_size // limit_price)
            shares = (shares // 1000) * 1000 
            if shares <= 0: continue
            cost, _ = calculate_cost(limit_price, shares)
            if current_cash >= cost:
                orders_data.append({'user_id': 'default_user', 'date': str(date.today()), 'stock_id': stock_id, 'action': 'BUY', 'order_price': round(limit_price, 2), 'shares': shares, 'status': 'PENDING'})
                current_cash -= cost
                print(f"✅ {stock_id} 符合策略，準備掛單 {shares} 股")

    if orders_data: supabase.table('sim_orders').insert(orders_data).execute()

def run_settlement():
    print(f"⚖️ [盤後] 開始結算... {date.today()}")
    api = DataLoader()
    if FINMIND_TOKEN: api.login_by_token(api_token=FINMIND_TOKEN)
    today_str = date.today().strftime('%Y-%m-%d')
    
    # 1. 處理待成交訂單
    try:
        pending_orders = supabase.table('sim_orders').select('*').eq('status', 'PENDING').execute().data
        if pending_orders:
            stock_ids = list(set([o['stock_id'] for o in pending_orders]))
            df_market = api.taiwan_stock_daily(stock_id=stock_ids, start_date=today_str, end_date=today_str)
            if not df_market.empty:
                account = supabase.table('sim_account').select('*').eq('user_id', 'default_user').execute().data[0]
                cash = float(account['cash_balance'])
                for order in pending_orders:
                    stock_data = df_market[df_market['stock_id'] == order['stock_id']]
                    if stock_data.empty: continue
                    row = stock_data.iloc[0]
                    executed = False
                    if order['action'] == 'BUY' and row['low'] <= order['order_price']:
                        total, fee = calculate_cost(order['order_price'], order['shares'])
                        executed = True
                        update_inventory(order['stock_id'], order['shares'], order['order_price'])
                    if executed:
                        supabase.table('sim_transactions').insert({'user_id': 'default_user', 'stock_id': order['stock_id'], 'action': order['action'], 'price': order['order_price'], 'shares': order['shares'], 'fee': fee, 'tax': 0, 'total_amount': total}).execute()
                        supabase.table('sim_orders').update({'status': 'FILLED'}).eq('id', order['id']).execute()
                    else:
                        if order['action'] == 'BUY': cash += calculate_cost(order['order_price'], order['shares'])[0]
                        supabase.table('sim_orders').update({'status': 'CANCELLED'}).eq('id', order['id']).execute()
                supabase.table('sim_account').update({'cash_balance': cash}).eq('user_id', 'default_user').execute()
    except: pass

    # 2. 檢查停損停利 (AI 出場)
    print("🔍 檢查庫存 (停損 / 停利 / AI出場)...")
    try:
        config = get_strategy_config()
        stop_loss_pct = float(config.get('stop_loss_pct', 0.05))
        take_profit_pct = float(config.get('take_profit_pct', 0.10))
        active_strat = config.get('active_strategy', 'MA_CROSS')
        p1, p2 = int(config.get('param_1', 5)), int(config.get('param_2', 20))
        
        inventory = supabase.table('sim_inventory').select('*').eq('user_id', 'default_user').execute().data
        if inventory:
            inv_stock_ids = [item['stock_id'] for item in inventory]
            df_inv_market = api.taiwan_stock_daily(stock_id=inv_stock_ids, start_date=today_str, end_date=today_str)
            if not df_inv_market.empty:
                account = supabase.table('sim_account').select('cash_balance').eq('user_id', 'default_user').execute().data[0]
                cash = float(account['cash_balance'])
                for item in inventory:
                    stock_data = df_inv_market[df_inv_market['stock_id'] == item['stock_id']]
                    if stock_data.empty: continue
                    close_price, avg_cost = float(stock_data.iloc[0]['close']), float(item['avg_cost'])
                    roi = (close_price - avg_cost) / avg_cost
                    action, reason = None, ""
                    
                    if roi <= -stop_loss_pct: action, reason = 'SELL', f"🛑 停損 ({roi*100:.2f}%)"
                    elif take_profit_pct > 0:
                        if roi >= take_profit_pct: action, reason = 'SELL', f"💰 固定停利 ({roi*100:.2f}%)"
                    elif roi > 0:
                        should_sell, tech_reason = check_technical_exit(item['stock_id'], active_strat, p1, p2)
                        if should_sell: action, reason = 'SELL', f"🤖 AI 技術出場: {tech_reason} ({roi*100:.2f}%)"
                    
                    if action == 'SELL':
                        revenue, fee, tax = calculate_revenue(close_price, item['shares'])
                        supabase.table('sim_inventory').delete().eq('stock_id', item['stock_id']).execute()
                        cash += revenue
                        supabase.table('sim_transactions').insert({'user_id': 'default_user', 'stock_id': item['stock_id'], 'action': 'SELL', 'price': close_price, 'shares': item['shares'], 'fee': fee, 'tax': tax, 'total_amount': revenue}).execute()
                        print(f"⚡ {item['stock_id']} {reason} -> 賣出成功")
                supabase.table('sim_account').update({'cash_balance': cash}).eq('user_id', 'default_user').execute()
    except: pass

    try: calculate_total_assets(float(supabase.table('sim_account').select('cash_balance').eq('user_id', 'default_user').execute().data[0]['cash_balance']))
    except: pass
    print("✅ 結算完成")

def update_inventory(stock_id, shares, price):
    try:
        inv = supabase.table('sim_inventory').select('*').eq('user_id', 'default_user').eq('stock_id', stock_id).execute().data
        if inv:
            new_shares = inv[0]['shares'] + shares
            if new_shares > 0:
                avg_cost = ((float(inv[0]['shares']) * float(inv[0]['avg_cost'])) + (float(shares) * float(price))) / new_shares if shares > 0 else inv[0]['avg_cost']
                supabase.table('sim_inventory').update({'shares': new_shares, 'avg_cost': avg_cost, 'updated_at': datetime.now().isoformat()}).eq('user_id', 'default_user').eq('stock_id', stock_id).execute()
            else: supabase.table('sim_inventory').delete().eq('user_id', 'default_user').eq('stock_id', stock_id).execute()
        elif shares > 0: supabase.table('sim_inventory').insert({'user_id': 'default_user', 'stock_id': stock_id, 'shares': shares, 'avg_cost': price}).execute()
    except: pass

def calculate_total_assets(cash):
    try:
        inventory = supabase.table('sim_inventory').select('*').eq('user_id', 'default_user').execute().data
        stock_value = 0
        for item in inventory:
            last_price = supabase.table('fact_price').select('close').eq('stock_id', item['stock_id']).order('date', desc=True).limit(1).execute().data
            stock_value += (float(last_price[0]['close']) if last_price else float(item['avg_cost'])) * int(item['shares'])
        total_asset = cash + stock_value
        supabase.table('sim_account').update({'total_asset': total_asset}).eq('user_id', 'default_user').execute()
        supabase.table('sim_daily_assets').upsert({'user_id': 'default_user', 'date': str(date.today()), 'cash_balance': cash, 'stock_value': stock_value, 'total_assets': total_asset}).execute()
    except: pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["predict", "settle"], required=True)
    args = parser.parse_args()
    if args.action == "predict": run_prediction()
    elif args.action == "settle": run_settlement()
