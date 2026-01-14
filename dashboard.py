import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
import plotly.graph_objects as go

# 1. 頁面設定
st.set_page_config(page_title="Stock Dashboard", layout="wide")
st.title("📈 股票數據儀表板")

# 2. 取得資料庫連線
db_url = st.secrets.get("DATABASE_URL")
if not db_url:
    # 本機測試用
    db_url = os.getenv("DATABASE_URL")

# 3. 清除快取按鈕 (這對除錯很有用)
if st.sidebar.button("🔄 強制重新整理資料"):
    st.cache_data.clear()

@st.cache_data(ttl=600)
def load_data(symbol):
    if not db_url:
        return pd.DataFrame()

    try:
        engine = create_engine(db_url)
        # 🟢 關鍵修正：使用 SELECT * 避免欄位錯誤
        query = text("SELECT * FROM fact_price WHERE stock_id = :symbol ORDER BY date ASC")
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"symbol": symbol})
        
        # 欄位轉小寫 (標準化)
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"資料庫讀取失敗: {e}")
        return pd.DataFrame()

# 4. 選擇股票
option = st.sidebar.selectbox('選擇股票：', ('2330.TW', '0050.TW', 'TSLA', 'AAPL'))

if db_url:
    st.write(f"正在讀取 {option}...")
    df = load_data(option)

    if not df.empty:
        # 5. 畫圖
        fig = go.Figure(data=[go.Candlestick(x=df['date'],
                    open=df['open'], high=df['high'],
                    low=df['low'], close=df['close'],
                    name='K線')])

        # 🟢 動態檢查：只有欄位真的存在且有值時才畫線
        if 'ma_5' in df.columns:
            # 過濾掉 NULL 值以免線條斷掉
            ma5_data = df[df['ma_5'].notna()]
            if not ma5_data.empty:
                fig.add_trace(go.Scatter(x=ma5_data['date'], y=ma5_data['ma_5'], 
                                       line=dict(color='orange', width=1), name='MA 5'))
        
        if 'ma_20' in df.columns:
            ma20_data = df[df['ma_20'].notna()]
            if not ma20_data.empty:
                fig.add_trace(go.Scatter(x=ma20_data['date'], y=ma20_data['ma_20'], 
                                       line=dict(color='blue', width=1), name='MA 20'))

        fig.update_layout(title=f"{option} 走勢圖", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        
        # 數據表
        with st.expander("查看詳細數據"):
            st.dataframe(df.sort_values('date', ascending=False))
    else:
        st.warning("查無資料，請確認資料庫是否已寫入數據。")
else:
    st.error("尚未設定 DATABASE_URL Secrets。")
