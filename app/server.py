import ccxt, os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import pandas as pd

# Load API keys
load_dotenv()

exchange = ccxt.coinbaseadvanced({
    "apiKey": os.getenv("COINBASE_KEY"),
    "secret": os.getenv("COINBASE_SECRET"),
    "password": os.getenv("COINBASE_PASSPHRASE", "")
})

app = Flask(__name__)

symbol = "ETH/USDC"
timeframe = "15m"
atr_len = 14
atr_mult_stop = 2.8
risk_pct = 0.02   # 2% risk per trade

def fetch_data():
    candles = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
    return pd.DataFrame(candles, columns=["time","open","high","low","close","volume"])

def calc_atr(df, length=14):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(length).mean().iloc[-1]

def get_size():
    df = fetch_data()
    atr = calc_atr(df, atr_len)
    balance = exchange.fetch_balance()
    usdc_balance = balance["total"]["USDC"]
    usd_risk = usdc_balance * risk_pct
    size = usd_risk / (atr_mult_stop * atr)
    return size

@app.route("/tv", methods=["POST"])
def webhook():
    data = request.json or {}
    side = data.get("side", "").upper()   # "BUY" or "SELL"

    try:
        size = get_size()

        if side not in ["BUY", "SELL"]:
            return jsonify({"status": "error", "message": f"Invalid side: {side}"}), 400

        order = exchange.create_market_order(symbol, side, size)
        return jsonify({"status": "ok", "side": side, "size": size, "order": order})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == "__main__":
    app.run(port=5000, debug=True)
