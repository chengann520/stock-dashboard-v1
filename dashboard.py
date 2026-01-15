import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import random
from dotenv import load_dotenv
from page_paper_trade import show_ai_trading_page
from page_strategy_settings import show_strategy_settings_page, load_config

# 0. 載入環境變數 (本地測試用)
load_dotenv()

# 1. 頁面設定 (Premium Look)
st.set_page_config(
    page_title="Global Market Pulse | 全球股市戰情室",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 🟢 初始化 Session State (如果沒有設定過，預設為台積電)
if 'selected_stock_id' not in st.session_state:
    st.session_state['selected_stock_id'] = '2330.TW'

# 自定義 CSS 提升質感
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .metric-container {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .stMetric {
        background: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

# 2. 連線設定
db_url = st.secrets.get("DATABASE_URL") or os.getenv("DATABASE_URL")
if not db_url:
    st.error("❌ 未設定 DATABASE_URL，請檢查 Secrets 或是 .env 檔案。")
    st.stop()

engine = create_engine(db_url)

# --- 2.5 載入策略設定 ---
strategy_config = load_config()

# --- 3. 模擬交易引擎與參數 ---
INITIAL_CAPITAL = 1_000_000  # 初始資金 100萬
FEE_RATE = 0.001425          # 手續費 0.1425%
TAX_RATE = 0.003             # 交易稅 0.3% (僅賣出收)

def get_mock_ai_signal(date, stock_id, current_price):
    """模擬 AI 訊號 (用於回測展示)"""
    action = random.choices(['buy', 'sell', 'hold'], weights=[0.1, 0.1, 0.8])[0]
    target_price = current_price * random.uniform(0.98, 1.02)
    return action, round(target_price, 2)

class BacktestEngine:
    def __init__(self, capital):
        self.cash = capital
        self.inventory = {}  # 持倉: {stock_id: shares}
        self.history = []    # 交易紀錄
        self.daily_assets = [] # 每日資產總值紀錄
        
        # 從資料庫同步設定
        self.max_trade_budget = float(strategy_config.get('max_position_size', 100000))
        self.stop_loss_pct = float(strategy_config.get('stop_loss_pct', 0.05))

    def calculate_cost(self, price, shares):
        amount = price * shares
        fee = int(amount * FEE_RATE)
        fee = max(20, fee)
        return int(amount + fee), fee

    def calculate_revenue(self, price, shares):
        amount = price * shares
        fee = int(amount * FEE_RATE)
        fee = max(20, fee)
        tax = int(amount * TAX_RATE)
        return int(amount - fee - tax), fee, tax

    def run(self, df_market_data):
        """
        df_market_data 必須包含: date, stock_id, open, high, low, close
        """
        df_market_data = df_market_data.sort_values('date')
        dates = df_market_data['date'].unique()

        for d in dates:
            daily_data = df_market_data[df_market_data['date'] == d]
            if daily_data.empty: continue
            
            pending_orders = []
            for index, row in daily_data.iterrows():
                stock = row['stock_id']
                ref_price = row['open'] 
                action, limit_price = get_mock_ai_signal(d, stock, ref_price)
                
                if action == 'buy' and self.cash > 0:
                    # 根據設定決定買入股數 (預算 / 市價)
                    shares = int(self.max_trade_budget // limit_price)
                    if shares > 0:
                        cost_estimate, _ = self.calculate_cost(limit_price, shares)
                        if self.cash >= cost_estimate:
                            pending_orders.append({
                                'action': 'buy', 'stock': stock, 
                                'price': limit_price, 'shares': shares, 'date': d
                            })
                elif action == 'sell' and stock in self.inventory:
                    shares = self.inventory[stock]
                    pending_orders.append({
                        'action': 'sell', 'stock': stock, 
                        'price': limit_price, 'shares': shares, 'date': d
                    })

            for order in pending_orders:
                stock_rows = daily_data[daily_data['stock_id'] == order['stock']]
                if stock_rows.empty: continue
                row = stock_rows.iloc[0]
                
                if order['action'] == 'buy':
                    if row['low'] <= order['price']:
                        cost, fee = self.calculate_cost(order['price'], order['shares'])
                        if self.cash >= cost:
                            self.cash -= cost
                            self.inventory[order['stock']] = self.inventory.get(order['stock'], 0) + order['shares']
                            self.history.append({
                                '交易日期': order['date'],
                                '股票代號': order['stock'],
                                '買賣別': '買入',
                                '成交價': order['price'],
                                '股數': order['shares'],
                                '手續費': fee,
                                '交易稅': 0,
                                '總金額': -cost
                            })
                elif order['action'] == 'sell':
                    if row['high'] >= order['price']:
                        revenue, fee, tax = self.calculate_revenue(order['price'], order['shares'])
                        self.cash += revenue
                        del self.inventory[order['stock']]
                        self.history.append({
                            '交易日期': order['date'],
                            '股票代號': order['stock'],
                            '買賣別': '賣出',
                            '成交價': order['price'],
                            '股數': order['shares'],
                            '手續費': fee,
                            '交易稅': tax,
                            '總金額': revenue
                        })

            stock_value = 0
            for stock, shares in self.inventory.items():
                stock_rows = daily_data[daily_data['stock_id'] == stock]
                close_price = stock_rows['close'].values[0] if not stock_rows.empty else 0
                stock_value += (close_price * shares)
            
            total_asset = self.cash + stock_value
            self.daily_assets.append({'date': d, 'total_asset': total_asset, 'cash': self.cash, 'stock_value': stock_value})

            # --- 增加：出場檢查 (停損) ---
            if self.inventory:
                to_remove = []
                for stock, shares in self.inventory.items():
                    stock_rows = daily_data[daily_data['stock_id'] == stock]
                    if not stock_rows.empty:
                        curr_p = float(stock_rows.iloc[0]['close'])
                        # 查找買入價格 (簡化版：拿歷史最後一筆買入價)
                        buy_price = [h['成交價'] for h in self.history if h['股票代號'] == stock and h['買賣別'] == '買入'][-1]
                        if (curr_p - buy_price) / buy_price <= -self.stop_loss_pct:
                            revenue, fee, tax = self.calculate_revenue(curr_p, shares)
                            self.cash += revenue
                            self.history.append({
                                '交易日期': d, '股票代號': stock, '買賣別': '賣出',
                                '成交價': curr_p, '股數': shares, '手續費': fee, '交易稅': tax, '總金額': revenue,
                                '備註': '🛑 停損觸發'
                            })
                            to_remove.append(stock)
                for s in to_remove: del self.inventory[s]

        return pd.DataFrame(self.history), pd.DataFrame(self.daily_assets)

# 🟢 改寫：通知函式 (只回傳資料，不負責畫圖)
def get_ai_notifications():
    """從資料庫抓取今日高信心的看漲訊號"""
    try:
        # 1. 找出最新日期
        date_query = text("SELECT MAX(date) FROM ai_analysis")
        with engine.connect() as conn:
            latest_date = conn.execute(date_query).scalar()
            
        if not latest_date:
            return pd.DataFrame() # 沒資料回傳空表

        # 2. 抓取真實資料 (看漲 + 信心 > 70%)
        query = text("""
            SELECT a.stock_id, s.company_name, a.probability 
            FROM ai_analysis a
            JOIN dim_stock s ON a.stock_id = s.stock_id
            WHERE a.date = :date 
              AND a.signal = 'Bull' 
              AND a.probability >= 0.7
            ORDER BY a.probability DESC
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"date": latest_date})
            
        return df
            
    except Exception as e:
        st.error(f"資料讀取錯誤: {e}")
        return pd.DataFrame()

# --- 頁面主佈局開始 ---

# 1. 建立頂部兩欄佈局 (左邊標題，右邊通知)
col_header, col_notify = st.columns([7, 3]) # 左7右3的比例

# --- 顯示當前策略概覽 (核心戰術對齊) ---
if strategy_config:
    with col_header:
        s_strat = strategy_config.get('active_strategy', 'N/A')
        s_risk = strategy_config.get('risk_preference', 'N/A')
        s_budget = strategy_config.get('max_position_size', 0)
        s_stop = strategy_config.get('stop_loss_pct', 0)
        
        st.info(f"🧠 **AI 核心戰術**：`{s_strat}` | **風險偏好**：`{s_risk}` | **單筆預算**：`${s_budget:,.0f}` | **停損設定**：`{s_stop*100:.1f}%`", icon="💡")

with col_header:
    st.title("� 台股戰情室")

with col_notify:
    # 2. 取得真實通知資料
    df_notify = get_ai_notifications()
    
    if not df_notify.empty:
        # 顯示一個漂亮的通知框 (Expander)
        with st.expander(f"� AI 發現 {len(df_notify)} 檔飆股！", expanded=True):
            for _, row in df_notify.iterrows():
                # 按鈕標籤
                btn_label = f"🚀 {row['probability']:.0%} | {row['stock_id']}"
                if row['company_name'] and row['company_name'] != row['stock_id']:
                    btn_label += f" {row['company_name']}"
                
                # 點擊按鈕切換股票
                if st.button(btn_label, key=f"top_btn_{row['stock_id']}"):
                    st.session_state['selected_stock_id'] = row['stock_id']
                    st.rerun()
    else:
        st.info("🍵 今日 AI 無特別訊號")

st.markdown("---")

# 3. 取得股票選單 (Cache 1hr)
@st.cache_data(ttl=3600)
def get_stock_options():
    try:
        query = text("SELECT stock_id, company_name FROM dim_stock ORDER BY stock_id")
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
        
        ids = []
        display_names = []
        
        for _, row in df.iterrows():
            if row['stock_id'] == row['company_name']:
                d_name = f"{row['stock_id']}"
            else:
                d_name = f"{row['stock_id']} | {row['company_name']}"
                
            ids.append(row['stock_id'])
            display_names.append(d_name)
            
        return ids, display_names
    except Exception as e:
        st.error(f"讀取清單失敗: {e}")
        return [], []

# 4. 側邊欄邏輯
st.sidebar.header("🛠️ 監控控制台")

# 🟢 A. 建立導覽選單
menu = st.sidebar.radio(
    "功能導航",
    ["📊 市場數據分析", "🤖 AI 模擬操盤室", "⚙️ 策略參數設定"],
    help="切換即時數據分析、AI 實戰模擬與策略參數設定"
)

st.sidebar.markdown("---")

if menu == "📊 市場數據分析":
    # 🟢 B. 取得清單並決定下拉選單位置
    stock_ids, display_names = get_stock_options()

    if stock_ids:
        try:
            current_index = stock_ids.index(st.session_state['selected_stock_id'])
        except ValueError:
            current_index = 0

        selected_display = st.sidebar.selectbox(
            '請輸入代碼或選擇股票：',
            display_names,
            index=current_index,
            help="支援搜尋功能，直接輸入代碼即可快速篩選"
        )
        
        # 從顯示名稱取出代碼
        selected_symbol_from_box = selected_display.split(" | ")[0]

        # 🟢 C. 如果選單變動，更新 Session State 並重整
        if selected_symbol_from_box != st.session_state['selected_stock_id']:
            st.session_state['selected_stock_id'] = selected_symbol_from_box
            st.rerun()
            
        symbol = st.session_state['selected_stock_id']
    else:
        st.sidebar.warning("⚠️ 資料庫中無股票清單")
        symbol = None
else:
    symbol = None

st.sidebar.markdown("---")
if st.sidebar.button("🔄 強制清空快取 & 更新"):
    st.cache_data.clear()
    st.rerun()

# 📊 AI 戰績統計
st.sidebar.markdown("---")
st.sidebar.header("📊 AI 戰績統計")

def get_ai_accuracy():
    try:
        with engine.connect() as conn:
            # 計算總準確率
            sql = text("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as wins
                FROM ai_analysis
                WHERE is_correct IS NOT NULL
            """)
            result = conn.execute(sql).fetchone()
            
            if result and result[0] > 0:
                return float(result[1]) / float(result[0])
            return 0
    except Exception:
        return 0

acc = get_ai_accuracy()
st.sidebar.metric("歷史預測準確率 (Win Rate)", f"{acc:.1%}")

if acc > 0.6:
    st.sidebar.success("模型表現優異！🚀")
elif acc > 0.5:
    st.sidebar.warning("模型表現尚可 😐")
elif acc > 0:
    st.sidebar.error("模型需要再訓練 📉")
else:
    st.sidebar.info("尚未有足夠驗證資料 ⏳")

# 5. 數據載入 (Cache 10min)
@st.cache_data(ttl=600)
def load_data(stock_symbol):
    if not stock_symbol:
        return pd.DataFrame()

    try:
        query = text("SELECT * FROM fact_price WHERE stock_id = :symbol ORDER BY date ASC")
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"symbol": stock_symbol})
        
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"資料庫讀取失敗: {e}")
        return pd.DataFrame()

def get_ai_signal(stock_symbol):
    """讀取最新的 AI 預測"""
    try:
        query = text("""
            SELECT signal, probability, date, entry_price, target_price, stop_loss
            FROM ai_analysis 
            WHERE stock_id = :symbol 
            ORDER BY date DESC LIMIT 1
        """)
        with engine.connect() as conn:
            result = conn.execute(query, {"symbol": stock_symbol}).fetchone()
        return result
    except Exception:
        return None

# 6. 主要顯示邏輯
if symbol:
    df = load_data(symbol)

    if not df.empty:
        # 使用 Tabs 分隔即時分析與模擬交易
        tab_analysis, tab_simulation = st.tabs(["📈 即時分析", "🤖 AI 模擬交易"])

        with tab_analysis:
            # A. 數據摘要區
            last_row = df.iloc[-1]
            prev_row = df.iloc[-2] if len(df) > 1 else last_row
            
            # 判斷欄位名稱
            close_col = 'close' if 'close' in df.columns else 'close_price'
            ma5_col = 'ma_5' if 'ma_5' in df.columns else 'ma5' if 'ma5' in df.columns else None
            vol_col = 'volume'
            
            # 計算漲跌
            change = last_row[close_col] - prev_row[close_col]
            pct_change = (change / prev_row[close_col] * 100) if prev_row[close_col] != 0 else 0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("當前價格", f"{last_row[close_col]:.2f}", f"{change:+.2f} ({pct_change:+.2f}%)")
            
            ma5_val = f"{last_row[ma5_col]:.2f}" if ma5_col and pd.notnull(last_row[ma5_col]) else "N/A"
            c2.metric("MA 5 均線", ma5_val)
            
            vol_val = f"{int(last_row[vol_col]):,}" if vol_col in df.columns else "N/A"
            c3.metric("今日成交量", vol_val)
            
            # 🤖 顯示 AI 預測與策略建議
            ai_data = get_ai_signal(symbol)
            if ai_data:
                ai_signal = ai_data[0] # Bull or Bear
                prob = float(ai_data[1])
                ai_date = ai_data[2]
                entry_p = float(ai_data[3]) if ai_data[3] else 0
                target_p = float(ai_data[4]) if ai_data[4] else 0
                stop_p = float(ai_data[5]) if ai_data[5] else 0
                
                st.markdown("---")
                st.markdown("### 🤖 AI 策略建議")
                
                if ai_signal == "Bull":
                    st.success(f"🔥 強力看多 (信心度: {prob:.0%})")
                else:
                    st.warning(f"❄️ 趨勢看空 (信心度: {prob:.0%})")
                    
                if entry_p > 0:
                    c1pre, c2pre, c3pre = st.columns(3)
                    c1pre.metric("💰 建議入手價", f"{entry_p:.2f}")
                    c2pre.metric("🎯 目標獲利價", f"{target_p:.2f}", delta=f"{(target_p-entry_p):.2f}")
                    c3pre.metric("🛑 停損價格", f"{stop_p:.2f}")
                
                st.caption(f"數據更新時間: {ai_date} (價格基於 ATR 波動率計算)")
            else:
                c4.metric("AI 預測", "⏳ 計算中...")

            # B. 走勢圖表
            st.subheader(f"📈 {symbol} 價量趨勢分析")
            
            fig = go.Figure()
            
            # 蠟燭圖
            fig.add_trace(go.Candlestick(
                x=df['date'],
                open=df.get('open', df.get('open_price')),
                high=df.get('high', df.get('high_price')),
                low=df.get('low', df.get('low_price')),
                close=df.get(close_col),
                name='K線'
            ))

            # 均線
            if ma5_col:
                ma5_line = df[df[ma5_col].notna()]
                fig.add_trace(go.Scatter(x=ma5_line['date'], y=ma5_line[ma5_col], line=dict(color='#FFA500', width=1.5), name='MA 5'))
            
            ma20_col = 'ma_20' if 'ma_20' in df.columns else 'ma20' if 'ma20' in df.columns else None
            if ma20_col:
                ma20_line = df[df[ma20_col].notna()]
                fig.add_trace(go.Scatter(x=ma20_line['date'], y=ma20_line[ma20_col], line=dict(color='#1E90FF', width=1.5), name='MA 20'))

            fig.update_layout(
                template='plotly_white',
                xaxis_rangeslider_visible=False,
                height=600,
                margin=dict(l=20, r=20, t=50, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True)

            # 🟢 法人買賣超 (Bar Chart)
            if 'foreign_net' in df.columns and symbol and (".TW" in symbol or ".TWO" in symbol):
                st.subheader("🏦 三大法人買賣超 (單位: 股)")
                
                chip_fig = go.Figure()
                has_chip_data = (df['foreign_net'].abs().sum() + df['trust_net'].abs().sum() + df['dealer_net'].abs().sum()) > 0
                
                if has_chip_data:
                    chip_fig.add_trace(go.Bar(
                        x=df['date'], y=df['foreign_net'], name='外資', marker_color='purple'
                    ))
                    chip_fig.add_trace(go.Bar(
                        x=df['date'], y=df['trust_net'], name='投信', marker_color='red'
                    ))
                    chip_fig.add_trace(go.Bar(
                        x=df['date'], y=df['dealer_net'], name='自營商', marker_color='gray'
                    ))

                    chip_fig.update_layout(
                        template='plotly_white',
                        barmode='group',
                        xaxis_title="日期",
                        yaxis_title="買賣超股數",
                        height=400,
                        margin=dict(l=20, r=20, t=30, b=20),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(chip_fig, use_container_width=True)
                else:
                    st.info("💡 目前尚無籌碼數據 (三大法人資料通常在 15:00 ~ 16:30 更新)")

            # C. 詳細數據區
            with st.expander("📊 查看歷史數據明細"):
                st.dataframe(df.sort_values('date', ascending=False), use_container_width=True)

        with tab_simulation:
            st.subheader("🤖 AI 投資模擬實驗室")
            st.markdown(f"### 初始資金: NT$ {INITIAL_CAPITAL:,.0f} | 交易策略: 限價單 (Limit Order)")
            
            if st.button('開始回測 / 重新模擬'):
                engine_bt = BacktestEngine(INITIAL_CAPITAL)
                
                with st.spinner('AI 正在穿越時空進行交易...'):
                    # 確保資料包含 stock_id
                    sim_df = df.copy()
                    sim_df['stock_id'] = symbol
                    trade_log, asset_log = engine_bt.run(sim_df)
                
                st.success("回測完成！")

                # --- 區塊 1: 總資產概況 (Metrics) ---
                if not asset_log.empty:
                    final_asset = asset_log.iloc[-1]['total_asset']
                    roi = ((final_asset - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("最終總資產", f"${final_asset:,.0f}")
                    col2.metric("投資報酬率 (ROI)", f"{roi:.2f}%", delta=f"{roi:.2f}%")
                    col3.metric("總交易次數", f"{len(trade_log)} 筆")

                    st.divider()

                    # --- 區塊 2: 折線圖 (總資產價值變化) ---
                    st.subheader("📈 總資產價值趨勢")
                    fig_line = px.line(asset_log, x='date', y='total_asset', title='資產淨值 (NAV) 走勢')
                    fig_line.add_hline(y=INITIAL_CAPITAL, line_dash="dash", line_color="gray", annotation_text="本金")
                    st.plotly_chart(fig_line, use_container_width=True)

                    # --- 區塊 3: 圓餅圖 (資金分配 - 取最後一天狀態) ---
                    st.subheader("🍰 最終資金分配")
                    last_day = asset_log.iloc[-1]
                    allocation_data = pd.DataFrame({
                        'Type': ['現金 (Cash)', '股票市值 (Stock)'],
                        'Value': [last_day['cash'], last_day['stock_value']]
                    })
                    fig_pie = px.pie(allocation_data, values='Value', names='Type', hole=0.4, 
                                     color_discrete_sequence=['#00CC96', '#EF553B'])
                    st.plotly_chart(fig_pie, use_container_width=True)

                    # --- 區塊 4: 交易明細列表 ---
                    st.subheader("📝 交易明細")
                    if not trade_log.empty:
                        display_log = trade_log.copy()
                        display_log['總金額'] = display_log['總金額'].apply(lambda x: f"{x:,.0f}")
                        display_log['成交價'] = display_log['成交價'].apply(lambda x: f"{x:.2f}")
                        
                        def highlight_buy_sell(val):
                            color = 'red' if val == '買入' else 'green'
                            return f'color: {color}'

                        st.dataframe(
                            display_log.style.applymap(highlight_buy_sell, subset=['買賣別']),
                            use_container_width=True
                        )
                    else:
                        st.info("這段期間 AI 選擇按兵不動，沒有進行任何交易。")
                else:
                    st.warning("無足夠數據進行模擬。")

    else:
        st.warning(f"🤔 找不到 {symbol} 的股價數據。")
        st.info("請確認 ETL 程式 (`main.py`) 是否已成功將資料寫入資料表 `fact_price`。")
elif menu == "🤖 AI 模擬操盤室":
    show_ai_trading_page()
elif menu == "⚙️ 策略參數設定":
    show_strategy_settings_page()
else:
    st.info("👈 請在左側選單選擇一支股票開始分析。")

# 頁尾
st.markdown("---")
st.caption(f"最後更新時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data powered by Yahoo Finance")
