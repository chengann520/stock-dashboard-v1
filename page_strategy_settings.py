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
    st.title("🧠 AI 策略與風險控制中心")
    
    current_config = load_config()

    with st.form("strategy_form"):
        # === 1. 風險性格設定 ===
        st.subheader("1. 風險性格設定 (Risk Personality)")
        st.info("這會影響 AI 的下單部位大小與進場積極度。")
        
        risk_options = {
            'AVERSE': '🛡️ 風險趨避 (保守，部位 x0.8，高門檻)',
            'NEUTRAL': '⚖️ 風險中立 (標準，部位 x1.0)',
            'SEEKING': '🔥 風險偏好 (激進，部位 x1.2，低門檻)'
        }
        
        curr_risk = current_config.get('risk_preference', 'NEUTRAL')
        risk_key = st.selectbox(
            "請選擇您的風險偏好",
            options=list(risk_options.keys()),
            format_func=lambda x: risk_options[x],
            index=list(risk_options.keys()).index(curr_risk) if curr_risk in risk_options else 1
        )

        st.divider()

        # === 2. 自動出場機制 (Exit Strategy) ===
        st.subheader("2. 自動出場機制 (Exit Strategy)")
        
        col1, col2 = st.columns(2)
        with col1:
            stop_loss = st.slider(
                "🛑 停損點 (Stop Loss %)", 
                0.01, 0.30, 
                float(current_config.get('stop_loss_pct', 0.05)),
                format="%.2f",
                help="虧損超過此比例，AI 將強制止損"
            )
            
        with col2:
            # 讀取現有設定，如果是 0 代表是用 AI 判斷
            current_tp = float(current_config.get('take_profit_pct', 0.10))
            is_dynamic = (current_tp == 0.0)
            
            st.write("💰 停利策略")
            # 使用 Checkbox 切換模式
            use_ai_exit = st.checkbox("由 AI 自行判斷賣點 (趨勢反轉才賣)", value=is_dynamic)
            
            if use_ai_exit:
                st.info("🤖 AI 將在出現「技術賣訊」時才獲利了結 (例如: 均線死亡交叉)。這能讓獲利最大化，但也可能回吐部分獲利。")
                take_profit = 0.0 # 存入 0 代表動態停利
            else:
                take_profit = st.slider(
                    "固定停利點 %", 
                    0.05, 1.00, 
                    0.10 if is_dynamic else current_tp, # 如果原本是 AI 模式，切回來預設 10%
                    format="%.2f"
                )

        st.divider()

        # === 3. 資金與交易邏輯 ===
        st.subheader("3. 交易邏輯與資金")
        max_pos = st.number_input("基準單筆金額 (NTD)", value=int(current_config.get('max_position_size', 100000)))
        
        # 策略選擇
        strategies = {
            'MA_CROSS': '📈 均線黃金交叉 (順勢策略)',
            'RSI_REVERSAL': '📉 RSI 超賣反彈 (逆勢抄底)',
            'KD_CROSS': '🔁 KD 指標黃金交叉 (波段操作)'
        }
        curr_strat = current_config.get('active_strategy', 'MA_CROSS')
        strat_keys = list(strategies.keys())
        try:
            idx = strat_keys.index(curr_strat)
        except:
            idx = 0
            
        selected_strat_key = st.selectbox(
            "核心策略",
            options=strat_keys,
            format_func=lambda x: strategies[x],
            index=idx
        )
        
        # 參數輸入
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
        
        submitted = st.form_submit_button("💾 更新 AI 大腦")
        
        if submitted:
            new_settings = {
                'risk_preference': risk_key,
                'stop_loss_pct': stop_loss,
                'take_profit_pct': take_profit,
                'max_position_size': max_pos,
                'active_strategy': selected_strat_key,
                'param_1': param_1,
                'param_2': param_2
            }
            save_config(new_settings)

if __name__ == "__main__":
    show_strategy_settings_page()
