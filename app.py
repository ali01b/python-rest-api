from flask import Flask, jsonify
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# 1. GÜNCELLENMİŞ FIBONACCI HESABI (Daha kısa periyot)
def calculate_fibonacci_levels(data):
    recent_data = data[-90:]  # 3 aylık veri
    if len(recent_data) < 20: return []  # Minimum veri kontrolü
    
    max_price = recent_data['high'].max()
    min_price = recent_data['low'].min()
    diff = max_price - min_price
    
    return [
        round(max_price - diff * 0.236, 2),  # Fibonacci düzeltme seviyeleri
        round(max_price - diff * 0.382, 2),
        round(max_price - diff * 0.5, 2)
    ]

# 2. DÜZELTİLMİŞ PIVOT HESAPLAMA (Canlı fiyat entegrasyonu)
def calculate_pivot_levels(data, latest_price):
    try:
        # Son 6 haftalık veri
        weekly_data = data[-42:].resample('W', on='date').agg({
            'high': 'max',
            'low': 'min',
            'close': 'last'
        })
        
        if weekly_data.empty: 
            return {"R1": latest_price, "R2": latest_price, 
                    "S1": latest_price, "S2": latest_price}
        
        last_week = weekly_data.iloc[-1]
        pp = (last_week['high'] + last_week['low'] + last_week['close']) / 3
        
        return {
            "R1": round((2 * pp) - last_week['low'], 2),
            "R2": round(pp + (last_week['high'] - last_week['low']), 2),
            "S1": round((2 * pp) - last_week['high'], 2),
            "S2": round(pp - (last_week['high'] - last_week['low']), 2)
        }
    except Exception as e:
        print(f"Pivot Hatası: {e}")
        return {"R1": latest_price, "R2": latest_price, 
                "S1": latest_price, "S2": latest_price}

# 3. GÜNCELLENMİŞ DESTEK-DİRENÇ FİLTRESİ
def filter_levels(levels, latest_price, buffer=0.05):
    price_buffer = latest_price * buffer
    return [
        l for l in levels 
        if (latest_price - price_buffer) < l < (latest_price + price_buffer)
    ]

@app.route('/stock/<ticker>', methods=['GET'])
def get_stock_data(ticker):
    try:
        # GERÇEK ZAMANLI VERİ ÇEKME
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y", interval="1d")  # 1 yıllık günlük veri
        
        if hist.empty:
            return jsonify({"error": "Veri bulunamadı"}), 404
        
        # TARİH FORMATI VE SIRALAMA
        hist = hist.reset_index().sort_values('Date', ascending=False)
        hist.rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"
        }, inplace=True)
        
        # SON FİYAT KONTROLÜ
        latest_price = round(hist.iloc[0]['close'], 2)
        hist['date'] = hist['date'].dt.strftime('%Y-%m-%d')
        
        # GÜNCELLENMİŞ SEVİYE HESAPLAMALARI
        fib_levels = calculate_fibonacci_levels(hist)
        pivot_levels = calculate_pivot_levels(hist, latest_price)
        
        # SEVİYE KARIŞIMI VE FİLTRELEME
        all_levels = fib_levels + list(pivot_levels.values())
        relevant_levels = filter_levels(all_levels, latest_price)
        
        # TARİHSEL VERİYİ SON 30 GÜN İLE SINIRLA
        historical_data = hist.head(30)[['date', 'open', 'high', 'low', 'close']]
        
        return jsonify({
            "ticker": ticker.replace(".IS", ""),
            "price": latest_price,
            "levels": sorted(relevant_levels),
            "historical": historical_data.to_dict(orient='records'),
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(port=8080, debug=True)