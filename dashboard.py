import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
import plotly.graph_objects as go
from dotenv import load_dotenv

# 0. 載入環境變數 (本地測試用)
load_dotenv()

# 1. 頁面設定
st.set_page_config(page_title="台股戰情室", layout="wide")
st.title("📈 台灣百大權值股監控")

# 2. 連線設定
db_url = st.secrets.get("DATABASE_URL") or os.getenv("DATABASE_URL")
if not db_url:
    st.error("❌ 未設定 DATABASE_URL")
    st.stop()

engine = create_engine(db_url)

# 3. 取得股票選單
@st.cache_data(ttl=3600)  # 快取 1 小時
def get_stock_options():
    try:
        # 注意：這裡使用 stock_name 以符合 schema.sql
        query = text("SELECT stock_id, stock_name FROM dim_stock ORDER BY stock_id")
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
        
        display_list = []
        mapping = {}
        
        for _, row in df.iterrows():
            display_name = f"{row['stock_id']} | {row['stock_name']}"
            display_list.append(display_name)
            mapping[display_name] = row['stock_id']
            
        return display_list, mapping
    except Exception as e:
        st.error(f"讀取清單失敗: {e}")
        return [], {}

# 4. 側邊欄與清除快取
display_options, name_to_id_map = get_stock_options()

if st.sidebar.button("🔄 強制重新整理資料"):
    st.cache_data.clear()
    st.rerun()

if display_options:
    selected_display = st.sidebar.selectbox('🔍 選擇股票：', display_options)
    symbol = name_to_id_map[selected_display]
else:
    st.sidebar.warning("資料庫無股票清單")
    symbol = None

# 5. 數據載入函式 (防呆版)
@st.cache_data(ttl=600)
def load_data(stock_symbol):
    if not stock_symbol:
        return pd.DataFrame()

    try:
        # 使用 SELECT * 避免欄位變動導致報錯
        query = text("SELECT * FROM fact_price WHERE stock_id = :symbol ORDER BY date ASC")
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"symbol": stock_symbol})
        
        # 欄位標準化 (轉小寫)
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"資料庫讀取失敗: {e}")
        return pd.DataFrame()

# 6. 核心顯示邏輯
if symbol:
    st.write(f"正在讀取 {symbol} 數據...")
    df = load_data(symbol)

    if not df.empty:
        # 畫圖 (動態檢查欄位)
        fig = go.Figure(data=[go.Candlestick(x=df['date'],
                    open=df.get('open', df.get('open_price')),
                    high=df.get('high', df.get('high_price')),
                    low=df.get('low', df.get('low_price')),
                    close=df.get('close', df.get('close_price')),
                    name='K線')])

        # 檢查 MA 欄位 (相容 ma_5 與 ma5)
        ma5_col = 'ma_5' if 'ma_5' in df.columns else 'ma5' if 'ma5' in df.columns else None
        if ma5_col:
            ma5_data = df[df[ma5_col].notna()]
            if not ma5_data.empty:
                fig.add_trace(go.Scatter(x=ma5_data['date'], y=ma5_data[ma5_col], line=dict(color='orange', width=1), name='MA 5'))
        
        ma20_col = 'ma_20' if 'ma_20' in df.columns else 'ma20' if 'ma20' in df.columns else None
        if ma20_col:
            ma20_data = df[df[ma20_col].notna()]
            if not ma20_data.empty:
                fig.add_trace(go.Scatter(x=ma20_data['date'], y=ma20_data[ma20_col], line=dict(color='blue', width=1), name='MA 20'))

        fig.update_layout(title=f"{symbol} 股價走勢圖", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

        # 顯示最新數據與數據表
        last_row = df.iloc[-1]
        col1, col2, col3 = st.columns(3)
        
        close_col = 'close' if 'close' in df.columns else 'close_price' if 'close_price' in df.columns else None
        close_val = f"{last_row[close_col]:.2f}" if close_col else "N/A"
        col1.metric("收盤價", close_val)
        
        ma5_val = f"{last_row[ma5_col]:.2f}" if ma5_col and pd.notnull(last_row[ma5_col]) else "N/A"
        vol_val = f"{int(last_row['volume']):,}" if 'volume' in df.columns else "N/A"
        col2.metric("MA 5", ma5_val)
        col3.metric("成交量", vol_val)

        with st.expander("查看詳細數據"):
            st.dataframe(df.sort_values('date', ascending=False))
    else:
        st.warning(f"⚠️ {symbol} 尚無股價資料，請檢查 ETL Pipeline 是否已執行。")
else:
    st.info("💡 請從左側選單選擇股票。")
