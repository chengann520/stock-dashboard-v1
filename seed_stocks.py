import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 載入 .env 裡的 DATABASE_URL
load_dotenv()

# 台灣熱門 50 大股票清單 (你可以隨時在這裡增加)
stocks_list = [
    {"id": "0050.TW", "name": "元大台灣50"},
    {"id": "2330.TW", "name": "台積電"},
    {"id": "2317.TW", "name": "鴻海"},
    {"id": "2454.TW", "name": "聯發科"},
    {"id": "2308.TW", "name": "台達電"},
    {"id": "2382.TW", "name": "廣達"},
    {"id": "2881.TW", "name": "富邦金"},
    {"id": "2882.TW", "name": "國泰金"},
    {"id": "2886.TW", "name": "兆豐金"},
    {"id": "2891.TW", "name": "中信金"},
    {"id": "1216.TW", "name": "統一"},
    {"id": "1301.TW", "name": "台塑"},
    {"id": "1303.TW", "name": "南亞"},
    {"id": "2002.TW", "name": "中鋼"},
    {"id": "2412.TW", "name": "中華電"},
    {"id": "3008.TW", "name": "大立光"},
    {"id": "3034.TW", "name": "聯詠"},
    {"id": "2303.TW", "name": "聯電"},
    {"id": "2603.TW", "name": "長榮"},
    {"id": "2609.TW", "name": "陽明"},
    {"id": "2615.TW", "name": "萬海"},
    {"id": "3711.TW", "name": "日月光投控"},
    {"id": "2884.TW", "name": "玉山金"},
    {"id": "5880.TW", "name": "合庫金"},
    {"id": "2892.TW", "name": "第一金"},
    {"id": "2880.TW", "name": "華南金"},
    {"id": "2885.TW", "name": "元大金"},
    {"id": "2883.TW", "name": "開發金"},
    {"id": "2890.TW", "name": "永豐金"},
    {"id": "1101.TW", "name": "台泥"},
    {"id": "1102.TW", "name": "亞泥"},
    {"id": "2357.TW", "name": "華碩"},
    {"id": "3231.TW", "name": "緯創"},
    {"id": "2327.TW", "name": "國巨"},
    {"id": "2379.TW", "name": "瑞昱"},
    {"id": "2345.TW", "name": "智邦"},
    {"id": "6669.TW", "name": "緯穎"},
    {"id": "3037.TW", "name": "欣興"},
    {"id": "2395.TW", "name": "研華"},
    {"id": "2408.TW", "name": "南亞科"},
    {"id": "2912.TW", "name": "統一超"},
    {"id": "TSLA", "name": "Tesla"},
    {"id": "AAPL", "name": "Apple"},
    {"id": "NVDA", "name": "NVIDIA"},
]

def seed_data():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ 錯誤: 找不到 DATABASE_URL")
        return

    engine = create_engine(db_url)
    
    print(f"🚀 準備寫入 {len(stocks_list)} 檔股票...")
    
    with engine.begin() as conn:
        for stock in stocks_list:
            # 注意：這裡將 company_name 修改為符合 schema.sql 的 stock_name
            sql = text("""
                INSERT INTO dim_stock (stock_id, stock_name)
                VALUES (:id, :name)
                ON CONFLICT (stock_id) 
                DO UPDATE SET stock_name = :name;
            """)
            conn.execute(sql, {"id": stock["id"], "name": stock["name"]})
            
    print("✅ 股票清單更新完成！")

if __name__ == "__main__":
    seed_data()
