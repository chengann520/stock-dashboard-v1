import streamlit as st
from supabase import create_client
import os

# --- 連線設定 ---
SUPABASE_URL = st.secrets["SUPABASE_URL"] if "SUPABASE_URL" in st.secrets else os.environ.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets["SUPABASE_KEY"] if "SUPABASE_KEY" in st.secrets else os.environ.get("SUPABASE_KEY")

try:
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("❌ 未設定 SUPABASE_URL 或 SUPABASE_KEY")
        st.stop()
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"連線失敗，請檢查 Secrets 設定: {e}")
    st.stop()

def load_config():
    """從資料庫讀取目前的 AI 大腦設定"""
    try:
        data = supabase.table('strategy_config').select('*').eq('user_id', 'default_user').execute().data
        if data: return data[0]
    except:
        pass
    return {}

def save_config(new_config):
    """將策略餵給資料庫"""
    try:
        new_config['user_id'] = 'default_user'
        new_config['updated_at'] = 'now()'
        supabase.table('strategy_config').upsert(new_config).execute()
        st.toast("✅ 策略已成功餵入 AI 大腦！", icon="🧠")
        st.success("設定已儲存，機器人將於下次執行時採用新策略。")
    except Exception as e:
        st.error(f"儲存失敗: {e}")

def show_strategy_settings_page():
    st.title("🧠 AI 策略指揮中心")
    st.markdown("在此頁面定義交易邏輯，**點擊儲存後，GitHub 機器人會自動讀取並執行**。")

    # 讀取現有設定
    config = load_config()
    
    # --- 頂部狀態列 ---
    curr_strat = config.get('active_strategy', 'MA_CROSS')
    curr_risk = config.get('risk_preference', 'NEUTRAL')
    
    c1, c2, c3 = st.columns(3)
    c1.metric("目前運作策略", curr_strat)
    c2.metric("目前風險屬性", curr_risk)
    c3.metric("單筆交易預算", f"${config.get('max_position_size', 100000):,}")
    
    st.divider()

    with st.form("strategy_feeder"):
        # =========================================
        # 1. 選擇核心戰術 (Core Strategy)
        # =========================================
        st.subheader("1. 選擇核心戰術")
        
        # 定義策略選項與說明
        strategies = {
            'N1_MOMENTUM': '🏆 N1 策略 (首選：極致穩定)',
            'BEST_OF_3': '🚀 Best of 3 (進階：高回報抄底)',
            'MA_CROSS': '📈 均線黃金交叉 (趨勢策略)',
            'RSI_REVERSAL': '📉 RSI 低檔反彈 (逆勢策略)',
            'KD_CROSS': '🔁 KD 低檔金叉 (波段策略)',
            'MACD_CROSS': '📊 MACD 柱狀圖翻紅 (動能策略)'
        }
        
        # 找出目前的選項索引
        strat_keys = list(strategies.keys())
        try:
            curr_idx = strat_keys.index(curr_strat)
        except:
            curr_idx = 0
            
        selected_strategy = st.selectbox(
            "請選擇要餵給 AI 的邏輯：",
            options=strat_keys,
            format_func=lambda x: strategies[x],
            index=curr_idx
        )

        # === 參數區 (由資料庫讀取，或使用預設值) ===
        p1_val = config.get('param_1', 0)
        p2_val = config.get('param_2', 0)

        p1 = p1_val if p1_val > 0 else (60 if selected_strategy == 'N1_MOMENTUM' else 5)
        p2 = p2_val if p2_val > 0 else (80 if selected_strategy == 'N1_MOMENTUM' else 20)
        
        if selected_strategy == 'N1_MOMENTUM':
            st.success("""
            **🏆 首選推薦：Composer "N1" 策略**
            *這目前最適合「長期持有」且「睡得著覺」的穩定型策略。*
            
            **運作邏輯：**
            1. **選股**：每天從 10 檔科技巨頭中，挑選出近期漲勢最強的 2 檔。
            2. **安全檢查**：檢查標的是否過熱 (RSI) 以及是否處於上升趨勢。
            3. **避險機制**：若市場有危險訊號，資金自動轉向「現金」或「美債 ETF」。
            """)
            
            st.divider()
            st.write("🛡️ **避險模式設定**")
            current_safe = config.get('safe_asset_id', '00679B.TW')
            safe_option = st.radio(
                "當觸發避險時，資金要停泊在哪裡？",
                ["現金 (CASH) - 空手觀望", "美債 ETF (00679B) - 股債平衡"],
                index=0 if current_safe == 'CASH' else 1
            )
            final_safe_asset = 'CASH' if "現金" in safe_option else '00679B.TW'

        elif selected_strategy == 'BEST_OF_3':
            st.warning("""
            **🚀 進階推薦：The Best of Three**
            *追求 2025 年目前數據表現最強的策略，適合風險承受度稍高的投資者。*
            
            **運作邏輯：**
            1. **抄底邏輯**：監控優質股池，專門買進「近期跌最深 (Drawdown 最大)」的股票。
            2. **均值回歸**：賭它即將觸底反彈，吃到反彈最肥美的一段利潤。
            3. **長線保護**：股價必須在年線之上才敢抄底，確保不是買到爛股。
            """)

        st.divider()

        # =========================================
        # 2. 風險與資金 (Risk & Money)
        # =========================================
        st.subheader("2. 風險控管設定")
        
        c_risk1, c_risk2 = st.columns(2)
        with c_risk1:
            risk_options = {'AVERSE': '🛡️ 保守 (買少一點)', 'NEUTRAL': '⚖️ 中立 (標準)', 'SEEKING': '🔥 積極 (買多一點)'}
            curr_r_key = config.get('risk_preference', 'NEUTRAL')
            risk_pref = st.selectbox("風險性格", list(risk_options.keys()), 
                                     format_func=lambda x: risk_options[x],
                                     index=list(risk_options.keys()).index(curr_r_key) if curr_r_key in risk_options else 1)
            
            max_pos = st.number_input("單筆交易預算 (NTD)", value=int(config.get('max_position_size', 100000)), step=10000)
            stop_loss = st.slider("🛑 停損點 (Stop Loss %)", 0.01, 0.30, float(config.get('stop_loss_pct', 0.05)))

        with c_risk2:
            st.write("💰 **獲利出場設定**")
            st.info("🤖 **AI 自動判斷**：系統將根據技術指標轉弱時自動賣出，以追求最大化利潤。")
            take_profit = 0.0

        st.divider()
        
        # =========================================
        # 3. 提交按鈕
        # =========================================
        submit_btn = st.form_submit_button("🚀 儲存並餵給 AI", type="primary")
        
        if submit_btn:
            new_data = {
                'active_strategy': selected_strategy,
                'param_1': p1,
                'param_2': p2,
                'safe_asset_id': final_safe_asset if selected_strategy == 'N1_MOMENTUM' else config.get('safe_asset_id', '00679B.TW'),
                'risk_preference': risk_pref,
                'max_position_size': max_pos,
                'stop_loss_pct': stop_loss,
                'take_profit_pct': take_profit
            }
            save_config(new_data)
            # 重新整理頁面以更新頂部狀態
            st.rerun()

if __name__ == "__main__":
    show_strategy_settings_page()
