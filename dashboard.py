import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
import plotly.graph_objects as go

# 1. 設定頁面標題
st.set_page_config(page_title="Market Pulse 監控儀表板", layout="wide")
st.title("📈 Market Pulse 自動化數據監控")

# 2. 連線資料庫 (使用 Streamlit 的 Secrets 管理密碼，稍後教你設)
# 為了方便你現在本機測試，我們先用 os.getenv，之後部署上雲端再改
db_url = os.getenv("DATABASE_URL") 

# 如果在 Streamlit Cloud 上，密碼會藏在 st.secrets 裡
if not db_url and "DATABASE_URL" in st.secrets:
    db_url = st.secrets["DATABASE_URL"]

@st.cache_data(ttl=600) # 快取 10 分鐘，避免一直連資料庫
def load_data(symbol):
    if not db_url:
        st.error("找不到資料庫連線字串！")
        return pd.DataFrame()
    
    engine = create_engine(db_url)
    query = text(f"""
        SELECT date, open, high, low, close, ma_5, ma_20, volume
        FROM fact_price
        WHERE stock_id = :symbol
        ORDER BY date ASC
    """)
    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"symbol": symbol})
    
    return df

# 3. 側邊欄：選擇股票
option = st.sidebar.selectbox(
    '選擇要查看的股票：',
    ('2330.TW', '0050.TW', 'TSLA', 'AAPL')
)

# 4. 載入資料
st.write(f"正在從雲端資料庫讀取 {option} 的數據...")
df = load_data(option)

if not df.empty:
    # 5. 畫圖 (使用 Plotly 畫互動式 K 線圖)
    fig = go.Figure(data=[go.Candlestick(x=df['date'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='K線'),
                go.Scatter(x=df['date'], y=df['ma_5'], line=dict(color='orange', width=1), name='MA 5'),
                go.Scatter(x=df['date'], y=df['ma_20'], line=dict(color='blue', width=1), name='MA 20')
                ])

    fig.update_layout(title=f"{option} 股價走勢圖", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    # 顯示最新數據
    last_row = df.iloc[-1]
    col1, col2, col3 = st.columns(3)
    col1.metric("最新收盤價", f"{last_row['close']:.2f}")
    col2.metric("MA 5", f"{last_row['ma_5']:.2f}")
    col3.metric("成交量", f"{int(last_row['volume']):,}")

    # 顯示原始資料表 (可折疊)
    with st.expander("查看詳細數據表"):
        st.dataframe(df.sort_values('date', ascending=False))

else:
    st.warning("資料庫裡還沒有這支股票的資料，請檢查 ETL Pipeline 是否成功執行。")
