import streamlit as st
import pandas as pd
import plotly.express as px
import os
from supabase import create_client
from datetime import date, datetime

# --- 1. 連線設定 ---
SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")

# 初始化 Supabase
try:
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("❌ 未設定 SUPABASE_URL 或 SUPABASE_KEY")
        st.stop()
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"無法連線到資料庫，請檢查 API Key 設定: {e}")
    st.stop()

# --- 2. 資料讀取函數 ---

def get_account_summary():
    """取得帳戶餘額與庫存"""
    try:
        # 讀取現金
        acc_res = supabase.table('sim_account').select('*').eq('user_id', 'default_user').execute()
        cash = float(acc_res.data[0]['cash_balance']) if acc_res.data else 1000000
        
        # 讀取庫存
        inv_res = supabase.table('sim_inventory').select('*').execute()
        inventory_df = pd.DataFrame(inv_res.data)
        
        return cash, inventory_df
    except Exception as e:
        st.error(f"讀取帳戶摘要失敗: {e}")
        return 1000000, pd.DataFrame()

def get_pending_orders():
    """取得 AI 預測但尚未成交的掛單 (明日或今日盤中)"""
    try:
        res = supabase.table('sim_orders').select('*').eq('status', 'PENDING').order('date', desc=True).execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"讀取掛單失敗: {e}")
        return pd.DataFrame()

def get_transaction_history():
    """取得已成交的歷史紀錄"""
    try:
        res = supabase.table('sim_transactions').select('*').order('trade_date', desc=True).execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"讀取交易紀錄失敗: {e}")
        return pd.DataFrame()

def get_asset_curve():
    """取得每日總資產走勢"""
    try:
        res = supabase.table('sim_daily_assets').select('*').order('date').execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"讀取資產走勢失敗: {e}")
        return pd.DataFrame()

# --- 3. 頁面主程式 ---

def show_ai_trading_page():
    st.title("🚀 AI 實戰模擬操盤室")
    st.markdown("這裡顯示 AI 對未來的預測與實際交易成果 (基於 Supabase 資料庫)")

    # 重新整理按鈕
    if st.button("🔄 刷新即時數據"):
        st.cache_data.clear()
        st.rerun()

    # --- 區塊 A: 資產總覽 (Metrics) ---
    cash, df_inventory = get_account_summary()
    
    df_assets = get_asset_curve()
    
    if not df_assets.empty:
        latest_asset = df_assets.iloc[-1]
        total_asset_val = float(latest_asset['total_assets'])
        stock_val = float(latest_asset['stock_value'])
        last_update = latest_asset['date']
    else:
        total_asset_val = cash
        stock_val = 0
        last_update = str(date.today())

    initial_capital = 1_000_000
    roi = ((total_asset_val - initial_capital) / initial_capital) * 100
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 總資產淨值", f"${total_asset_val:,.0f}")
    col2.metric("💵 可用現金", f"${cash:,.0f}")
    col3.metric("📈 股票市值", f"${stock_val:,.0f}")
    col4.metric("🔥 累積報酬率 (ROI)", f"{roi:.2f}%", delta_color="normal")
    
    st.caption(f"數據最後更新日期: {last_update}")

    st.divider()

    # --- 區塊 B: 圖表分析 (Charts) ---
    tab1, tab2 = st.tabs(["📊 資產趨勢與配置", "🤖 AI 預測掛單"])

    with tab1:
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.subheader("資產成長曲線")
            if not df_assets.empty:
                fig_line = px.line(df_assets, x='date', y='total_assets', markers=True)
                fig_line.add_hline(y=initial_capital, line_dash="dash", line_color="gray", annotation_text="本金")
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.info("尚無資產紀錄，請等待第一個交易日結算。")

        with c2:
            st.subheader("資金配置")
            pie_data = pd.DataFrame({
                'Type': ['現金', '股票'],
                'Value': [cash, stock_val]
            })
            if stock_val > 0 or cash > 0:
                fig_pie = px.pie(pie_data, values='Value', names='Type', hole=0.4, 
                                 color_discrete_sequence=['#00CC96', '#EF553B'])
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.write("尚無資料")

    with tab2:
        st.subheader("📝 AI 目前的掛單 (Pending Orders)")
        st.markdown("這是 AI 預測未來走勢後，目前掛在市場上**等待成交**的單子。")
        
        df_pending = get_pending_orders()
        if not df_pending.empty:
            show_df = df_pending[['date', 'stock_id', 'action', 'order_price', 'shares', 'status']].copy()
            show_df['order_price'] = show_df['order_price'].apply(lambda x: f"${x:,.2f}")
            
            def highlight_action(val):
                return 'color: red' if val == 'BUY' else 'color: green'
            
            st.dataframe(show_df.style.applymap(highlight_action, subset=['action']), use_container_width=True)
        else:
            st.info("😴 目前沒有掛單 (AI 正在休息或認為現在不宜進場)")

    st.divider()

    # --- 區塊 C: 詳細帳本 (Tables) ---
    c3, c4 = st.columns(2)

    with c3:
        st.subheader("📦 目前庫存 (Inventory)")
        if not df_inventory.empty:
            st.dataframe(df_inventory, use_container_width=True)
        else:
            st.write("目前空手 (No Position)")

    with c4:
        st.subheader("📜 歷史成交紀錄 (Transactions)")
        df_trans = get_transaction_history()
        if not df_trans.empty:
            cols = ['trade_date', 'stock_id', 'action', 'price', 'shares', 'fee', 'tax', 'total_amount']
            show_trans = df_trans[cols].copy()
            
            show_trans['price'] = show_trans['price'].apply(lambda x: f"{x:.2f}")
            show_trans['total_amount'] = show_trans['total_amount'].apply(lambda x: f"{x:,.0f}")
            
            st.dataframe(
                show_trans.style.applymap(lambda x: 'color: red' if x == 'BUY' else 'color: green', subset=['action']),
                use_container_width=True
            )
        else:
            st.write("尚無成交紀錄")

if __name__ == "__main__":
    st.set_page_config(layout="wide")
    show_ai_trading_page()
