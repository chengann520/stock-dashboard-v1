import os
import argparse
import time
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta, date
from supabase import create_client
from tqdm import tqdm

# --- 1. 連線設定 ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ 錯誤: 環境變數未設定 (SUPABASE_URL/KEY)")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 交易參數
FEE_RATE = 0.001425
TAX_RATE = 0.003

# 定義 N1 策略專用的「台股科技巨頭池」
TECH_GIANTS = [
    '2330.TW', # 台積電
    '2454.TW', # 聯發科
    '2317.TW', # 鴻海
    '2382.TW', # 廣達
    '2308.TW', # 台達電
    '3711.TW', # 日月光
    '3008.TW', # 大立光
    '3034.TW', # 聯詠
    '2303.TW', # 聯電
    '2357.TW'  # 華碩
]
SAFE_ASSET = '00679B.TW' # 元大美債20年 (作為避險資產)

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

# --- 2. 輔助函數 ---

def get_strategy_config():
    """從資料庫讀取策略與風控設定"""
    try:
        data = supabase.table('strategy_config').select('*').eq('user_id', 'default_user').execute().data
        if data: return data[0]
    except Exception as e:
        print(f"⚠️ 讀取設定失敗: {e}")
    # 預設值
    return {
        'max_position_size': 100000, 'risk_preference': 'NEUTRAL',
        'stop_loss_pct': 0.05, 'take_profit_pct': 0.1,
        'active_strategy': 'MA_CROSS', 'param_1': 5, 'param_2': 20,
        'ai_confidence_threshold': 0.7
    }

def get_all_stocks_from_db():
    """從 dim_stock 表格讀取所有股票代碼"""
    print("📥 正在從資料庫讀取股票清單...")
    try:
        res = supabase.table('dim_stock').select('stock_id').limit(3000).execute()
        stocks = [item['stock_id'] for item in res.data]
        print(f"✅ 成功從資料庫讀取 {len(stocks)} 檔股票")
        return stocks
    except Exception as e:
        print(f"❌ 讀取股票清單失敗: {e}")
        stocks = ['2330.TW', '2317.TW', '2454.TW', '2881.TW', '2603.TW']
        print(f"⚠️ 使用預設代單檔數: {len(stocks)} ({stocks})")
        return stocks

def check_technical_exit(stock_id, strategy_name, p1, p2):
    """檢查這支股票是否出現「技術賣訊」"""
    try:
        start_date = (date.today() - timedelta(days=120)).strftime('%Y-%m-%d')
        res = supabase.table('fact_price').select('*').eq('stock_id', stock_id).gte('date', start_date).order('date').execute()
        df = pd.DataFrame(res.data)
        
        if df.empty or len(df) < max(p1, p2, 30): return False, "資料不足"
        
        if strategy_name == 'MA_CROSS':
            df['MA_S'] = ta.sma(df['close'], length=p1)
            df['MA_L'] = ta.sma(df['close'], length=p2)
            if df.iloc[-2]['MA_S'] > df.iloc[-2]['MA_L'] and df.iloc[-1]['MA_S'] < df.iloc[-1]['MA_L']:
                return True, f"均線死亡交叉 (MA{p1} < MA{p2})"

        elif strategy_name == 'RSI_REVERSAL':
            df['RSI'] = ta.rsi(df['close'], length=p1)
            curr_rsi, prev_rsi = df.iloc[-1]['RSI'], df.iloc[-2]['RSI']
            if prev_rsi > 70 and curr_rsi < prev_rsi:
                return True, f"RSI 超買區反轉 (RSI={curr_rsi:.1f})"

        elif strategy_name == 'KD_CROSS':
            kdf = ta.stoch(df['high'], df['low'], df['close'], k=p1, d=3, smooth_k=3)
            k_col, d_col = f"STOCHk_{p1}_3_3", f"STOCHd_{p1}_3_3"
            if kdf.iloc[-2][k_col] > kdf.iloc[-2][d_col] and kdf.iloc[-1][k_col] < kdf.iloc[-1][d_col] and kdf.iloc[-1][k_col] > 80:
                return True, f"KD 高檔死亡交叉 (K={kdf.iloc[-1][k_col]:.1f})"
        
        elif strategy_name == 'MACD_CROSS':
            macdf = ta.macd(df['close'], fast=p1, slow=p2, signal=9)
            hist_col = f"MACDh_{p1}_{p2}_9"
            if df.iloc[-2][hist_col] > 0 and df.iloc[-1][hist_col] < 0:
                return True, f"MACD 柱狀圖翻綠 (MACD={df.iloc[-1][hist_col]:.2f})"
                
    except Exception as e:
        print(f"❌ 計算賣出指標失敗 {stock_id}: {e}")
    return False, ""

