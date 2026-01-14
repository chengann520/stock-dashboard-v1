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

# 3. 取得股票選單 (Cache 1hr)
@st.cache_data(ttl=3600)
def get_stock_options():
    try:
        # 讀取代號與名稱
        query = text("SELECT stock_id, company_name FROM dim_stock ORDER BY stock_id")
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
        
        display_list = []
        mapping = {}
        
        for _, row in df.iterrows():
            # 如果名稱跟代碼一樣，就只顯示代碼，否則顯示 代碼 | 名稱
            if row['stock_id'] == row['company_name']:
                display_name = f"🔍 {row['stock_id']}"
            else:
                display_name = f"📊 {row['stock_id']} | {row['company_name']}"
                
            display_list.append(display_name)
            mapping[display_name] = row['stock_id']
            
        return display_list, mapping
    except Exception as e:
        st.error(f"讀取清單失敗: {e}")
        return [], {}

# 4. 側邊欄設計
st.sidebar.header("🛠️ 監控控制台")

display_options, name_to_id_map = get_stock_options()

if display_options:
    selected_display = st.sidebar.selectbox(
        '請輸入代碼或選擇股票：',
        display_options,
        help="支援搜尋功能，直接輸入代碼即可快速篩選"
    )
    symbol = name_to_id_map[selected_display]
else:
    st.sidebar.warning("⚠️ 資料庫中無股票清單")
    symbol = None

st.sidebar.markdown("---")
if st.sidebar.button("🔄 強制清空快取 & 更新"):
    st.cache_data.clear()
    st.rerun()

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
            SELECT signal, probability, date 
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
        
        # 🤖 顯示 AI 訊號
        ai_data = get_ai_signal(symbol)
        if ai_data:
            ai_signal = ai_data[0] # Bull or Bear
            prob = float(ai_data[1])
            ai_date = ai_data[2]
            
            if ai_signal == "Bull":
                display_text = f"🐂 看多 ({prob:.0%})"
            else:
                display_text = f"🐻 看空 ({prob:.0%})"
            
            c4.metric("AI 預測", display_text, f"更新: {ai_date}")
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

        # 🟢 新增：法人買賣超 (Bar Chart)
        if 'foreign_net' in df.columns and symbol and (".TW" in symbol or ".TWO" in symbol):
            st.subheader("🏦 三大法人買賣超 (單位: 股)")
            
            chip_fig = go.Figure()
            
            # 判斷是否有數據 (避免全 0 的狀況顯示得很空)
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
                    barmode='group', # 分組顯示 (並排)
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
