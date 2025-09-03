#!/usr/bin/env python3
"""
Delta Exchange Spike Notifier - Perpetual Futures Only
Monitors crypto prices and sends Telegram alerts for spikes.
Optionally places tiny market orders for testing.
"""

import os
import json
import time
import math
import threading
import hmac
import hashlib
from collections import deque, defaultdict
from datetime import datetime
import requests
import websocket
import ssl
import numpy as np
import certifi

# ---------------------------
# Config
# ---------------------------
REST_BASE = "https://api.india.delta.exchange"
WS_URL = "wss://socket.india.delta.exchange"
TOP_N_SYMBOLS = int(os.getenv("TOP_N_SYMBOLS", "120"))
MIN_TURNOVER_USD = float(os.getenv("MIN_TURNOVER_USD", "5000"))
CANDLES_SAVE_MIN = 360
PCT_SPIKE_THRESHOLD = float(os.getenv("PCT_SPIKE_THRESHOLD", "2.0"))
ALERT_SCORE_THRESHOLD = float(os.getenv("ALERT_SCORE_THRESHOLD", "0.65"))
ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", "900"))



# CANDLES_SAVE_MIN = 360  # store up to last N minutes per symbol (6 hours)
# FOLLOWUP_WATCH_MIN = 30  # watch each alerted symbol for this many minutes to detect quick reverts


# PCT_SPIKE_THRESHOLD = 0.01   # 0.01% change, basically any movement
# ALERT_SCORE_THRESHOLD = 0.0   # Any spike score triggers alert
# ALERT_COOLDOWN_SEC = 5        # Alerts every 5 seconds (for testing)



WEIGHTS = {
    "price": 0.25,
    "volume": 0.20,
    "momentum": 0.15,
    "candle_quality": 0.10,
    "htf_alignment": 0.10,
    "depth": 0.10,
}

# ---------------------------
# Telegram Bot
# ---------------------------
TELEGRAM_BOT_TOKEN = "8256148964:AAGtAwiEcLIRMkiLOmPHimWGTBdzmGQOUTc"
TELEGRAM_CHAT_ID = "630658837"

# ---------------------------
# Delta API creds
# ---------------------------
API_KEY = "cgCYh2dZfpozKKTkeBygVpuZsoELlD"
API_SECRET = "RCWft2ptKL6kKRuY7Az8dZvdCB6TGg6O6IMreRRzUe7VACCmWXC2hlcy4BOP"

# ---------------------------
# State
# ---------------------------
candles_1m = defaultdict(lambda: deque(maxlen=CANDLES_SAVE_MIN))
tickers = {}
last_alert_ts = {}
session = requests.Session()
session.headers.update({"Accept": "application/json"})

