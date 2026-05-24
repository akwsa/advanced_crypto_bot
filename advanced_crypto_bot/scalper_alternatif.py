"""
Indodax Scalping Bot - EMA 9/21 + RSI + Volume
Modal: Rp 10.000.000 | Pair: BTC/IDR (Spot)
Strategi: Multi-confluence scalper (EMA crossover + RSI filter + Volume confirmation)
"""

import hashlib
import hmac
import time
import logging
import urllib.parse

import requests
import numpy as np

# ============================================================================
# KONFIGURASI - ISI API KEY DARI INDODAX
# ============================================================================

API_KEY = "YOUR_API_KEY"
SECRET_KEY = "YOUR_SECRET_KEY"

PAIR = "btc_idr"
SYMBOL = "BTCIDR"
TIMEFRAME = 15  # menit (1, 15, 30, 60)
MODAL_IDR = 10_000_000
TRADE_AMOUNT_IDR = int(MODAL_IDR * 0.10)  # 10% modal per posisi = Rp 1.000.000
MAX_DAILY_LOSS = 0.03  # 3% max daily loss

# Indikator
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 9
RSI_BUY_MAX = 70
RSI_BUY_MIN = 40
RSI_SELL_MAX = 60
RSI_SELL_MIN = 30
VOL_MULTIPLIER = 1.2

# Risk Management
STOP_LOSS_PCT = 0.005   # 0.5%
TAKE_PROFIT_PCT = 0.01  # 1.0%
TRAILING_STOP_PCT = 0.003  # 0.3%
COOLDOWN_CANDLES = 2

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("scalper.log")],
)
log = logging.getLogger("scalper")

# ============================================================================
# INDODAX API
# ============================================================================

BASE_URL = "https://indodax.com"
TAPI_URL = f"{BASE_URL}/tapi"


def private_request(method, params=None):
    body = {"method": method, "timestamp": int(time.time() * 1000), "recvWindow": 5000}
    if params:
        body.update(params)
    body_encoded = urllib.parse.urlencode(body)
    sign = hmac.new(SECRET_KEY.encode(), body_encoded.encode(), hashlib.sha512).hexdigest()
    headers = {"Key": API_KEY, "Sign": sign}
    r = requests.post(TAPI_URL, data=body, headers=headers, timeout=10)
    data = r.json()
    if data.get("success") != 1:
        log.error(f"API Error [{method}]: {data.get('error')}")
        return None
    return data["return"]


def get_balance():
    info = private_request("getInfo")
    if not info:
        return 0, 0.0
    return int(info["balance"]["idr"]), float(info["balance"]["btc"])


def place_order(order_type, price, amount_idr=None, amount_btc=None):
    params = {"pair": PAIR, "type": order_type, "price": price}
    if order_type == "buy" and amount_idr:
        params["idr"] = amount_idr
    elif order_type == "sell" and amount_btc:
        params["btc"] = f"{amount_btc:.8f}"
    result = private_request("trade", params)
    if result:
        log.info(f"Order {order_type.upper()} @ {price:,} | ID: {result.get('order_id')}")
    return result


# ============================================================================
# MARKET DATA
# ============================================================================


def get_ohlc(limit=100):
    now = int(time.time())
    start = now - (limit * TIMEFRAME * 60)
    url = f"{BASE_URL}/tradingview/history_v2?symbol={SYMBOL}&tf={TIMEFRAME}&from={start}&to={now}"
    r = requests.get(url, timeout=10)
    data = r.json()
    if not data:
        return None
    closes = np.array([float(c["Close"]) for c in data])
    volumes = np.array([float(c["Volume"]) for c in data])
    return closes, volumes


def get_ticker():
    r = requests.get(f"{BASE_URL}/api/ticker/{PAIR}", timeout=10)
    t = r.json()["ticker"]
    return {"last": int(t["last"]), "buy": int(t["buy"]), "sell": int(t["sell"])}


# ============================================================================
# INDIKATOR
# ============================================================================


def ema(data, period):
    result = np.zeros_like(data)
    k = 2.0 / (period + 1)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = data[i] * k + result[i - 1] * (1 - k)
    return result


