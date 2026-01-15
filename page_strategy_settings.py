import streamlit as st
from supabase import create_client
import os

# --- 連線設定 ---
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

def load_config():
    """從資料庫讀取目前的設定"""
    try:
        data = supabase.table('strategy_config').select('*').eq('user_id', 'default_user').execute().data
        if data:
            return data[0]
    except Exception as e:
        st.error(f"讀取設定失敗: {e}")
    return {}

def save_config(new_config):
    """將新設定寫回資料庫"""
    try:
        new_config['user_id'] = 'default_user' # 確保主鍵
        new_config['updated_at'] = 'now()'
        supabase.table('strategy_config').upsert(new_config).execute()
        st.success("✅ 策略參數已更新！機器人下次執行時將生效。")
    except Exception as e:
        st.error(f"儲存失敗: {e}")

def show_strategy_settings_page():
    st.title("🧠 AI 策略邏輯灌輸中心")
    st.info("在此教導 AI 該使用哪種技術指標來判斷進場點。")

    # 讀取現有設定
    current_config = load_config()
    
    if not current_config:
        st.warning("無法讀取設定，使用預設值")
        current_config = {}

    with st.form("strategy_form"):
        st.subheader("1. 資金與風險管理 (Risk Management)")
        
        col1, col2 = st.columns(2)
        with col1:
            # 單筆交易金額上限
            max_pos = st.number_input(
                "單筆最大投入金額 (NTD)", 
                min_value=10000, 
                max_value=1000000, 
                step=10000, 
                value=int(current_config.get('max_position_size', 100000))
            )
            
        with col2:
            # 停損百分比
            stop_loss = st.slider(
                "停損點 (Stop Loss %)", 
                min_value=0.01, max_value=0.20, step=0.01,
                value=float(current_config.get('stop_loss_pct', 0.05)),
                format="%.2f"
            )

        st.divider()

        # === 重點：策略邏輯選擇區 ===
        st.subheader("2. 核心交易邏輯 (Core Logic)")
        
        # 定義有哪些策略可選
        strategies = {
            'MA_CROSS': '📈 均線黃金交叉 (順勢策略)',
            'RSI_REVERSAL': '📉 RSI 超賣反彈 (逆勢抄底)',
            'KD_CROSS': '🔁 KD 指標黃金交叉 (波段操作)'
        }
        
        # 找出目前設定的策略索引
        curr_strat = current_config.get('active_strategy', 'MA_CROSS')
        strat_keys = list(strategies.keys())
        try:
            idx = strat_keys.index(curr_strat)
        except:
            idx = 0
            
        selected_strat_key = st.selectbox(
            "請選擇要灌輸給 AI 的交易邏輯",
            options=strat_keys,
            format_func=lambda x: strategies[x],
            index=idx
        )
        
        # 根據選擇的策略，動態顯示參數輸入框
        p1_val = int(current_config.get('param_1', 5))
        p2_val = int(current_config.get('param_2', 20))
        
        col_p1, col_p2 = st.columns(2)
        
        if selected_strat_key == 'MA_CROSS':
            st.caption("說明：當「短期均線」向上突破「長期均線」時買進。")
            with col_p1:
                param_1 = st.number_input("短期均線天數 (MA Short)", value=p1_val, min_value=3)
            with col_p2:
                param_2 = st.number_input("長期均線天數 (MA Long)", value=p2_val, min_value=10)
                
        elif selected_strat_key == 'RSI_REVERSAL':
            st.caption("說明：當 RSI 低於「超賣區」且開始回升時買進。")
            with col_p1:
                param_1 = st.number_input("RSI 天數", value=p1_val if p1_val > 0 else 14)
            with col_p2:
                param_2 = st.number_input("超賣門檻 (通常 30)", value=p2_val if p2_val > 0 else 30)
                
        elif selected_strat_key == 'KD_CROSS':
            st.caption("說明：當 K 值由下往上突破 D 值，且數值低於門檻時買進。")
            with col_p1:
                param_1 = st.number_input("RSV 天數 (通常 9)", value=p1_val if p1_val > 0 else 9)
            with col_p2:
                param_2 = st.number_input("低檔門檻 (通常 20)", value=p2_val if p2_val > 0 else 20)

        st.divider()
        
        submitted = st.form_submit_button("🧠 灌輸邏輯並儲存")
        
        if submitted:
            new_settings = {
                'max_position_size': max_pos,
                'stop_loss_pct': stop_loss,
                'active_strategy': selected_strat_key,
                'param_1': param_1,
                'param_2': param_2
            }
            save_config(new_settings)

if __name__ == "__main__":
    show_strategy_settings_page()
