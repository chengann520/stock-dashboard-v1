import os
import argparse
import pandas as pd
from datetime import datetime, date
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
        # 讀取設定表
        data = supabase.table('strategy_config').select('*').eq('user_id', 'default_user').execute().data
        if data:
            return data[0]
    except Exception as e:
        print(f"⚠️ 讀取策略設定失敗，使用預設值: {e}")
    
    # 預設值 (萬一資料庫讀不到)
    return {
        'max_position_size': 100000,
        'stop_loss_pct': 0.05,
        'ai_confidence_threshold': 0.7
    }

def run_prediction():
    print(f"🤖 [盤前] 開始 AI 預測... {date.today()}")
    
    # 1. 讀取最新策略設定
    config = get_strategy_config()
    print(f"⚙️ 目前策略: 模式={config.get('strategy_mode')}, 最大倉位=${config.get('max_position_size')}, 信心門檻={config.get('ai_confidence_threshold')}")

    # === AI 邏輯區 (模擬) ===
    # 假設這是 AI 算出來的原始信號
    raw_predictions = [
        {'stock_id': '2330.TW', 'action': 'BUY', 'price': 580.0, 'confidence': 0.85},
        {'stock_id': '2881.TW', 'action': 'BUY', 'price': 62.5, 'confidence': 0.60}, # 信心較低
        {'stock_id': '2603.TW', 'action': 'BUY', 'price': 150.0, 'confidence': 0.95}
    ]
    
    try:
        account = supabase.table('sim_account').select('*').eq('user_id', 'default_user').execute().data[0]
        current_cash = float(account['cash_balance'])
        
        orders_data = []
        
        # 2. 應用策略過濾器
        threshold = float(config.get('ai_confidence_threshold', 0.7))
        max_trade_amt = float(config.get('max_position_size', 100000))

        for pred in raw_predictions:
            # 規則 A: 信心不足就不做
            if pred['confidence'] < threshold:
                print(f"❌ {pred['stock_id']} 信心 {pred['confidence']} 低於門檻 {threshold}，跳過")
                continue
                
            # 規則 B: 計算股數 (不超過最大單筆金額)
            shares_can_buy = int(max_trade_amt // pred['price'])
            
            # 轉成整張 (台股通常 1000 股一張)
            shares_can_buy = (shares_can_buy // 1000) * 1000 
            
            if shares_can_buy <= 0:
                print(f"⚠️ {pred['stock_id']} 資金配額不足以買一張，跳過")
                continue

            est_cost, _ = calculate_cost(pred['price'], shares_can_buy)
            
            # 規則 C: 總資金檢查
            if current_cash >= est_cost:
                orders_data.append({
                    'user_id': 'default_user',
                    'date': str(date.today()),
                    'stock_id': pred['stock_id'],
                    'action': pred['action'],
                    'order_price': pred['price'],
                    'shares': shares_can_buy,
                    'status': 'PENDING'
                })
                current_cash -= est_cost # 暫扣
                print(f"✅ {pred['stock_id']} 符合策略，準備掛單 {shares_can_buy} 股")
            else:
                print(f"⚠️ {pred['stock_id']} 帳戶餘額不足")

        # 3. 寫入資料庫
        if orders_data:
            supabase.table('sim_orders').insert(orders_data).execute()
            print(f"🚀 已送出 {len(orders_data)} 筆訂單")
        else:
            print("💤 本日無符合策略的標的")
    except Exception as e:
        print(f"❌ 預測邏輯錯誤: {e}")

def run_settlement():
    """盤後：抓取真實股價並結算"""
    print(f"⚖️ [盤後] 開始結算... {date.today()}")
    
    # 1. 從資料庫抓取今日未成交訂單
    try:
        pending_orders = supabase.table('sim_orders').select('*').eq('status', 'PENDING').execute().data
        if not pending_orders:
            print("沒有待處理的訂單")
            return
    except Exception as e:
        print(f"❌ 讀取訂單錯誤: {e}")
        return

    # 2. 抓取今日真實股市行情 (FinMind)
    api = DataLoader()
    if FINMIND_TOKEN:
        api.login_by_token(api_token=FINMIND_TOKEN)
    
    stock_ids = list(set([o['stock_id'] for o in pending_orders]))
    today_str = date.today().strftime('%Y-%m-%d')
    
    try:
        df_market = api.taiwan_stock_daily(
            stock_id=stock_ids,
            start_date=today_str,
            end_date=today_str
        )
    except Exception as e:
        print(f"❌ FinMind 抓取錯誤: {e}")
        return
    
    if df_market.empty:
        print("❌ 抓不到今日股價資料 (可能是假日或尚未收盤)")
        return

    # 3. 執行比對與結算
    try:
        account = supabase.table('sim_account').select('*').eq('user_id', 'default_user').execute().data[0]
        cash = float(account['cash_balance'])
        
        for order in pending_orders:
            stock_data = df_market[df_market['stock_id'] == order['stock_id']]
            if stock_data.empty: continue
            
            row = stock_data.iloc[0]
            executed = False
            fee = 0
            tax = 0
            total_amount = 0
            
            if order['action'] == 'BUY':
                if row['low'] <= order['order_price']:
                    total_amount, fee = calculate_cost(order['order_price'], order['shares'])
                    executed = True
                    update_inventory(order['stock_id'], order['shares'], order['order_price'])
                    print(f"🎯 成交買入: {order['stock_id']} @ {order['order_price']}")
            
            elif order['action'] == 'SELL':
                if row['high'] >= order['order_price']:
                    total_amount, fee, tax = calculate_revenue(order['order_price'], order['shares'])
                    executed = True
                    cash += total_amount
                    update_inventory(order['stock_id'], -order['shares'], order['order_price'])
                    print(f"🎯 成交賣出: {order['stock_id']} @ {order['order_price']}")

            if executed:
                # 紀錄到 sim_transactions
                supabase.table('sim_transactions').insert({
                    'user_id': 'default_user',
                    'stock_id': order['stock_id'],
                    'action': order['action'],
                    'price': order['order_price'],
                    'shares': order['shares'],
                    'fee': fee,
                    'tax': tax,
                    'total_amount': total_amount
                }).execute()

                supabase.table('sim_orders').update({
                    'status': 'FILLED',
                    'fee': fee,
                    'tax': tax,
                    'total_amount': total_amount
                }).eq('id', order['id']).execute()
            else:
                # 未成交，取消訂單並退回資金 (如果是買單)
                if order['action'] == 'BUY':
                    est_cost, _ = calculate_cost(order['order_price'], order['shares'])
                    cash += est_cost
                
                supabase.table('sim_orders').update({'status': 'CANCELLED'}).eq('id', order['id']).execute()
                print(f"⏩ 未成交取消: {order['stock_id']}")

        # 更新最終現金
        supabase.table('sim_account').update({'cash_balance': cash}).eq('user_id', 'default_user').execute()
        
        # 計算總資產 (現金 + 持股價值) 並紀錄每日快照
        calculate_total_assets(cash)
        
        print("✅ 結算完成")
    except Exception as e:
        print(f"❌ 結算邏輯錯誤: {e}")

def update_inventory(stock_id, shares, price):
    """更新庫存邏輯"""
    try:
        inv = supabase.table('sim_inventory').select('*').eq('user_id', 'default_user').eq('stock_id', stock_id).execute().data
        if inv:
            new_shares = inv[0]['shares'] + shares
            if new_shares > 0:
                # 更新平均成本 (僅買入時更新)
                if shares > 0:
                    total_cost = (float(inv[0]['shares']) * float(inv[0]['avg_cost'])) + (float(shares) * float(price))
                    avg_cost = total_cost / new_shares
                else:
                    avg_cost = inv[0]['avg_cost']
                
                supabase.table('sim_inventory').update({
                    'shares': new_shares,
                    'avg_cost': avg_cost,
                    'updated_at': datetime.now().isoformat()
                }).eq('user_id', 'default_user').eq('stock_id', stock_id).execute()
            else:
                supabase.table('sim_inventory').delete().eq('user_id', 'default_user').eq('stock_id', stock_id).execute()
        elif shares > 0:
            supabase.table('sim_inventory').insert({
                'user_id': 'default_user',
                'stock_id': stock_id,
                'shares': shares,
                'avg_cost': price
            }).execute()
    except Exception as e:
        print(f"❌ 庫存更新錯誤: {e}")

def calculate_total_assets(cash):
    """計算總資產並存入每日快照"""
    try:
        inventory = supabase.table('sim_inventory').select('*').eq('user_id', 'default_user').execute().data
        stock_value = 0
        for item in inventory:
            # 取得最新收盤價
            last_price = supabase.table('fact_price').select('close').eq('stock_id', item['stock_id']).order('date', desc=True).limit(1).execute().data
            price = float(last_price[0]['close']) if last_price else float(item['avg_cost'])
            stock_value += (price * int(item['shares']))
        
        total_asset = cash + stock_value
        supabase.table('sim_account').update({'total_asset': total_asset}).eq('user_id', 'default_user').execute()

        # 紀錄每日快照
        supabase.table('sim_daily_assets').upsert({
            'user_id': 'default_user',
            'date': str(date.today()),
            'cash_balance': cash,
            'stock_value': stock_value,
            'total_assets': total_asset
        }).execute()
    except Exception as e:
        print(f"❌ 總資產計算錯誤: {e}")

# --- 3. 主程式入口 ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["predict", "settle"], required=True)
    args = parser.parse_args()

    if args.action == "predict":
        run_prediction()
    elif args.action == "settle":
        run_settlement()