def rsi(data, period):
    deltas = np.diff(data)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.zeros(len(data))
    avg_loss = np.zeros(len(data))
    avg_gain[period] = gains[:period].mean()
    avg_loss[period] = losses[:period].mean()
    for i in range(period + 1, len(data)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period
    rs = np.divide(avg_gain, avg_loss, out=np.zeros_like(avg_gain), where=avg_loss != 0)
    result = 100.0 - (100.0 / (1.0 + rs))
    result[:period] = 50.0
    return result


# ============================================================================
# BOT UTAMA
# ============================================================================


class ScalpingBot:
    def __init__(self):
        self.in_position = False
        self.entry_price = 0.0
        self.amount_btc = 0.0
        self.stop_loss = 0.0
        self.take_profit = 0.0
        self.highest = 0.0
        self.daily_pnl = 0.0
        self.trade_count = 0
        self.cooldown = 0

    def analyze(self):
        ohlc = get_ohlc(100)
        if ohlc is None:
            return "HOLD"
        closes, volumes = ohlc
        ema_f = ema(closes, EMA_FAST)
        ema_s = ema(closes, EMA_SLOW)
        rsi_val = rsi(closes, RSI_PERIOD)
        vol_avg = volumes[-20:].mean()

        log.info(
            f"EMA9: {ema_f[-1]:,.0f} | EMA21: {ema_s[-1]:,.0f} | "
            f"RSI: {rsi_val[-1]:.1f} | Vol: {volumes[-1]:,.0f} (avg {vol_avg:,.0f})"
        )

        # BUY: EMA9 cross above EMA21 + RSI + Volume
        if (ema_f[-2] <= ema_s[-2] and ema_f[-1] > ema_s[-1]
                and RSI_BUY_MIN <= rsi_val[-1] <= RSI_BUY_MAX
                and volumes[-1] >= vol_avg * VOL_MULTIPLIER):
            return "BUY"

        # SELL: EMA9 cross below EMA21 + RSI + Volume
        if (ema_f[-2] >= ema_s[-2] and ema_f[-1] < ema_s[-1]
                and RSI_SELL_MIN <= rsi_val[-1] <= RSI_SELL_MAX
                and volumes[-1] >= vol_avg * VOL_MULTIPLIER):
            return "SELL"

        return "HOLD"

    def check_exit(self, price):
        if not self.in_position:
            return False
        if price > self.highest:
            self.highest = price
        if price <= self.stop_loss:
            log.warning(f"⛔ STOP LOSS @ {price:,}")
            return True
        if price >= self.take_profit:
            log.info(f"✅ TAKE PROFIT @ {price:,}")
            return True
        if price > self.entry_price * (1 + TRAILING_STOP_PCT):
            if price <= self.highest * (1 - TRAILING_STOP_PCT):
                log.info(f"🔄 TRAILING STOP @ {price:,}")
                return True
        return False

    def buy(self):
        ticker = get_ticker()
        price = ticker["sell"]
        idr_bal = get_balance()[0]
        amount_idr = min(TRADE_AMOUNT_IDR, int(idr_bal * 0.95))
        if amount_idr < 50000:
            log.warning("Saldo IDR tidak cukup")
            return
        result = place_order("buy", price, amount_idr=amount_idr)
        if result:
            self.in_position = True
            self.entry_price = price
            self.amount_btc = amount_idr / price
            self.stop_loss = price * (1 - STOP_LOSS_PCT)
            self.take_profit = price * (1 + TAKE_PROFIT_PCT)
            self.highest = price
            self.cooldown = COOLDOWN_CANDLES
            self.trade_count += 1
            log.info(f"📈 BUY @ {price:,} | SL: {self.stop_loss:,.0f} | TP: {self.take_profit:,.0f}")

    def sell(self):
        if not self.in_position:
            return
        ticker = get_ticker()
        price = ticker["buy"]
        btc_bal = get_balance()[1]
        amount = min(self.amount_btc, btc_bal)
        if amount < 0.00001:
            self.in_position = False
            return
        result = place_order("sell", price, amount_btc=amount)
        if result:
            pnl = (price - self.entry_price) / self.entry_price * 100
            pnl_idr = (price - self.entry_price) * amount
            self.daily_pnl += pnl_idr
            self.in_position = False
            self.cooldown = COOLDOWN_CANDLES
            log.info(f"📉 SELL @ {price:,} | PnL: {pnl:+.2f}% (Rp {pnl_idr:+,.0f}) | Total: Rp {self.daily_pnl:+,.0f}")

    def run(self):
        log.info("=" * 50)
        log.info(f"🚀 Indodax Scalper | {PAIR} | TF:{TIMEFRAME}m | Modal: Rp {MODAL_IDR:,}")
        log.info(f"   EMA {EMA_FAST}/{EMA_SLOW} + RSI({RSI_PERIOD}) + Vol({VOL_MULTIPLIER}x)")
        log.info(f"   SL: {STOP_LOSS_PCT*100}% | TP: {TAKE_PROFIT_PCT*100}% | Trail: {TRAILING_STOP_PCT*100}%")
        log.info("=" * 50)

        idr, btc = get_balance()
        log.info(f"💰 Rp {idr:,} | {btc:.8f} BTC")

        while True:
            try:
                if self.daily_pnl <= -(MODAL_IDR * MAX_DAILY_LOSS):
                    log.error(f"🛑 Max daily loss! PnL: Rp {self.daily_pnl:,.0f}")
                    break

                price = get_ticker()["last"]

                if self.in_position and self.check_exit(price):
                    self.sell()
                    time.sleep(5)
                    continue

                if self.cooldown > 0:
                    self.cooldown -= 1
                else:
                    signal = self.analyze()
                    if signal == "BUY" and not self.in_position:
                        self.buy()
                    elif signal == "SELL" and self.in_position:
                        self.sell()

                log.info(f"⏳ Next: {TIMEFRAME}m | Trades: {self.trade_count} | PnL: Rp {self.daily_pnl:+,.0f}")
                time.sleep(TIMEFRAME * 60)

            except KeyboardInterrupt:
                log.info("Bot dihentikan")
                break
            except Exception as e:
                log.error(f"Error: {e}")
                time.sleep(30)

        if self.in_position:
            self.sell()
        log.info(f"📊 Done | Trades: {self.trade_count} | PnL: Rp {self.daily_pnl:+,.0f}")


if __name__ == "__main__":
    ScalpingBot().run()