# ---------------------------
# Helper functions
# ---------------------------
def send_telegram_alert(text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    try:
        resp = session.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"✅ Telegram alert sent: {text[:50]}...")
        else:
            print(f"❌ Telegram failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"❌ Telegram exception: {e}")

def fetch_top_symbols_by_turnover(n=TOP_N_SYMBOLS):
    try:
        url = f"{REST_BASE}/v2/tickers"
        params = {"contract_types": "perpetual_futures"}
        resp = session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        arr = [t for t in data.get("result", []) if t.get("contract_type") == "perpetual_futures"]
        arr_sorted = sorted(arr, key=lambda x: float(x.get("turnover_usd") or 0), reverse=True)
        symbols = [t["symbol"] for t in arr_sorted if float(t.get("turnover_usd") or 0) >= MIN_TURNOVER_USD]
        return symbols[:n]
    except Exception as e:
        print(f"❌ Failed to fetch symbols: {e}")
        return ["BTCUSD", "ETHUSD", "SOLUSD"]

def safe_mean(xs):
    return float(np.mean(xs)) if xs else 0.0

def compute_scores(symbol):
    c = list(candles_1m[symbol])
    if len(c) < 16:
        return None, None, "not_enough_candles"

    close_now = float(c[-1]["close"])
    close_15 = float(c[-16]["close"])
    pct15 = (close_now / close_15 - 1.0) * 100.0
    if abs(pct15) < PCT_SPIKE_THRESHOLD:
        return None, None, "below_threshold"
    direction = 1 if pct15 >= 0 else -1

    vol_last15 = sum([float(x.get("volume", 0) or 0) for x in c[-15:]])
    avg_1m = safe_mean([float(x.get("volume", 0) or 0) for x in c[-min(180, len(c)):]])
    vol_ratio = vol_last15 / max(avg_1m * 15.0, 1e-9)

    mom = (close_now / float(c[-4]["close"]) - 1.0) * 100.0 if len(c) >= 4 else 0.0

    agg_open = float(c[-15]["open"])
    agg_high = max(float(x["high"]) for x in c[-15:])
    agg_low = min(float(x["low"]) for x in c[-15:])
    agg_close = float(c[-1]["close"])
    candle_quality = abs(agg_close - agg_open) / max(agg_high - agg_low, 1e-9)

    closes = [float(x["close"]) for x in c]
    sma60 = safe_mean(closes[-60:]) if len(closes) >= 60 else safe_mean(closes)
    sma180 = safe_mean(closes[-180:]) if len(closes) >= 180 else safe_mean(closes)
    htf_alignment = 1.0 if (sma60 > sma180 and direction > 0) or (sma60 < sma180 and direction < 0) else 0.0

    score_price = min(abs(pct15) / 5.0, 1.0)
    score_vol = min(max((vol_ratio - 1.0) / 2.0, 0.0), 1.0)
    score_mom = max(min(mom / 2.0, 1.0), 0.0)
    score_candle = min(max(candle_quality, 0.0), 1.0)
    score_htf = htf_alignment
    score_depth = 0.5

    final = sum([
        WEIGHTS["price"] * score_price,
        WEIGHTS["volume"] * score_vol,
        WEIGHTS["momentum"] * score_mom,
        WEIGHTS["candle_quality"] * score_candle,
        WEIGHTS["htf_alignment"] * score_htf,
        WEIGHTS["depth"] * score_depth
    ])
    breakdown = {
        "pct15": pct15,
        "score_price": round(score_price,3),
        "vol_ratio": round(vol_ratio,3),
        "mom": round(mom,3),
        "candle_quality": round(candle_quality,3),
        "htf_alignment": score_htf,
        "final_score": round(final,4),
        "close_now": close_now
    }
    return final, breakdown, None

# ---------------------------
# WebSocket callbacks
# ---------------------------
def on_open(ws):
    print("🔌 WebSocket connected, subscribing...")
    top_symbols = fetch_top_symbols_by_turnover(TOP_N_SYMBOLS)
    print(f"📊 Monitoring {len(top_symbols)} symbols")
    sub_msg = {
        "type": "subscribe",
        "payload": {
            "channels": [
                {"name": "v2/ticker", "symbols": ["all"]},
                {"name": "candlestick_1m", "symbols": top_symbols},
            ]
        }
    }
    ws.send(json.dumps(sub_msg))
    print("✅ Subscribed to channels")
    send_telegram_alert("🚀 Delta Spike Notifier is now online and monitoring for price spikes!")

def on_message(ws, raw):
    try:
        msg = json.loads(raw)
    except:
        return
    mtype = msg.get("type")
    symbol = msg.get("symbol")
    if mtype and mtype.startswith("candlestick_") and symbol:
        # Check if all required fields are present and not None
        required_fields = ["open", "high", "low", "close"]
        if not all(msg.get(field) is not None for field in required_fields):
            return  # Skip this message if any required field is None
        
        candle = {
            "open": float(msg["open"]),
            "high": float(msg["high"]),
            "low": float(msg["low"]),
            "close": float(msg["close"]),
            "volume": float(msg.get("volume") or 0),
            "ts": int(msg.get("candle_start_time") or msg.get("timestamp") or int(time.time()*1000))
        }
        candles_1m[symbol].append(candle)
        try:
            final, breakdown, veto = compute_scores(symbol)
            if veto or final is None:
                return
            last = last_alert_ts.get(symbol, 0)
            if time.time() - last < ALERT_COOLDOWN_SEC:
                return
            if final >= ALERT_SCORE_THRESHOLD:
                txt = (f"🚨 *SPIKE ALERT* {symbol}\n"
                       f"Score: *{round(breakdown['final_score'],3)}*\n"
                       f"Change: *{round(breakdown['pct15'],3)}%* in 15m\n"
                       f"Volume: x{round(breakdown['vol_ratio'],2)}\n"
                       f"Price: ${breakdown['close_now']:.6f}\n"
                       f"Time: {datetime.now().strftime('%H:%M:%S')}")
                print(f"[DEBUG] {symbol} final score: {breakdown['final_score']:.3f}, pct15: {breakdown['pct15']:.3f}")
                if send_telegram_alert(txt):
                    last_alert_ts[symbol] = time.time()
        except Exception as e:
            print(f"❌ Score computation error: {e}")
    elif mtype == "v2/ticker" and symbol:
        tickers[symbol] = msg

def on_error(ws, err):
    print(f"❌ WebSocket error: {err}")

def on_close(ws, code, reason):
    print(f"🔌 WebSocket closed: {code} - {reason}")

# ---------------------------
# Main loop
# ---------------------------
def run():
    import signal
    running = True
    ws_instance = None

    def signal_handler(signum, frame):
        nonlocal running, ws_instance
        print("\n🛑 Ctrl+C received")
        running = False
        if ws_instance:
            try: ws_instance.close()
            except: pass
        threading.Timer(2.0, lambda: os._exit(0)).start()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    while running:
        try:
            print("🔄 Connecting to Delta Exchange...")
            ws_instance = websocket.WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            ws_thread = threading.Thread(
                target=lambda: ws_instance.run_forever(
                    ping_interval=20,
                    ping_timeout=10,
                    sslopt={"ca_certs": certifi.where()}
                ),
                daemon=True
            )
            ws_thread.start()
            while ws_thread.is_alive() and running:
                time.sleep(1)
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            if not running: break
            print("🔄 Reconnecting in 10s...")
            time.sleep(10)
    print("✅ Delta Spike Notifier stopped successfully")

# ---------------------------
# Entry
# ---------------------------
if __name__ == "__main__":
    print("🚀 Starting Delta Spike Notifier...")
    print(f"📱 Telegram Bot: {TELEGRAM_BOT_TOKEN[:10]}...")
    print(f"💬 Chat ID: {TELEGRAM_CHAT_ID}")
    print(f"🎯 Threshold: {PCT_SPIKE_THRESHOLD}%")
    print(f"📊 Monitoring top {TOP_N_SYMBOLS} symbols")
    print("="*50)
    run()
