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
            'N1_MOMENTUM': '🏆 N1 策略 (動能 + 國債避險)',
            'BEST_OF_3': '🚀 Best of 3 (抄底策略)',
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

        # === 動態參數區 (根據上面的選擇變換) ===
        st.info("👇 請設定該策略的詳細參數：")
        
        # 預設值讀取
        p1_val = int(config.get('param_1', 0))
        p2_val = int(config.get('param_2', 0))
        
        col_p1, col_p2 = st.columns(2)
        
        # 參數 1 & 2 的意義會隨策略改變
        if selected_strategy == 'N1_MOMENTUM':
            st.success("🏆 **N1 策略邏輯**：\n1. 鎖定台股科技巨頭 (如台積電、聯發科...)\n2. 買進「漲勢最強」的前 2 名。\n3. 若大盤不穩或 RSI 過熱，自動轉進「債券 ETF (00679B)」避險。")
            with col_p1:
                p1 = st.number_input("動能週期 (天)", value=p1_val if p1_val>0 else 60, help="計算過去幾天的漲幅來排名 (預設 60天/一季)")
            with col_p2:
                p2 = st.number_input("RSI 安全門檻", value=p2_val if p2_val>0 else 80, help="RSI 超過此數值代表過熱，不追高")
            
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
            st.success("🚀 **Best of 3 (改量版) 邏輯**：\n模擬 Composer 的抄底邏輯。系統會監控一籃子優質股，專門買進「近期跌最深 (Drawdown 最大)」但「長線趨勢仍向上」的股票，賭它均值回歸。")
            with col_p1:
                p1 = st.number_input("回撤觀察期 (天)", value=p1_val if p1_val>0 else 20, help="看過去幾天內的跌幅")
            with col_p2:
                p2 = st.number_input("長線保護 (MA天數)", value=p2_val if p2_val>0 else 200, help="股價必須在年線之上才敢抄底")

        elif selected_strategy == 'MA_CROSS':
            with col_p1:
                p1 = st.number_input("短期均線 (MA Short)", value=p1_val if p1_val>0 else 5, min_value=3)
            with col_p2:
                p2 = st.number_input("長期均線 (MA Long)", value=p2_val if p2_val>0 else 20, min_value=10)
            st.caption("邏輯：當 短均線 向上突破 長均線 時買進。")
            
        elif selected_strategy == 'RSI_REVERSAL':
            with col_p1:
                p1 = st.number_input("RSI 週期 (通常 14)", value=p1_val if p1_val>0 else 14)
            with col_p2:
                p2 = st.number_input("超賣區門檻 (通常 30)", value=p2_val if p2_val>0 else 30)
            st.caption("邏輯：當 RSI 低於門檻且開始回升時買進。")
            
        elif selected_strategy == 'KD_CROSS':
            with col_p1:
                p1 = st.number_input("RSV 週期 (通常 9)", value=p1_val if p1_val>0 else 9)
            with col_p2:
                p2 = st.number_input("KD 低檔門檻 (通常 20)", value=p2_val if p2_val>0 else 20)
            st.caption("邏輯：當 K值由下往上突破 D值，且 K值 < 門檻時買進。")
 
        elif selected_strategy == 'MACD_CROSS':
            with col_p1:
                p1 = st.number_input("快線 EMA (通常 12)", value=p1_val if p1_val>0 else 12)
            with col_p2:
                p2 = st.number_input("慢線 EMA (通常 26)", value=p2_val if p2_val>0 else 26)
            st.caption("邏輯：當 MACD 柱狀體由綠翻紅 (或快線突破慢線) 時買進。")

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

        with c_risk2:
            stop_loss = st.slider("🛑 停損點 (Stop Loss %)", 0.01, 0.30, float(config.get('stop_loss_pct', 0.05)))
            
            # 停利設定 (包含 AI 動態停利)
            curr_tp = float(config.get('take_profit_pct', 0.1))
            use_ai_exit = st.checkbox("由 AI 決定何時賣出 (動態停利)", value=(curr_tp == 0))
            
            if use_ai_exit:
                take_profit = 0.0
                st.caption("🤖 AI 將在技術指標轉弱時賣出 (例如均線死叉)")
            else:
                take_profit = st.slider("💰 固定停利點 %", 0.05, 1.00, 0.1 if curr_tp==0 else curr_tp)

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