def calculate_confidence(df, strategy_name, p1, p2):
    """
    計算 AI 對該訊號的信心度 (0.0 ~ 1.0)
    邏輯：根據指標的「超買/超賣」程度或「均線偏離度」來加權
    """
    try:
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        if strategy_name == 'MA_CROSS':
            # 均線金叉信心：看短均線往上衝的斜率
            slope = (last['MA_S'] - prev['MA_S']) / prev['MA_S']
            conf = min(0.5 + (slope * 50), 0.95) # 基礎 0.5，最高 0.95
            return round(conf, 2)
            
        elif strategy_name == 'RSI_REVERSAL':
            # RSI 信心：RSI 越低代表超賣越嚴重，反彈信心越高
            rsi_val = last['RSI']
            conf = 1.0 - (rsi_val / 100.0) # RSI 20 -> 0.8
            return round(conf, 2)
            
        elif strategy_name == 'KD_CROSS':
            # KD 信心：看 K 值在低檔的位置
            k_col = f"STOCHk_{p1}_3_3"
            k_val = last[k_col]
            conf = 1.0 - (k_val / 100.0)
            return round(conf, 2)
            
        elif strategy_name == 'MACD_CROSS':
            # MACD 信心：看柱狀圖翻紅的大小
            hist_col = f"MACDh_{p1}_{p2}_9"
            val = last[hist_col]
            conf = 0.5 + min(abs(val) / 2, 0.45)
            return round(conf, 2)
            
        elif strategy_name == 'N1_MOMENTUM':
            # N1 信心：看動能強度與 RSI 是否有足夠空間
            momentum = last.get('momentum', 0)
            rsi = last.get('RSI', 50)
            conf = 0.4 + (momentum * 2) + (1.0 - (rsi / 100.0)) * 0.2
            return min(round(conf, 2), 0.98)

        elif strategy_name == 'BEST_OF_3':
            # Best of 3 信心：跌幅越深信心越高
            drawdown = abs(last.get('drawdown', 0))
            conf = 0.6 + (drawdown * 2)
            return min(round(conf, 2), 0.99)

    except:
        pass
    return 0.75 # 預設信心

# --- 3. 核心功能 ---

