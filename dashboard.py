import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
import plotly.graph_objects as go
from dotenv import load_dotenv

# 0. 載入環境變數 (本地測試用)
load_dotenv()

# 1. 設定頁面
st.set_page_config(page_title="Market Pulse 監控儀表板", layout="wide")
st.title("📈 Market Pulse 自動化數據監控")

# 2. 取得資料庫連線
# 優先從 Streamlit Secrets 讀取，如果沒有則讀取系統變數 (本機測試用)
db_url = st.secrets.get("DATABASE_URL") or os.getenv("DATABASE_URL")

@st.cache_data(ttl=600)
def load_data(symbol):
    if not db_url:
        st.error("❌ 找不到資料庫連線字串 (DATABASE_URL)！請檢查 Secrets 設定。")
        return pd.DataFrame()

    try:
        engine = create_engine(db_url)
        # 關鍵修改：改用 SELECT *，避免因為缺少 MA 欄位導致程式崩潰
        query = text("""
            SELECT *
            FROM fact_price
            WHERE stock_id = :symbol
            ORDER BY date ASC
        """)
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"symbol": symbol})
        
        return df
    except Exception as e:
        st.error(f"資料庫讀取失敗: {e}")
        return pd.DataFrame()

# 3. 側邊欄與資料讀取
option = st.sidebar.selectbox('選擇股票：', ('2330.TW', '0050.TW', 'TSLA', 'AAPL'))

if db_url:
    st.write(f"正在讀取 {option} 數據...")
    df = load_data(option)

    if not df.empty:
        # 4. 畫圖 (動態檢查欄位)
        # 注意：這裡假設資料庫裡的欄位名稱與 yfinance 抓取時一致 (open, high, low, close)
        # 如果你的資料庫欄位是 open_price，請自行調整
        fig = go.Figure(data=[go.Candlestick(x=df['date'],
                    open=df.get('open', df.get('open_price')),
                    high=df.get('high', df.get('high_price')),
                    low=df.get('low', df.get('low_price')),
                    close=df.get('close', df.get('close_price')),
                    name='K線')])

        # 只有當資料庫裡真的有 ma_5 或 ma5 欄位時，才畫這條線
        ma5_col = 'ma_5' if 'ma_5' in df.columns else 'ma5' if 'ma5' in df.columns else None
        if ma5_col:
            fig.add_trace(go.Scatter(x=df['date'], y=df[ma5_col], line=dict(color='orange', width=1), name='MA 5'))
        
        ma20_col = 'ma_20' if 'ma_20' in df.columns else 'ma20' if 'ma20' in df.columns else None
        if ma20_col:
            fig.add_trace(go.Scatter(x=df['date'], y=df[ma20_col], line=dict(color='blue', width=1), name='MA 20'))

        fig.update_layout(title=f"{option} 股價走勢", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

        # 顯示最新數據
        last_row = df.iloc[-1]
        col1, col2, col3 = st.columns(3)
        
        close_col = 'close' if 'close' in df.columns else 'close_price' if 'close_price' in df.columns else None
        close_val = f"{last_row[close_col]:.2f}" if close_col else "N/A"
        col1.metric("收盤價", close_val)
        
        # 安全地讀取 MA，如果沒有則顯示 N/A
        ma5_val = f"{last_row[ma5_col]:.2f}" if ma5_col and pd.notnull(last_row[ma5_col]) else "N/A"
        vol_val = f"{int(last_row['volume']):,}" if 'volume' in df.columns else "N/A"
        
        col2.metric("MA 5", ma5_val)
        col3.metric("成交量", vol_val)

        with st.expander("查看詳細數據表"):
            st.dataframe(df.sort_values('date', ascending=False))
            
        # 顯示目前的欄位 (除錯用)
        # st.write("目前資料庫有的欄位:", df.columns.tolist())

    else:
        st.warning("查無資料，請確認資料庫是否已有寫入數據。")
else:
    st.warning("尚未設定資料庫連線。")
