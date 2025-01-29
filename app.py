import datetime
from flask import Flask, jsonify
import yfinance as yf
from scipy.signal import find_peaks
from flask_cors import CORS
import pandas as pd
import numpy as np

app = Flask(__name__, template_folder="html")

CORS(app) 



def calculate_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi



def calculate_support_resistance(data, levels=3, min_distance=5):
    lows = data['Low'].values
    highs = data['High'].values

    # Destek seviyelerini bul (dip noktaları)
    support_indices, _ = find_peaks(-lows, distance=min_distance, prominence=0.5)
    support_levels = np.sort(lows[support_indices])

    # Direnç seviyelerini bul (zirve noktaları)
    resistance_indices, _ = find_peaks(highs, distance=min_distance, prominence=0.5)
    resistance_levels = np.sort(highs[resistance_indices])[::-1]  # Büyükten küçüğe sırala

    # En yakın 3 seviyeyi seç
    support_levels = np.unique(support_levels)[:levels]
    resistance_levels = np.unique(resistance_levels)[:levels]

    return support_levels.tolist(), resistance_levels.tolist()


def get_stock_data(ticker):
    stock = yf.Ticker(ticker)
    
    # İlk olarak 2 yıllık veri çek
    data = stock.history(period="2y", interval="1d")

    # Eğer veri boş değilse en eski tarihi al
    if not data.empty:
        oldest_date = data.index[0].tz_localize(None)  # Zaman dilimini kaldır
        two_years_ago = pd.Timestamp(datetime.datetime.today() - datetime.timedelta(days=730))  

        if oldest_date > two_years_ago:  # 2 yıl öncesine ulaşmıyorsa tüm veriyi al
            data = stock.history(period="max", interval="1d")
    
    return data


@app.route('/api/stock/<string:symbol>', methods=['GET'])
def stock_data(symbol):
    stock_name = symbol
    if not stock_name:
        return jsonify({"error": "Please provide a stock name using the 'name' parameter."}), 400

    stock = yf.Ticker(stock_name)
    data = get_stock_data(symbol)
    
    if data.empty:
        return jsonify({"error": "No data found for the given stock."}), 404

    current_price = data['Close'].iloc[-1]

    support_levels, resistance_levels = calculate_support_resistance(data)

    # Prepare RSI data
    data['RSI'] = calculate_rsi(data)
    rsi_data = data[['RSI']].dropna()
    rsi_with_time = [
        {"time": str(index), "rsi": round(row['RSI'], 2)}
        for index, row in rsi_data.iterrows()
    ]

    # Prepare historical data
    historical_data = [
        {
            "time": str(index),
            "open": round(row['Open'], 2),
            "high": round(row['High'], 2),
            "low": round(row['Low'], 2),
            "close": round(row['Close'], 2)
        }
        for index, row in data.iterrows()
    ]

    # Prepare response
    response = {
        "symbol": stock_name,
        "current_price": round(current_price, 2),
        "levels": {
            "supports": [round(level, 2) for level in support_levels],
            "resistances": [round(level, 2) for level in resistance_levels]
        },
        "rsi": rsi_with_time,
        "historical_data": historical_data
    }

    return jsonify(response)

if __name__ == '__main__':
    app.run(debug=True)