def run_prediction():
    print(f"🤖 [盤前] 開始 AI 策略運算... {date.today()}")
    config = get_strategy_config()
    strategy_name = config.get('active_strategy', 'MA_CROSS')
    
    # 讀取參數
    p1 = int(config.get('param_1', 60))
    p2 = int(config.get('param_2', 80))
    
    # 讀取風控與資金
    risk_pref = config.get('risk_preference', 'NEUTRAL')
    base_size = float(config.get('max_position_size', 100000))
    conf_threshold = float(config.get('ai_confidence_threshold', 0.7))
    size_multiplier = {'AVERSE': 0.8, 'NEUTRAL': 1.0, 'SEEKING': 1.2}.get(risk_pref, 1.0)
    final_trade_size = base_size * size_multiplier
    
    print(f"🧠 策略: {strategy_name} ({p1},{p2}) | 信心門檻: {conf_threshold} | 風險模式: {risk_pref} | 單筆預算: ${final_trade_size:,.0f}")

    start_date = (date.today() - timedelta(days=300)).strftime('%Y-%m-%d')
    
    try:
        account = supabase.table('sim_account').select('*').eq('user_id', 'default_user').execute().data[0]
        current_cash = float(account['cash_balance'])
    except: return
    
    orders_data = []

    # 取得現有庫存與掛單，避免重複買入
    try:
        inventory = [i['stock_id'] for i in supabase.table('sim_inventory').select('stock_id').eq('user_id', 'default_user').execute().data]
        pending = [o['stock_id'] for o in supabase.table('sim_orders').select('stock_id').eq('user_id', 'default_user').eq('status', 'PENDING').execute().data]
        owned_stocks = set(inventory + pending)
    except: owned_stocks = set()

    # ==========================================
    # 🏆 策略 1: N1 Momentum (強者恆強 + 避險)
    # ==========================================
    if strategy_name == 'N1_MOMENTUM':
        safe_asset_id = config.get('safe_asset_id', '00679B.TW')
        print(f"🏆 執行 N1 策略 (池: {len(TECH_GIANTS)}檔科技股 | 動能: {p1}日) | 避險模式: {safe_asset_id}")
        candidates = []
        
        res = supabase.table('fact_price').select('*').in_('stock_id', TECH_GIANTS).gte('date', start_date).order('date').execute()
        df_all = pd.DataFrame(res.data)
        
        if df_all.empty:
            print("❌ 無法取得科技股資料")
            return

        for stock_id, df in df_all.groupby('stock_id'):
            if len(df) < p1 + 10: continue
            df = df.sort_values('date')
            
            current_price = float(df.iloc[-1]['close'])
            # 動能計算：過去 p1 天的漲幅
            momentum = (current_price / float(df.iloc[-1-p1]['close'])) - 1
            
            # 安全檢查：RSI 是否過熱
            df['RSI'] = ta.rsi(df['close'], length=14)
            current_rsi = float(df.iloc[-1]['RSI'])
            
            # 趨勢檢查：是否在 MA20 之上
            df['MA20'] = ta.sma(df['close'], length=20)
            trend_ok = current_price > float(df.iloc[-1]['MA20'])
            
            candidates.append({
                'stock_id': stock_id, 'momentum': momentum, 'rsi': current_rsi,
                'price': current_price, 'trend_ok': trend_ok
            })
            
        # 排名：動能由高到低
        candidates.sort(key=lambda x: x['momentum'], reverse=True)
        top_picks = candidates[:2]
        final_buy_list = []
        
        print("📊 N1 候選排名 (Top 2):")
        for c in top_picks:
            print(f"   - {c['stock_id']}: 漲幅 {c['momentum']*100:.1f}%, RSI {c['rsi']:.1f}")
            # 嚴格避險：只要過熱或破線就不買股票
            if c['rsi'] < p2 and c['trend_ok']:
                final_buy_list.append(c['stock_id'])
            else:
                print(f"   ⚠️ {c['stock_id']} 觸發安全防線 (RSI過熱或趨勢轉弱)")
        
        budget_per_stock = final_trade_size
        for stock in final_buy_list:
            price = [x['price'] for x in candidates if x['stock_id'] == stock][0]
            shares = int(budget_per_stock // price)
            if shares > 0 and stock not in owned_stocks:
                # 計算信心度
                df_stock = df_all[df_all['stock_id'] == stock].copy()
                df_stock['momentum'] = [x['momentum'] for x in candidates if x['stock_id'] == stock][0]
                df_stock['RSI'] = [x['rsi'] for x in candidates if x['stock_id'] == stock][0]
                confidence = calculate_confidence(df_stock, 'N1_MOMENTUM', p1, p2)
                
                if confidence >= conf_threshold:
                    est_cost, _ = calculate_cost(price, shares)
                    orders_data.append({
                        'user_id': 'default_user', 
                        'date': str(date.today()), 
                        'stock_id': stock, 
                        'action': 'BUY', 
                        'order_price': round(price, 2), 
                        'shares': shares, 
                        'status': 'PENDING',
                        'total_amount': est_cost
                    })
                    # 寫入 AI 分析表
                    supabase.table('ai_analysis').upsert({
                        'stock_id': stock, 'date': str(date.today()), 'signal': 'Bull', 
                        'probability': confidence, 'entry_price': round(price, 2),
                        'target_price': round(price * 1.1, 2), 'stop_loss': round(price * 0.95, 2)
                    }).execute()
                else:
                    print(f"   ⚠️ {stock} 信心度不足 ({confidence} < {conf_threshold})")

        # 處理避險
        if len(final_buy_list) < 2:
            remaining_slots = 2 - len(final_buy_list)
            print(f"🛡️ {remaining_slots} 個部位啟動避險機制")
            
            if safe_asset_id == 'CASH':
                print(f"💰 避險模式：持有現金 (CASH)")
            else:
                res_safe = supabase.table('fact_price').select('*').eq('stock_id', safe_asset_id).order('date', desc=True).limit(1).execute()
                if res_safe.data:
                    safe_price = float(res_safe.data[0]['close'])
                    safe_budget = budget_per_stock * remaining_slots
                    shares = int(safe_budget // safe_price)
                    if shares > 0:
                        orders_data.append({'user_id': 'default_user', 'date': str(date.today()), 'stock_id': safe_asset_id, 'action': 'BUY', 'order_price': round(safe_price, 2), 'shares': shares, 'status': 'PENDING'})
                        print(f"🛡️ 避險模式：買入 {safe_asset_id} ({shares}股)")

    # ==========================================
    # 🚀 策略 2: Best of 3 (Drawdown Reversal)
    # ==========================================
    elif strategy_name == 'BEST_OF_3':
        print(f"🚀 執行 Best of 3 策略 (尋找跌深反彈優質股)...")
        pool = TECH_GIANTS 
        res = supabase.table('fact_price').select('*').in_('stock_id', pool).gte('date', start_date).order('date').execute()
        df_all = pd.DataFrame(res.data)
        candidates = []
        
        for stock_id, df in df_all.groupby('stock_id'):
            if len(df) < 200: continue
            df = df.sort_values('date')
            current_price = float(df.iloc[-1]['close'])
            
            # 回撤計算：距離 p1 天內最高點的跌幅
            recent_high = df['high'].tail(p1).max()
            drawdown = (current_price - recent_high) / recent_high
            
            # 長線保護：必須在 MA(p2) 之上 (預設 200)
            df['MA_L'] = ta.sma(df['close'], length=p2)
            ma_long = float(df.iloc[-1]['MA_L'])
            
            if current_price > ma_long:
                candidates.append({'stock_id': stock_id, 'drawdown': drawdown, 'price': current_price})
        
        # 排序：回撤越大 (跌越深) 排前面
        candidates.sort(key=lambda x: x['drawdown'])
        if candidates:
            best_dip = candidates[0]
            print(f"🎯 鎖定抄底標的: {best_dip['stock_id']} (回撤 {best_dip['drawdown']*100:.2f}%)")
            shares = int(final_trade_size // best_dip['price'])
            if shares > 0 and best_dip['stock_id'] not in owned_stocks:
                # 計算信心度
                df_dip = df_all[df_all['stock_id'] == best_dip['stock_id']].copy()
                df_dip['drawdown'] = best_dip['drawdown']
                confidence = calculate_confidence(df_dip, 'BEST_OF_3', p1, p2)
                
                if confidence >= conf_threshold:
                    est_cost, _ = calculate_cost(best_dip['price'], shares)
                    orders_data.append({
                        'user_id': 'default_user', 
                        'date': str(date.today()), 
                        'stock_id': best_dip['stock_id'], 
                        'action': 'BUY', 
                        'order_price': round(best_dip['price'], 2), 
                        'shares': shares, 
                        'status': 'PENDING',
                        'total_amount': est_cost
                    })
                    supabase.table('ai_analysis').upsert({
                        'stock_id': best_dip['stock_id'], 'date': str(date.today()), 'signal': 'Bull', 
                        'probability': confidence, 'entry_price': round(best_dip['price'], 2),
                        'target_price': round(best_dip['price'] * 1.15, 2), 'stop_loss': round(best_dip['price'] * 0.93, 2)
                    }).execute()
                else:
                    print(f"   ⚠️ {best_dip['stock_id']} 信心度不足 ({confidence} < {conf_threshold})")
        else:
            print("💤 沒有優質股符合抄底條件 (需在長線支撐之上)")

    # ==========================================
    # 原本的技術指標策略 (MA, RSI, KD...)
    # ==========================================
    else:
        all_stocks = get_all_stocks_from_db()
        print(f"🔍 [通用掃描] 開始掃描 {len(all_stocks)} 檔股票...")
        BATCH_SIZE = 100
        total_scanned = 0
        total_signals = 0
        total_filtered_conf = 0
        
        for i in tqdm(range(0, len(all_stocks), BATCH_SIZE), desc="Analyzing Market"):
            batch_stocks = all_stocks[i : i + BATCH_SIZE]
            try:
                res = supabase.table('fact_price').select('*').in_('stock_id', batch_stocks).gte('date', start_date).order('date').execute()
                df_batch = pd.DataFrame(res.data)
                if df_batch.empty: continue

                for stock_id, df in df_batch.groupby('stock_id'):
                    total_scanned += 1
                    if len(df) < p2 + 5: continue
                    df = df.sort_values('date')
                    limit_price = float(df.iloc[-1]['close'])
                    signal = False
                    
                    try:
                        # 核心邏輯：偵測最近 3 天是否有交叉訊號
                        if strategy_name == 'MA_CROSS':
                            df['MA_S'], df['MA_L'] = ta.sma(df['close'], length=p1), ta.sma(df['close'], length=p2)
                            is_cross = (df['MA_S'].shift(1) < df['MA_L'].shift(1)) & (df['MA_S'] > df['MA_L'])
                            
                            if stock_id == '2330.TW': # 針對台積電測試
                                print(f"2330 Debug: MA_S={df.iloc[-1]['MA_S']:.2f}, MA_L={df.iloc[-1]['MA_L']:.2f}, Prev_MA_S={df.iloc[-2]['MA_S']:.2f}, Prev_MA_L={df.iloc[-2]['MA_L']:.2f}, Cross={is_cross.iloc[-1]}")

                            print(f"🔍 [{stock_id}] MA{p1}:{df['MA_S'].iloc[-1]:.2f}, MA{p2}:{df['MA_L'].iloc[-1]:.2f} | 交叉(3日): {is_cross.tail(3).any()}")
                            if is_cross.tail(3).any(): signal = True
                        elif strategy_name == 'RSI_REVERSAL':
                            df['RSI'] = ta.rsi(df['close'], length=p1)
                            is_rev = (df['RSI'].shift(1) < p2) & (df['RSI'] > df['RSI'].shift(1))
                            print(f"🔍 [{stock_id}] RSI:{df['RSI'].iloc[-1]:.2f} | 反轉(3日): {is_rev.tail(3).any()}")
                            if is_rev.tail(3).any(): signal, limit_price = True, limit_price * 0.99
                        elif strategy_name == 'KD_CROSS':
                            kdf = ta.stoch(df['high'], df['low'], df['close'], k=p1, d=3, smooth_k=3)
                            k_col, d_col = f"STOCHk_{p1}_3_3", f"STOCHd_{p1}_3_3"
                            is_cross = (kdf[k_col].shift(1) < kdf[d_col].shift(1)) & (kdf[k_col] > kdf[d_col]) & (kdf[k_col] < p2)
                            print(f"🔍 [{stock_id}] K:{kdf[k_col].iloc[-1]:.2f}, D:{kdf[d_col].iloc[-1]:.2f} | 交叉(3日): {is_cross.tail(3).any()}")
                            if is_cross.tail(3).any(): signal = True
                        elif strategy_name == 'MACD_CROSS':
                            macdf = ta.macd(df['close'], fast=p1, slow=p2, signal=9)
                            hist_col = f"MACDh_{p1}_{p2}_9"
                            is_cross = (macdf[hist_col].shift(1) <= 0) & (macdf[hist_col] > 0)
                            print(f"🔍 [{stock_id}] MACD Hist:{macdf[hist_col].iloc[-1]:.4f} | 交叉(3日): {is_cross.tail(3).any()}")
                            if is_cross.tail(3).any(): signal = True
                    except: continue

                    if signal:
                        total_signals += 1
                        if stock_id not in owned_stocks:
                            confidence = calculate_confidence(df, strategy_name, p1, p2)
                            if confidence >= conf_threshold:
                                try:
                                    supabase.table('ai_analysis').upsert({
                                        'stock_id': stock_id, 'date': str(date.today()), 'signal': 'Bull', 
                                        'probability': confidence, 'entry_price': round(limit_price, 2),
                                        'target_price': round(limit_price * 1.1, 2), 'stop_loss': round(limit_price * 0.95, 2)
                                    }).execute()
                                except: pass
                                
                                shares = int(final_trade_size // limit_price)
                                if shares > 0:
                                    est_cost, _ = calculate_cost(limit_price, shares)
                                    if current_cash >= est_cost:
                                        orders_data.append({
                                            'user_id': 'default_user', 
                                            'date': str(date.today()), 
                                            'stock_id': stock_id, 
                                            'action': 'BUY', 
                                            'order_price': round(limit_price, 2), 
                                            'shares': shares, 
                                            'status': 'PENDING',
                                            'total_amount': est_cost
                                        })
                                        current_cash -= est_cost
                                        print(f"✅ 成功掛單: {stock_id} ({shares}股, 單價 {limit_price})")
                                    else:
                                        print(f"💸 資金不足略過: {stock_id} (需 {est_cost}, 剩 {current_cash})")
                                else:
                                    print(f"🤏 預算不足買一股: {stock_id} (股價 {limit_price}, 預算 {final_trade_size})")
                            else:
                                total_filtered_conf += 1
                                print(f"📉 信心不足過濾: {stock_id} ({confidence} < {conf_threshold})")
                        else:
                            print(f"🎒 已持有略過: {stock_id}")
            except Exception as e: 
                print(f"⚠️ 掃描批次時出錯: {e}")
                time.sleep(1)
        
        print(f"\n📊 掃描總結:")
        print(f"   - 掃描標的數: {total_scanned}")
        print(f"   - 觸發訊號數: {total_signals}")
        print(f"   - 因信心不足過濾: {total_filtered_conf}")
        print(f"   - 最終入選掛單: {len(orders_data)}")

    # 3. 寫入資料庫 (通用)
    if orders_data:
        real_account = supabase.table('sim_account').select('cash_balance').eq('user_id', 'default_user').execute().data[0]
        real_cash = float(real_account['cash_balance'])
        final_orders = []
        for order in orders_data:
            cost, _ = calculate_cost(order['order_price'], order['shares'])
            if real_cash >= cost:
                final_orders.append(order)
                real_cash -= cost
        if final_orders:
            supabase.table('sim_orders').insert(final_orders).execute()
            print(f"🚀 已送出 {len(final_orders)} 筆委託單")
        else: print("💸 資金不足以執行任何訂單")
    else: print("💤 今日無符合策略之標的")

def run_settlement():
    print(f"⚖️ [盤後] 開始結算... {date.today()}")
    today_str = date.today().strftime('%Y-%m-%d')
    
    try:
        pending_orders = supabase.table('sim_orders').select('*').eq('status', 'PENDING').execute().data
        if pending_orders:
            stock_ids = list(set([o['stock_id'] for o in pending_orders]))
            res = supabase.table('fact_price').select('*').in_('stock_id', stock_ids).eq('date', today_str).execute()
            df_market = pd.DataFrame(res.data)
            
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
    except Exception as e:
        print(f"❌ 結算失敗: {e}")

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
            res = supabase.table('fact_price').select('*').in_('stock_id', inv_stock_ids).eq('date', today_str).execute()
            df_inv_market = pd.DataFrame(res.data)
            
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
    except Exception as e:
        print(f"❌ 庫存檢查失敗: {e}")

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
