import streamlit as st
from supabase import create_client
import os

# --- 連線設定 ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")

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
    st.title("⚙️ AI 策略指揮中心")
    st.markdown("在這裡調整交易參數，您的 GitHub 機器人會自動讀取最新的指令。")

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

        st.subheader("2. AI 策略邏輯 (Strategy Logic)")
        
        # 策略模式
        mode_options = ['CONSERVATIVE', 'AGGRESSIVE', 'BALANCED']
        current_mode = current_config.get('strategy_mode', 'CONSERVATIVE')
        try:
            idx = mode_options.index(current_mode)
        except:
            idx = 0
            
        strategy_mode = st.selectbox(
            "交易風格模式", 
            mode_options,
            index=idx,
            help="保守: 只買權值股 / 積極: 包含中小型股"
        )
        
        col3, col4 = st.columns(2)
        with col3:
            # 停利百分比
            take_profit = st.slider(
                "停利點 (Take Profit %)", 
                min_value=0.05, max_value=0.50, step=0.01,
                value=float(current_config.get('take_profit_pct', 0.10)),
                format="%.2f"
            )
        with col4:
            # AI 信心門檻
            ai_threshold = st.slider(
                "AI 信心門檻 (Confidence Threshold)", 
                min_value=0.5, max_value=0.99, step=0.01,
                value=float(current_config.get('ai_confidence_threshold', 0.7)),
                help="AI 預測機率高於此數值才下單"
            )

        st.divider()
        
        submitted = st.form_submit_button("💾 儲存設定")
        
        if submitted:
            new_settings = {
                'max_position_size': max_pos,
                'stop_loss_pct': stop_loss,
                'take_profit_pct': take_profit,
                'strategy_mode': strategy_mode,
                'ai_confidence_threshold': ai_threshold
            }
            save_config(new_settings)

if __name__ == "__main__":
    show_strategy_settings_page()
