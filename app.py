from flask import Flask, jsonify
import yfinance as yf
import pandas as pd
import pandas_ta as ta

app = Flask(__name__)

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
        weekly_data = data[-30:].resample('W', on='date').agg({
            'high': 'max', 'low': 'min', 'close': 'last'
        }).dropna()
        if len(weekly_data) == 0: return {"R1": 0, "R2": 0, "S1": 0, "S2": 0}
        pp = (weekly_data['high'] + weekly_data['low'] + weekly_data['close']) / 3
        return {
            "R1": round(float((2 * pp) - weekly_data['low']).iloc[-1], 2),
            "R2": round(float(pp + (weekly_data['high'] - weekly_data['low'])).iloc[-1], 2),
            "S1": round(float((2 * pp) - weekly_data['high']).iloc[-1], 2),
            "S2": round(float(pp - (weekly_data['high'] - weekly_data['low'])).iloc[-1], 2)
        }
    except: return {"R1": 0, "R2": 0, "S1": 0, "S2": 0}

# 3. Swing Seviyeleri
def detect_swing_levels(data):
    try:
        recent_data = data[-90:].copy()
        recent_data['high'] = recent_data['high'].round(1)
        recent_data['low'] = recent_data['low'].round(1)
        swing_highs = recent_data[recent_data['high'] == recent_data['high'].rolling(10, min_periods=1).max()]['high']
        swing_lows = recent_data[recent_data['low'] == recent_data['low'].rolling(10, min_periods=1).min()]['low']
        return {"highs": swing_highs.dropna().unique().tolist(), "lows": swing_lows.dropna().unique().tolist()}
    except Exception as e:
        print(f"Swing Hata: {e}")
        return {"highs": [], "lows": []}

# 4. Hacim Profili
def calculate_volume_profile(data):
    try:
        data['price_bins'] = (data['close'] / 0.10).round() * 0.10
        return data.groupby('price_bins')['volume'].sum().nlargest(5).index.round(2).tolist()
    except Exception as e:
        print(f"Hacim Hata: {e}")
        return []

# 5. Seviye Filtreleme (0 ve Geçersiz Değerleri Temizle)
def filter_supports(levels, latest_price):
    return sorted([l for l in levels if l > 0 and l < latest_price], reverse=True)[:4]

def filter_resistances(levels, latest_price):
    return sorted([l for l in levels if l > 0 and l > latest_price])[:4]

@app.route('/stock/<ticker>', methods=['GET'])
def get_stock_data(ticker):
    try:
        # Veri Çekme
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5y").reset_index()
        hist.rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"
        }, inplace=True)
        
        if hist.empty: return jsonify({"error": "Veri bulunamadı"}), 404

        # Göstergeler
        vwap_data = hist.ta.vwap(high='high', low='low', close='close', volume='volume')
        hist['vwap'] = vwap_data.iloc[:, 0].round(2)
        hist['rsi'] = hist.ta.rsi(length=14).round(2)
        macd = hist.ta.macd(fast=12, slow=26, signal=9)
        hist['macd'] = macd['MACD_12_26_9'].round(2)
        hist['macd_signal'] = macd['MACDs_12_26_9'].round(2)
        hist['adx'] = hist.ta.adx()['ADX_14'].round(2)
        hist['date'] = hist['date'].dt.strftime('%Y-%m-%d')

        # Seviyeler
        latest_price = round(hist['close'].iloc[-1], 2)
        fib_levels = calculate_fibonacci_levels(hist)
        pivot_levels = calculate_pivot_levels(hist)
        swing_levels = detect_swing_levels(hist)
        volume_profile = calculate_volume_profile(hist)
        
        # Moving Average'lar (0 Kontrollü)
        sma_50 = hist['close'].rolling(50).mean().dropna()
        sma_50 = round(sma_50.iloc[-1], 2) if not sma_50.empty and sma_50.iloc[-1] > 0 else None
        sma_200 = hist['close'].rolling(200).mean().dropna()
        sma_200 = round(sma_200.iloc[-1], 2) if not sma_200.empty and sma_200.iloc[-1] > 0 else None
        ema_50 = hist['close'].ewm(span=50).mean().dropna()
        ema_50 = round(ema_50.iloc[-1], 2) if not ema_50.empty and ema_50.iloc[-1] > 0 else None

        # Tüm Seviyeler
        all_supports = fib_levels + [pivot_levels["S1"], pivot_levels["S2"]] + swing_levels["lows"] + volume_profile
        all_supports += [sma_200] if sma_200 else []
        all_resistances = fib_levels + [pivot_levels["R1"], pivot_levels["R2"]] + swing_levels["highs"] + volume_profile
        all_resistances += [sma_50, ema_50] if sma_50 and ema_50 else []

        # Filtrele
        supports = filter_supports(all_supports, latest_price)
        resistances = filter_resistances(all_resistances, latest_price)

        # Tarihsel Veri
        historical_data = hist[['date', 'open', 'high', 'low', 'close', 'volume', 'rsi', 'macd', 'macd_signal', 'adx', 'vwap']]
        historical_data = historical_data.dropna().round(2).to_dict(orient='records')

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
            "historical_data": historical_data
        })
    except Exception as e: return jsonify({"error": str(e)}), 500

if __name__ == '__main__': app.run(port=8080, debug=True)