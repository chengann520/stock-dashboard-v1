import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine
from config.settings import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME

# Set page config
st.set_page_config(page_title="Market Pulse Dashboard", layout="wide")

st.title("📈 Market Pulse Stock Dashboard")

@st.cache_resource
def get_engine():
    from config.settings import DATABASE_URL
    if DATABASE_URL:
        return create_engine(DATABASE_URL)
    conn_str = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(conn_str)

def load_data(stock_id):
    engine = get_engine()
    query = f"SELECT * FROM fact_price WHERE stock_id = '{stock_id}' ORDER BY date DESC LIMIT 200"
    df = pd.read_sql(query, engine)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    return df

def get_stock_list():
    engine = get_engine()
    query = "SELECT DISTINCT stock_id FROM fact_price"
    try:
        df = pd.read_sql(query, engine)
        return df['stock_id'].tolist()
    except Exception:
        return ["2330.TW", "2317.TW", "TSLA", "AAPL"] # Fallback

# Sidebar for selection
stocks = get_stock_list()
selected_stock = st.sidebar.selectbox("Select Ticker", stocks)

if selected_stock:
    df = load_data(selected_stock)
    
    if not df.empty:
        # Create Candlestick chart
        fig = go.Figure(data=[go.Candlestick(
            x=df['date'],
            open=df['open_price'],
            high=df['high_price'],
            low=df['low_price'],
            close=df['close_price'],
            name="Price"
        )])

        # Add MA lines
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma5'], name='MA5', line=dict(color='orange', width=1)))
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], name='MA20', line=dict(color='blue', width=1)))

        fig.update_layout(
            title=f"{selected_stock} Technical Chart",
            yaxis_title="Price",
            xaxis_title="Date",
            template="plotly_dark",
            height=600
        )

        st.plotly_chart(fig, use_container_width=True)

        # Show raw data
        with st.expander("View Raw Data"):
            st.dataframe(df)
    else:
        st.warning(f"No data found for {selected_stock} in the database. Please run the ETL pipeline first.")
else:
    st.info("Please select a stock ticker from the sidebar.")
