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

def calculate_fibonacci_levels(data):
    if data.empty:
        return []
    recent_data = data[-252:]
    max_price = recent_data['high'].max()
    min_price = recent_data['low'].min()
    return [
        round(min_price + (max_price - min_price) * 0.382, 2),
        round(min_price + (max_price - min_price) * 0.5, 2),
        round(min_price + (max_price - min_price) * 0.618, 2)
    ]

def calculate_pivot_levels(data):
    try:
        if data.empty or len(data) < 2:
            return {"R1": 0, "R2": 0, "S1": 0, "S2": 0}
        
        data['date'] = pd.to_datetime(data['date'])
        weekly_data = data[-30:].resample('W', on='date').agg({
            'high': 'max', 'low': 'min', 'close': 'last'
        }).dropna()
        
        if weekly_data.empty:
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

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

@app.route('/stock/<ticker>', methods=['GET'])
def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        
        try:
            hist = stock.history(period="5y")
            if hist.empty:
                hist = stock.history(period="max")
        except:
            hist = stock.history(period="max")

        if hist.empty:
            return jsonify({"error": "Veri bulunamadı"}), 404
        
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
        
        hist['vwap'] = (hist['high'] + hist['low'] + hist['close']) / 3 * hist['volume']
        hist['vwap'] = (hist['vwap'].cumsum() / hist['volume'].cumsum()).round(2)
        
        hist['date'] = hist['date'].dt.strftime('%Y-%m-%d')
        hist.drop(columns=['ema_12', 'ema_26'], inplace=True)
        
        latest_price = round(hist['close'].iloc[-1], 2) if not hist['close'].dropna().empty else 0
        
        fib_levels = calculate_fibonacci_levels(hist)
        pivot_levels = calculate_pivot_levels(hist)
        
        if hist['rsi'].dropna().empty:
            rsi_value, macd_value, macd_signal_value = None, None, None
        else:
            rsi_value = hist['rsi'].iloc[-1]
            macd_value = hist['macd'].iloc[-1]
            macd_signal_value = hist['macd_signal'].iloc[-1]
        
        return jsonify({
            "ticker": ticker.replace(".IS", ""),
            "price": latest_price,
            "pivot_levels": pivot_levels,
            "indicators": {
                "rsi": rsi_value,
                "macd": macd_value,
                "macd_signal": macd_signal_value
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(port=8080, debug=True)
