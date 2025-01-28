from flask import Flask, jsonify, render_template, request
import yfinance as yf
from scipy.signal import find_peaks

app = Flask(__name__, template_folder="html")


def calculate_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_support_resistance(data, levels=3, min_distance=10, current_price=None):
    lows = data['Low']
    highs = data['High']

    if current_price is None:
        current_price = data['Close'].iloc[-1]

    price_range = 0.10  # %10
    lower_bound = current_price * (1 - price_range)
    upper_bound = current_price * (1 + price_range)

    support_indices, _ = find_peaks(-lows, distance=min_distance)
    support_levels = lows.iloc[support_indices]
    # Güncel fiyata yakın destek seviyelerini filtrele
    support_levels = support_levels[(support_levels >= lower_bound) & (support_levels <= upper_bound)]
    support_levels = support_levels.sort_values().unique()[:levels]

    resistance_indices, _ = find_peaks(highs, distance=min_distance)
    resistance_levels = highs.iloc[resistance_indices]
    resistance_levels = resistance_levels[(resistance_levels >= lower_bound) & (resistance_levels <= upper_bound)]
    resistance_levels = resistance_levels.sort_values(ascending=False).unique()[:levels]

    return support_levels, resistance_levels


@app.route('/api/stock/<string:symbol>', methods=['GET'])
def get_stock_data(symbol):
    stock_name = symbol
    if not stock_name:
        return jsonify({"error": "Please provide a stock name using the 'name' parameter."}), 400

    stock = yf.Ticker(stock_name)
    data = stock.history(period="2y", interval="1d")

    if data.empty:
        return jsonify({"error": "No data found for the given stock."}), 404

    current_price = data['Close'].iloc[-1]

    support_levels, resistance_levels = calculate_support_resistance(data, current_price=current_price)

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
    # from waitress import serve
    # serve(app, host="0.0.0.0", port=5000)
    app.run(debug=True)