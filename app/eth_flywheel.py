import ccxt, os, time
import pandas as pd
from dotenv import load_dotenv

# Load API credentials
load_dotenv()

exchange = ccxt.coinbaseadvanced({
    "apiKey": os.getenv("COINBASE_KEY"),
    "secret": os.getenv("COINBASE_SECRET"),
    "password": os.getenv("COINBASE_PASSPHRASE", "")
})

symbol = "ETH/USDC"
timeframe = "1m"   # faster signals for testing

class FlywheelBot:
    def __init__(self):
        # Aggressive Config for $75 account
        self.risk_pct = 0.10       # 10% per trade base risk
        self.atr_len = 7           # shorter ATR window = faster reaction
        self.atr_mult_stop = 1.0   # tight stop
        self.atr_mult_trail = 1.5  # close trail
        self.add_step_atr = 0.3    # add quickly
        self.max_adds = 5          # allow multiple adds

        # State
        self.base_entry = None
        self.last_add_price = None
        self.adds_done = 0
        self.in_position = False
        self.side = None

    def fetch_data(self):
        candles = exchange.fetch_ohlcv(symbol, timeframe, limit=200)
        return pd.DataFrame(candles, columns=["time","open","high","low","close","volume"])

    def calc_atr(self, df):
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(self.atr_len).mean().iloc[-1]

    def get_balance_usdc(self):
        balance = exchange.fetch_balance()
        return balance["total"]["USDC"]

    def run(self):
        while True:
            try:
                df = self.fetch_data()
                price = df["close"].iloc[-1]
                atr = self.calc_atr(df)

                # Position sizing based on risk % (USDC only)
                balance = self.get_balance_usdc()
                usd_risk = balance * self.risk_pct
                size = usd_risk / price   # convert USDC to ETH size

                # Strategy logic (EMA cross as entry condition)
                df["ema_fast"] = df["close"].ewm(span=10).mean()
                df["ema_slow"] = df["close"].ewm(span=30).mean()
                long_signal = df["ema_fast"].iloc[-1] > df["ema_slow"].iloc[-1]

                print(f"[INFO] Price={price:.2f}, Balance={balance:.2f} USDC, In Position={self.in_position}")

                # ENTRY
                if not self.in_position and long_signal:
                    print(f"ENTER LONG @ {price}, spend {usd_risk:.2f} USDC, size ~ {size:.4f} ETH")
                    exchange.create_market_buy_order(symbol, size, params={"cost": usd_risk})
                    self.base_entry = price
                    self.last_add_price = price
                    self.adds_done = 0
                    self.side = "long"
                    self.in_position = True

                # PYRAMID adds
                if self.in_position and self.side == "long" and self.adds_done < self.max_adds:
                    if price >= self.last_add_price + self.add_step_atr * atr:
                        print(f"ADD LONG @ {price}, spend {usd_risk:.2f} USDC, size ~ {size:.4f} ETH")
                        exchange.create_market_buy_order(symbol, size, params={"cost": usd_risk})
                        self.last_add_price = price
                        self.adds_done += 1

                # EXIT (trailing stop)
                if self.in_position and self.side == "long":
                    trail_stop = max(
                        self.base_entry - self.atr_mult_stop * atr,
                        df["high"].rolling(self.atr_len).max().iloc[-1] - self.atr_mult_trail * atr
                    )
                    if price <= trail_stop:
                        qty = exchange.fetch_balance()["total"]["ETH"]
                        print(f"EXIT LONG @ {price}, selling {qty:.4f} ETH")
                        exchange.create_market_sell_order(symbol, qty)
                        self.in_position = False
                        self.base_entry = None
                        self.adds_done = 0
                        self.side = None

            except Exception as e:
                print("Error:", e)

            time.sleep(60)   # check once per minute


if __name__ == "__main__":
    bot = FlywheelBot()
    bot.run()
