import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
import plotly.graph_objects as go
from datetime import datetime
from dotenv import load_dotenv

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

st.title("🛡️ 全球精選標的監控儀表板 (Top 200)")
st.markdown("---")

# 2. 連線設定
db_url = st.secrets.get("DATABASE_URL") or os.getenv("DATABASE_URL")
if not db_url:
    st.error("❌ 未設定 DATABASE_URL，請檢查 Secrets 或是 .env 檔案。")
    st.stop()

engine = create_engine(db_url)

# 🟢 新增：檢查通知函式 (點擊按鈕更新 Session State)
def check_notifications():
    """
    檢查資料庫中，是否有「最新日期」且「高信心看漲」的訊號
    """
    try:
        # 1. 找出資料庫裡最新的日期
        date_query = text("SELECT MAX(date) FROM ai_analysis")
        with engine.connect() as conn:
            latest_date = conn.execute(date_query).scalar()
            
        if not latest_date:
            return

        # 2. 抓取該日期所有「看漲 (Bull)」且「信心 >= 70%」的股票
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
            df_notify = pd.read_sql(query, conn, params={"date": latest_date})

        # 3. 顯示通知
        if not df_notify.empty:
            st.toast(f"🔔 AI 發現 {len(df_notify)} 檔潛力股！", icon="🚀")
            
            st.sidebar.header("🔥 今日 AI 精選")
            for _, row in df_notify.iterrows():
                # 按鈕文字
                btn_label = f"🚀 {row['probability']:.0%} | {row['stock_id']}"
                if row['company_name'] and row['company_name'] != row['stock_id']:
                    btn_label += f" {row['company_name']}"
                
                # 如果使用者點擊了這個按鈕
                if st.sidebar.button(btn_label, key=f"btn_{row['stock_id']}"):
                    st.session_state['selected_stock_id'] = row['stock_id']
                    st.rerun()
            
            st.sidebar.markdown("---")
            
    except Exception as e:
        st.error(f"通知系統錯誤: {e}")

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

# 🟢 A. 顯示 AI 通知按鈕 (會更新 session_state)
check_notifications()

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
            
    else:
        st.warning(f"🤔 找不到 {symbol} 的股價數據。")
        st.info("請確認 ETL 程式 (`main.py`) 是否已成功將資料寫入資料表 `fact_price`。")
else:
    st.info("👈 請在左側選單選擇一支股票開始分析。")

# 頁尾
st.markdown("---")
st.caption(f"最後更新時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data powered by Yahoo Finance")
