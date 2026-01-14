修改 src/extract.py (抓取籌碼資料)
我們要修改 extract_data 函式。邏輯是：

如果是台股 (.TW 或 .TWO)，就額外呼叫 FinMind 抓籌碼。

如果是美股 (TSLA, AAPL)，就跳過（美股沒有這種定義的法人資料）。

請用這段程式碼 取代 原本的 src/extract.py：

Python

import yfinance as yf
import pandas as pd
import logging
from datetime import datetime, timedelta
from FinMind.data import DataLoader # 引入 FinMind

def extract_data(symbol: str, period: str = "1mo"):
    """
    從 Yahoo Finance 抓股價 + 從 FinMind 抓三大法人
    """
    try:
        # 1. 先抓股價 (Yahoo Finance)
        stock = yf.Ticker(symbol)
        df_price = stock.history(period=period)
        
        if df_price.empty:
            logging.warning(f"⚠️ {symbol} 抓不到股價")
            return None

        # 整理股價 DataFrame
        df_price.reset_index(inplace=True)
        df_price['Date'] = pd.to_datetime(df_price['Date']).dt.date
        df_price.rename(columns={
            'Date': 'date', 'Open': 'open', 'High': 'high', 
            'Low': 'low', 'Close': 'close', 'Volume': 'volume'
        }, inplace=True)
        
        # 只留需要的欄位
        df_price = df_price[['date', 'open', 'high', 'low', 'close', 'volume']]
        df_price['stock_id'] = symbol

        # ==========================================
        # 2. 抓取三大法人 (FinMind) - 僅限台股
        # ==========================================
        if ".TW" in symbol or ".TWO" in symbol:
            try:
                # 處理代碼：把 '2330.TW' 變成 '2330' (FinMind 格式)
                stock_id_finmind = symbol.split('.')[0]
                
                # 計算日期範圍 (配合 period)
                end_date = datetime.now().strftime('%Y-%m-%d')
                start_date = (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d') # 多抓一點避免缺漏
                
                dl = DataLoader()
                # 抓取「三大法人買賣」
                df_chips = dl.taiwan_stock_institutional_investors(
                    stock_id=stock_id_finmind, 
                    start_date=start_date, 
                    end_date=end_date
                )
                
                if not df_chips.empty:
                    # 整理籌碼資料
                    # FinMind 回傳欄位: date, stock_id, buy, sell, name (Foreign_Investor, etc.)
                    
                    # 樞紐分析 (Pivot): 把直的表變成橫的
                    df_chips['date'] = pd.to_datetime(df_chips['date']).dt.date
                    
                    # 計算「買賣超」 (buy - sell)
                    df_chips['net'] = df_chips['buy'] - df_chips['sell']
                    
                    # Pivot Table: 轉成我們好讀的格式
                    pivot_df = df_chips.pivot_table(
                        index='date', 
                        columns='name', 
                        values='net', 
                        aggfunc='sum'
                    ).reset_index()
                    
                    # 對應欄位名稱
                    # Foreign_Investor -> foreign_net (外資)
                    # Investment_Trust -> trust_net (投信)
                    # Dealer_Self / Dealer_Hedging -> dealer_net (自營商合計)
                    
                    pivot_df['dealer_net'] = pivot_df.get('Dealer_Self', 0) + pivot_df.get('Dealer_Hedging', 0)
                    
                    # 重新命名與選取
                    rename_map = {
                        'Foreign_Investor': 'foreign_net',
                        'Investment_Trust': 'trust_net'
                    }
                    pivot_df.rename(columns=rename_map, inplace=True)
                    
                    # 確保欄位存在 (如果當天某法人沒動作，補 0)
                    for col in ['foreign_net', 'trust_net', 'dealer_net']:
                        if col not in pivot_df.columns:
                            pivot_df[col] = 0
                            
                    # 3. 合併 (Merge) 股價與籌碼
                    df_final = pd.merge(df_price, pivot_df[['date', 'foreign_net', 'trust_net', 'dealer_net']], on='date', how='left')
                    
                    # 補 0 (避免 NaN)
                    df_final[['foreign_net', 'trust_net', 'dealer_net']] = df_final[['foreign_net', 'trust_net', 'dealer_net']].fillna(0)
                    
                    return df_final

            except Exception as e:
                logging.warning(f"⚠️ {symbol} 籌碼抓取失敗 (但股價已抓到): {e}")
                # 就算籌碼失敗，還是回傳股價
                df_price['foreign_net'] = 0
                df_price['trust_net'] = 0
                df_price['dealer_net'] = 0
                return df_price

        # 如果是美股，補 0
        df_price['foreign_net'] = 0
        df_price['trust_net'] = 0
        df_price['dealer_net'] = 0
        
        return df_price

    except Exception as e:
        logging.error(f"❌ {symbol} 資料抓取失敗: {e}")
        return None
