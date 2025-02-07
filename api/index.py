from flask import Flask, jsonify
import numpy as np
import yfinance as yf
import pandas as pd
from flask_cors import CORS

app = Flask(__name__)
CORS(app)



def compute_rsi(data, window=14):
    delta = data.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    
    avg_gain = pd.Series(gain).rolling(window=window, min_periods=1).mean()
    avg_loss = pd.Series(loss).rolling(window=window, min_periods=1).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


# 1. Fibonacci Seviyeleri
def calculate_fibonacci_levels(data):
    recent_data = data[-252:]
    max_price = recent_data['high'].max()
    min_price = recent_data['low'].min()
    return [
        round(min_price + (max_price - min_price) * 0.382, 2),
        round(min_price + (max_price - min_price) * 0.5, 2),
        round(min_price + (max_price - min_price) * 0.618, 2)
    ]

# 2. Haftalık Pivotlar
def calculate_pivot_levels(data):
    try:
        data['date'] = pd.to_datetime(data['date'])
        weekly_data = data[-30:].resample('W', on='date').agg({
            'high': 'max', 'low': 'min', 'close': 'last'
        }).dropna()
        
        if len(weekly_data) == 0:
            return {"R1": 0, "R2": 0, "S1": 0, "S2": 0}
        
        latest_price = data['close'].iloc[-1]
        pp = (weekly_data['high'] + weekly_data['low'] + weekly_data['close'] + latest_price) / 4
        
        return {
            "R1": round(float((2 * pp) - weekly_data['low']).iloc[-1], 2),
            "R2": round(float(pp + (weekly_data['high'] - weekly_data['low'])).iloc[-1], 2),
            "S1": round(float((2 * pp) - weekly_data['high']).iloc[-1], 2),
            "S2": round(float(pp - (weekly_data['high'] - weekly_data['low'])).iloc[-1], 2)
        }
    except:
        return {"R1": 0, "R2": 0, "S1": 0, "S2": 0}

# 3. Swing Seviyeleri
def detect_swing_levels(data):
    try:
        recent_data = data[-90:].copy()
        recent_data['high'] = recent_data['high'].round(1)
        recent_data['low'] = recent_data['low'].round(1)
        swing_highs = recent_data[recent_data['high'] == recent_data['high'].rolling(10, min_periods=1).max()]['high']
        swing_lows = recent_data[recent_data['low'] == recent_data['low'].rolling(10, min_periods=1).min()]['low']
        return {"highs": swing_highs.dropna().unique().tolist(), "lows": swing_lows.dropna().unique().tolist()}
    except:
        return {"highs": [], "lows": []}

# 4. Hacim Profili (Son 3 Ay)
def calculate_volume_profile(data):
    try:
        recent_data = data[-63:].copy()
        recent_data['price_bins'] = (recent_data['close'] / 0.10).round() * 0.10
        return recent_data.groupby('price_bins')['volume'].sum().nlargest(5).index.round(2).tolist()
    except:
        return []

# 5. Destek ve Direnç Filtreleme (Son 3 Ay)
def filter_supports(levels, latest_price, data):
    recent_supports = [l for l in levels if l > 0 and l < latest_price]
    last_3_months_low = data[-63:]['low'].min()
    return sorted([l for l in recent_supports if l > last_3_months_low], reverse=True)[:4]

def filter_resistances(levels, latest_price):
    return sorted([l for l in levels if l > 0 and l > latest_price])[:4]

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

@app.route('/stock/<ticker>', methods=['GET'])
def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        
        
        try:
            hist = stock.history(period="5y")
            if hist.empty:
                hist = stock.history(period="max")  # Eğer 5 yıllık veri yoksa, maksimum veriyi al
        except Exception as e:
            print(f"Hata oluştu: {e}")
            hist = stock.history(period="max")  # Hata durumunda da maksimum veriyi al

# Reset index ile tarih sütununu bağımsız hale getir
        hist = hist.reset_index()
        
        hist.rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"
        }, inplace=True)
        
    
        hist['date'] = pd.to_datetime(hist['date'])
        hist['rsi'] = compute_rsi(hist['close']).round(2)
        hist['ema_12'] = ema(hist['close'], 12)
        hist['ema_26'] = ema(hist['close'], 26)
        hist['macd'] = (hist['ema_12'] - hist['ema_26']).round(2)
        hist['macd_signal'] = ema(hist['macd'], 9).round(2)

# VWAP hesaplama
        hist['vwap'] = (hist['high'] + hist['low'] + hist['close']) / 3 * hist['volume']
        hist['vwap'] = (hist['vwap'].cumsum() / hist['volume'].cumsum()).round(2)

# Tarihi formatla
        hist['date'] = hist['date'].dt.strftime('%Y-%m-%d')

# Gereksiz sütunları kaldır
        hist.drop(columns=['ema_12', 'ema_26'], inplace=True)

        # hist['date'] = pd.to_datetime(hist['date'])
        # hist['rsi'] = hist.ta.rsi(length=14).round(2)
        # macd = hist.ta.macd(fast=12, slow=26, signal=9)
        # hist['macd'] = macd['MACD_12_26_9'].round(2)
        # hist['macd_signal'] = macd['MACDs_12_26_9'].round(2)
        # hist['vwap'] = hist.ta.vwap(high='high', low='low', close='close', volume='volume').iloc[:, 0].round(2)
        # hist['date'] = hist['date'].dt.strftime('%Y-%m-%d')

        latest_price = round(hist['close'].iloc[-1], 2)
        fib_levels = calculate_fibonacci_levels(hist)
        pivot_levels = calculate_pivot_levels(hist)
        swing_levels = detect_swing_levels(hist)
        volume_profile = calculate_volume_profile(hist)
        
        all_supports = fib_levels + [pivot_levels["S1"], pivot_levels["S2"]] + swing_levels["lows"] + volume_profile
        all_resistances = fib_levels + [pivot_levels["R1"], pivot_levels["R2"]] + swing_levels["highs"] + volume_profile
        
        supports = filter_supports(all_supports, latest_price, hist)
        resistances = filter_resistances(all_resistances, latest_price)
        
        
        if len(supports) == 0:
            supports.append(latest_price)

        return jsonify({
            "ticker": ticker.replace(".IS", ""),
            "price": latest_price,
            "supports": supports,
            "resistances": resistances,
            "pivot_levels": pivot_levels,
            "indicators": {
                "rsi": hist['rsi'].iloc[-1],
                "macd": hist['macd'].iloc[-1],
                "macd_signal": hist['macd_signal'].iloc[-1]
            },
            "historical_data": hist[['date', 'open', 'high', 'low', 'close', 'volume', 'rsi', 'macd', 'macd_signal', 'vwap']].dropna().round(2).to_dict(orient='records')
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(port=8080, debug=True)
