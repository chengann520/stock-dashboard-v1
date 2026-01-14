import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# --- 🎯 精選名單定義區 ---

# 1. 台灣 50 成分股 (大型權值股)
tw50 = [
    '2330.TW', '2317.TW', '2454.TW', '2308.TW', '2382.TW', '2881.TW', '2882.TW', '2886.TW', '2891.TW', '1216.TW',
    '1301.TW', '1303.TW', '2002.TW', '2412.TW', '3008.TW', '3034.TW', '2303.TW', '2603.TW', '2609.TW', '2615.TW',
    '3711.TW', '2884.TW', '5880.TW', '2892.TW', '2880.TW', '2885.TW', '2883.TW', '2890.TW', '1101.TW', '1102.TW',
    '2357.TW', '3231.TW', '2327.TW', '2379.TW', '2345.TW', '6669.TW', '3037.TW', '2395.TW', '2408.TW', '2912.TW',
    '3045.TW', '4904.TW', '2801.TW', '6505.TW', '1326.TW', '2207.TW', '1590.TW', '3017.TW', '5871.TW', '9910.TW'
]

# 2. 台灣中型 100 (成長股、AI 供應鏈、熱門股)
mid100 = [
    '2376.TW', '2383.TW', '2368.TW', '3443.TW', '3661.TW', '3529.TW', '3035.TW', '3006.TW', '3189.TW', '3227.TW',
    '8046.TW', '6239.TW', '6278.TW', '6213.TW', '6415.TW', '6770.TW', '6643.TW', '6719.TW', '5347.TWO', '3293.TWO',
    '8299.TWO', '8069.TWO', '3324.TWO', '6147.TWO', '3131.TWO', '3374.TWO', '3680.TWO', '6121.TWO', '4966.TWO', '5274.TWO',
    '2610.TW', '2618.TW', '2606.TW', '2637.TW', '2633.TW', '1513.TW', '1519.TW', '1504.TW', '1514.TW', '1605.TW',
    '2511.TW', '2542.TW', '5522.TW', '2501.TW', '9945.TW', '2915.TW', '8454.TW', '8464.TW', '9921.TW', '9914.TW',
    '9904.TW', '1476.TW', '1402.TW', '1907.TW', '1717.TW', '1722.TW', '1704.TW', '4763.TW', '4137.TW', '1795.TW',
    '4147.TW', '4174.TW', '1760.TW', '6446.TW', '8436.TW', '2049.TW', '2059.TW', '2014.TW', '2027.TW', '2313.TW',
    '2353.TW', '2324.TW', '2356.TW', '2352.TW', '2301.TW', '2449.TW', '2421.TW', '2498.TW', '3532.TW', '3406.TW',
    '3481.TW', '2409.TW', '6176.TW', '6269.TW', '8150.TW', '4938.TW', '4958.TW', '4919.TW', '9938.TW', '9958.TW'
]

# 3. 熱門 ETF
etfs = [
    '0050.TW', '0056.TW', '00878.TW', '00929.TW', '00919.TW', '006208.TW', '00713.TW', '00679B.TW'
]

# 4. 美股科技巨頭 (Optional)
us_stocks = [
    'TSLA', 'AAPL', 'NVDA', 'AMD', 'MSFT', 'GOOG', 'AMZN', 'META', 'NFLX', 'INTC'
]

# 5. 台灣金融股全集 (含金控、銀行、證券、保險、租賃)
financials = [
    # --- 14家金控 (權值最重) ---
    '2881.TW', '2882.TW', '2891.TW', '2886.TW', '2884.TW',  # 富邦、國泰、中信、兆豐、玉山
    '2892.TW', '2885.TW', '5880.TW', '2880.TW', '2883.TW',  # 第一、元大、合庫、華南、凱基(原開發)
    '2890.TW', '2887.TW', '2888.TW', '2889.TW',             # 永豐、台新、新光、國票

    # --- 銀行股 (非金控) ---
    '2801.TW', '2834.TW', '2812.TW', '5876.TW', '2838.TW',  # 彰銀、臺企銀、台中銀、上海商銀、聯邦銀
    '2845.TW', '2836.TW', '2849.TW',                        # 遠東銀、高雄銀、安泰銀

    # --- 證券 & 期貨 ---
    '6005.TW', '6024.TW', '2855.TW', '6023.TWO',            # 群益證、群益期、統一證、元大期

    # --- 保險 & 再保 ---
    '2850.TW', '2851.TW', '2852.TW', '2816.TWO',            # 新產、中再保、第一保、旺旺保
    '2832.TW',                                              # 台產

    # --- 租賃 & 其他金融相關 ---
    '5871.TW', '9941.TW'                                    # 中租-KY、裕融
]

# 合併所有名單 (並去除重複)
all_targets = list(set(tw50 + mid100 + etfs + us_stocks + financials))

# 定義名稱對照 (簡化版，讓程式有東西顯示即可，詳細名稱 yfinance 抓不到也沒關係)
stock_data = [{"stock_id": sid, "company_name": sid} for sid in all_targets]

def seed_top200():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ 錯誤：找不到 DATABASE_URL")
        return

    print(f"🚀 準備寫入 {len(stock_data)} 檔精選股票 (Top 200)...")
    
    engine = create_engine(db_url)
    
    try:
        with engine.begin() as conn:
            # 1. 為了確保名單乾淨，我們先清空 dim_stock
            print("🧹 清除舊名單...")
            # CASCADE 也會刪除 fact_price 相關數據
            conn.execute(text("TRUNCATE TABLE dim_stock CASCADE;"))
            
            # 2. 寫入新名單
            print("📝 寫入新名單...")
            for row in stock_data:
                sql = text("""
                    INSERT INTO dim_stock (stock_id, company_name)
                    VALUES (:stock_id, :company_name)
                """)
                conn.execute(sql, row)
                
        print(f"✅ 成功更新！目前資料庫有 {len(stock_data)} 檔股票。")
        print("⚠️ 注意：公司名稱目前暫時設為代碼，你可以之後再手動更新或用腳立補齊中文名。")
        
    except Exception as e:
        print(f"❌ 寫入失敗: {e}")

if __name__ == "__main__":
    seed_top200()
