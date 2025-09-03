# #!/usr/bin/env python3
# """
# Delta Exchange Spike Notifier
# Monitors cryptocurrency prices and sends Telegram alerts for significant spikes
# """

# import os
# import json
# import time
# import math
# import threading
# from collections import deque, defaultdict
# from datetime import datetime
# import requests
# import websocket
# import numpy as np

# # Configuration
# REST_BASE = "https://api.india.delta.exchange"
# WS_URL = "wss://socket.india.delta.exchange"
# TOP_N_SYMBOLS = int(os.getenv("TOP_N_SYMBOLS", "120"))
# MIN_TURNOVER_USD = float(os.getenv("MIN_TURNOVER_USD", "5000"))
# PCT_SPIKE_THRESHOLD = float(os.getenv("PCT_SPIKE_THRESHOLD", "2.0"))
# ALERT_SCORE_THRESHOLD = float(os.getenv("ALERT_SCORE_THRESHOLD", "0.65"))
# ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", "900"))
# CANDLES_SAVE_MIN = 360
# FOLLOWUP_WATCH_MIN = 30

# # Weights for scoring
# WEIGHTS = {
#     "price": 0.25,
#     "volume": 0.20,
#     "momentum": 0.15,
#     "candle_quality": 0.10,
#     "htf_alignment": 0.10,
#     "depth": 0.10,
# }

# # Telegram configuration
# TELEGRAM_BOT_TOKEN = "8256148964:AAGtAwiEcLIRMkiLOmPHimWGTBdzmGQOUTc"
# TELEGRAM_CHAT_ID = "630658837"

# if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
#     print("❌ ERROR: Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables")
#     print("Example:")
#     print("export TELEGRAM_BOT_TOKEN=your_bot_token_here")
#     print("export TELEGRAM_CHAT_ID=your_chat_id_here")
#     exit(1)

# # State variables
# candles_1m = defaultdict(lambda: deque(maxlen=CANDLES_SAVE_MIN))
# tickers = {}
# last_alert_ts = {}
# session = requests.Session()
# session.headers.update({"Accept": "application/json"})

# def send_telegram_alert(text, parse_mode="Markdown"):
#     """Send message to Telegram"""
#     url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
#     payload = {
#         "chat_id": TELEGRAM_CHAT_ID,
#         "text": text,
#         "parse_mode": parse_mode,
#         "disable_web_page_preview": True
#     }
#     try:
#         response = session.post(url, json=payload, timeout=10)
#         if response.status_code == 200:
#             print(f"✅ Telegram alert sent: {text[:50]}...")
#             return True
#         else:
#             print(f"❌ Telegram failed: {response.status_code} - {response.text}")
#             return False
#     except Exception as e:
#         print(f"❌ Telegram exception: {e}")
#         return False

# def fetch_top_symbols_by_turnover(n=TOP_N_SYMBOLS):
#     """Fetch top trading symbols by turnover"""
#     try:
#         url = f"{REST_BASE}/v2/tickers"
#         params = {"contract_types": "perpetual_futures"}
#         response = session.get(url, params=params, timeout=10)
#         response.raise_for_status()
#         data = response.json()
        
#         if not data.get("success"):
#             raise RuntimeError("Failed to fetch tickers")
        
#         arr = data["result"]
#         arr = [t for t in arr if t.get("symbol")]
#         arr_sorted = sorted(arr, key=lambda x: float(x.get("turnover_usd") or 0), reverse=True)
#         symbols = [t["symbol"] for t in arr_sorted if float(t.get("turnover_usd") or 0) >= MIN_TURNOVER_USD]
#         return symbols[:n]
#     except Exception as e:
#         print(f"❌ Failed to fetch symbols: {e}")
#         return ["BTCUSD", "ETHUSD", "SOLUSD"]  # fallback

# def safe_mean(xs):
#     """Safe mean calculation"""
#     return float(np.mean(xs)) if xs else 0.0

# def compute_scores(symbol):
#     """Compute spike scores for a symbol"""
#     c = list(candles_1m[symbol])
#     if len(c) < 16:
#         return None, None, "not_enough_candles"

#     close_now = float(c[-1]["close"])
#     close_15 = float(c[-16]["close"]) if len(c) >= 16 else float(c[0]["close"])
#     pct15 = (close_now / close_15 - 1.0) * 100.0

#     # Check if threshold is met
#     if abs(pct15) < PCT_SPIKE_THRESHOLD:
#         return None, None, "below_threshold"

#     direction = 1 if pct15 >= 0 else -1

#     # Volume analysis
#     vol_last15 = sum([float(x.get("volume", 0) or 0) for x in c[-15:]])
#     look_avg = c[-(min(180, len(c))):]
#     avg_1m = safe_mean([float(x.get("volume", 0) or 0) for x in look_avg])
#     avg_15m = max(avg_1m * 15.0, 1e-9)
#     vol_ratio = vol_last15 / avg_15m

#     # Momentum
#     close_3 = float(c[-4]["close"]) if len(c) >= 4 else float(c[0]["close"])
#     mom = (close_now / close_3 - 1.0) * 100.0

#     # Candle quality
#     agg_open = float(c[-15]["open"])
#     agg_high = max(float(x["high"]) for x in c[-15:])
#     agg_low = min(float(x["low"]) for x in c[-15:])
#     agg_close = float(c[-1]["close"])
#     body = abs(agg_close - agg_open)
#     total_range = max(agg_high - agg_low, 1e-9)
#     candle_quality = body / total_range

#     # Higher timeframe alignment
#     closes = [float(x["close"]) for x in c]
#     sma60 = safe_mean(closes[-60:]) if len(closes) >= 60 else safe_mean(closes)
#     sma180 = safe_mean(closes[-180:]) if len(closes) >= 180 else safe_mean(closes)
#     htf_alignment = 1.0 if (sma60 > sma180 and direction > 0) or (sma60 < sma180 and direction < 0) else 0.0

#     # Scoring
#     score_price = min(abs(pct15) / 5.0, 1.0)
#     score_vol = min(max((vol_ratio - 1.0) / 2.0, 0.0), 1.0)
#     score_mom = max(min(max((mom / 2.0), -1), 1), 0.0)
#     score_candle = min(max(candle_quality, 0.0), 1.0)
#     score_htf = float(htf_alignment)
#     score_depth = 0.5  # neutral score for now

#     final = (WEIGHTS["price"] * score_price +
#              WEIGHTS["volume"] * score_vol +
#              WEIGHTS["momentum"] * score_mom +
#              WEIGHTS["candle_quality"] * score_candle +
#              WEIGHTS["htf_alignment"] * score_htf +
#              WEIGHTS["depth"] * score_depth)

#     breakdown = {
#         "pct15": pct15,
#         "score_price": round(score_price, 3),
#         "vol_ratio": round(vol_ratio, 3),
#         "mom": round(mom, 3),
#         "candle_quality": round(candle_quality, 3),
#         "htf_alignment": score_htf,
#         "final_score": round(final, 4),
#         "close_now": close_now,
#     }
    
#     return final, breakdown, None

# def on_open(ws):
#     """WebSocket connection opened"""
#     print("🔌 WebSocket connected, subscribing...")
#     try:
#         top_symbols = fetch_top_symbols_by_turnover(TOP_N_SYMBOLS)
#         print(f"📊 Monitoring {len(top_symbols)} symbols")
        
#         sub_msg = {
#             "type": "subscribe",
#             "payload": {
#                 "channels": [
#                     {"name": "v2/ticker", "symbols": ["all"]},
#                     {"name": "candlestick_1m", "symbols": top_symbols},
#                 ]
#             }
#         }
#         ws.send(json.dumps(sub_msg))
#         print("✅ Subscribed to channels")
        
#         # Send test message
#         send_telegram_alert("🚀 Delta Spike Notifier is now online and monitoring for price spikes!")
        
#     except Exception as e:
#         print(f"❌ Subscription failed: {e}")

# def on_error(ws, err):
#     """WebSocket error handler"""
#     print(f"❌ WebSocket error: {err}")

# def on_close(ws, code, reason):
#     """WebSocket connection closed"""
#     print(f"🔌 WebSocket closed: {code} - {reason}")

# def on_message(ws, raw):
#     """Handle incoming WebSocket messages"""
#     try:
#         msg = json.loads(raw)
#     except Exception:
#         return

#     mtype = msg.get("type")
    
#     if mtype and mtype.startswith("candlestick_"):
#         symbol = msg.get("symbol")
#         if not symbol:
#             return
            
#         candle = {
#             "open": float(msg["open"]),
#             "high": float(msg["high"]),
#             "low": float(msg["low"]),
#             "close": float(msg["close"]),
#             "volume": float(msg.get("volume") or 0),
#             "ts": int(msg.get("candle_start_time") or msg.get("timestamp") or int(time.time()*1000))
#         }
        
#         candles_1m[symbol].append(candle)
        
#         # Check for spike conditions
#         try:
#             final, breakdown, veto = compute_scores(symbol)
#             if veto:
#                 return
#             if final is None:
#                 return
                
#             # Check cooldown
#             last = last_alert_ts.get(symbol, 0)
#             if time.time() - last < ALERT_COOLDOWN_SEC:
#                 return
                
#             if final >= ALERT_SCORE_THRESHOLD:
#                 # Send alert
#                 txt = (f"🚨 *SPIKE ALERT* {symbol}\n"
#                        f"Score: *{round(breakdown['final_score'],3)}*\n"
#                        f"Change: *{round(breakdown['pct15'],3)}%* in 15m\n"
#                        f"Volume: x{round(breakdown['vol_ratio'],2)}\n"
#                        f"Price: ${breakdown['close_now']:.6f}\n"
#                        f"Time: {datetime.now().strftime('%H:%M:%S')}")
                
#                 if send_telegram_alert(txt):
#                     last_alert_ts[symbol] = time.time()
#                     print(f"🚨 Alert sent for {symbol}")
                    
#         except Exception as e:
#             print(f"❌ Score computation error: {e}")
            
#     elif mtype == "v2/ticker":
#         symbol = msg.get("symbol")
#         if symbol:
#             tickers[symbol] = msg






# def run():
#     """Main run loop with reconnection"""
#     import signal
#     import sys
#     import threading
    
#     # Global flag to control the loop
#     running = True
#     ws_instance = None
    
#     def signal_handler(signum, frame):
#         """Handle Ctrl+C gracefully"""
#         nonlocal running, ws_instance
#         print("\n🛑 Received interrupt signal (Ctrl+C)")
#         print("🔄 Shutting down gracefully...")
#         running = False
        
#         # Close WebSocket if it exists
#         if ws_instance:
#             try:
#                 ws_instance.close()
#             except:
#                 pass
        
#         # Force exit after a short delay
#         print("🔄 Exiting in 2 seconds...")
#         threading.Timer(2.0, lambda: os._exit(0)).start()
    
#     # Register signal handlers
#     signal.signal(signal.SIGINT, signal_handler)
#     signal.signal(signal.SIGTERM, signal_handler)
    
#     while running:
#         try:
#             print("🔄 Connecting to Delta Exchange...")
#             ws_instance = websocket.WebSocketApp(
#                 WS_URL,
#                 on_open=on_open,
#                 on_message=on_message,
#                 on_error=on_error,
#                 on_close=on_close
#             )
            
#             # Handle SSL issues on macOS
#             import ssl
            
#             # Run WebSocket in a separate thread so we can interrupt it
#             ws_thread = threading.Thread(
#                 target=lambda: ws_instance.run_forever(
#                     ping_interval=20, 
#                     ping_timeout=10,
#                     sslopt={"cert_reqs": ssl.CERT_NONE}
#                 ),
#                 daemon=True
#             )
#             ws_thread.start()
            
#             # Wait for the WebSocket thread or until interrupted
#             while ws_thread.is_alive() and running:
#                 time.sleep(1)
                
#             if not running:
#                 break
                
#         except Exception as e:
#             print(f"❌ Connection failed: {e}")
#             if not running:
#                 break
#             print("🔄 Reconnecting in 10 seconds...")
#             time.sleep(10)
    
#     print("✅ Delta Spike Notifier stopped successfully")




# if __name__ == "__main__":
#     print("🚀 Starting Delta Spike Notifier...")
#     print(f"📱 Telegram Bot: {TELEGRAM_BOT_TOKEN[:10]}...")
#     print(f"💬 Chat ID: {TELEGRAM_CHAT_ID}")
#     print(f"🎯 Threshold: {PCT_SPIKE_THRESHOLD}%")
#     print(f"📊 Monitoring top {TOP_N_SYMBOLS} symbols")
#     print("=" * 50)
    
#     run()





#!/usr/bin/env python3
"""
Delta Exchange Spike Notifier with optional auto-trading
Monitors crypto prices and sends Telegram alerts for spikes
Optionally places market orders on Delta Exchange
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
import numpy as np

# ---------------------------
# Configuration
# ---------------------------
REST_BASE = "https://api.india.delta.exchange"
WS_URL = "wss://socket.india.delta.exchange"

TOP_N_SYMBOLS = int(os.getenv("TOP_N_SYMBOLS", "120"))
MIN_TURNOVER_USD = float(os.getenv("MIN_TURNOVER_USD", "5000"))
PCT_SPIKE_THRESHOLD = float(os.getenv("PCT_SPIKE_THRESHOLD", "2.0"))
ALERT_SCORE_THRESHOLD = float(os.getenv("ALERT_SCORE_THRESHOLD", "0.65"))
ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", "900"))
CANDLES_SAVE_MIN = 360

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
# Delta API credentials
# ---------------------------
API_KEY = "cgCYh2dZfpozKKTkeBygVpuZsoELlD"
API_SECRET = "RCWft2ptKL6kKRuY7Az8dZvdCB6TGg6O6IMreRRzUe7VACCmWXC2hlcy4BOP"

# ---------------------------
# State variables
# ---------------------------
candles_1m = defaultdict(lambda: deque(maxlen=CANDLES_SAVE_MIN))
tickers = {}
last_alert_ts = {}
session = requests.Session()
session.headers.update({"Accept": "application/json"})

# ---------------------------
# Telegram alert
# ---------------------------
def send_telegram_alert(text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    try:
        resp = session.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"✅ Telegram alert sent: {text[:50]}...")
            return True
        else:
            print(f"❌ Telegram failed: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Telegram exception: {e}")
        return False

# ---------------------------
# Delta private API helpers
# ---------------------------
def generate_signature(method, path, body=""):
    timestamp = str(int(time.time()))
    message = f"{method}{timestamp}{path}{body}"
    signature = hmac.new(
        API_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return signature, timestamp

def delta_private_post(path, payload=None):
    body_json = json.dumps(payload) if payload else ""
    signature, timestamp = generate_signature("POST", path, body_json)
    headers = {
        "api-key": API_KEY,
        "signature": signature,
        "timestamp": timestamp,
        "User-Agent": "delta-python-bot",
        "Content-Type": "application/json"
    }
    url = REST_BASE + path
    resp = session.post(url, headers=headers, data=body_json)
    try:
        return resp.json()
    except:
        return {"error": resp.text}

def place_market_order(symbol, size=0.001, side="buy"):
    # Lookup product_id
    products = session.get(f"{REST_BASE}/v2/products").json().get("result", [])
    prod_id = next((p["id"] for p in products if p["symbol"] == symbol), None)
    if not prod_id:
        print(f"❌ Product ID not found for {symbol}")
        return None
    payload = {
        "product_id": prod_id,
        "size": size,
        "side": side,
        "order_type": "market_order"
    }
    result = delta_private_post("/v2/orders", payload)
    print(f"🛒 Order placed for {symbol}: {result}")
    return result

# ---------------------------
# Fetch top symbols
# ---------------------------
def fetch_top_symbols_by_turnover(n=TOP_N_SYMBOLS):
    try:
        url = f"{REST_BASE}/v2/tickers"
        params = {"contract_types": "perpetual_futures"}
        resp = session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError("Failed to fetch tickers")
        arr = [t for t in data["result"] if t.get("symbol")]
        arr_sorted = sorted(arr, key=lambda x: float(x.get("turnover_usd") or 0), reverse=True)
        symbols = [t["symbol"] for t in arr_sorted if float(t.get("turnover_usd") or 0) >= MIN_TURNOVER_USD]
        return symbols[:n]
    except Exception as e:
        print(f"❌ Failed to fetch symbols: {e}")
        return ["BTCUSD", "ETHUSD", "SOLUSD"]  # fallback

# ---------------------------
# Scoring logic
# ---------------------------
def safe_mean(xs):
    return float(np.mean(xs)) if xs else 0.0

def compute_scores(symbol):
    c = list(candles_1m[symbol])
    if len(c) < 16:
        return None, None, "not_enough_candles"

    close_now = float(c[-1]["close"])
    close_15 = float(c[-16]["close"]) if len(c) >= 16 else float(c[0]["close"])
    pct15 = (close_now / close_15 - 1.0) * 100.0
    if abs(pct15) < PCT_SPIKE_THRESHOLD:
        return None, None, "below_threshold"
    direction = 1 if pct15 >= 0 else -1

    vol_last15 = sum([float(x.get("volume", 0) or 0) for x in c[-15:]])
    look_avg = c[-(min(180, len(c))):]
    avg_1m = safe_mean([float(x.get("volume", 0) or 0) for x in look_avg])
    avg_15m = max(avg_1m * 15.0, 1e-9)
    vol_ratio = vol_last15 / avg_15m

    close_3 = float(c[-4]["close"]) if len(c) >= 4 else float(c[0]["close"])
    mom = (close_now / close_3 - 1.0) * 100.0

    agg_open = float(c[-15]["open"])
    agg_high = max(float(x["high"]) for x in c[-15:])
    agg_low = min(float(x["low"]) for x in c[-15:])
    agg_close = float(c[-1]["close"])
    body = abs(agg_close - agg_open)
    total_range = max(agg_high - agg_low, 1e-9)
    candle_quality = body / total_range

    closes = [float(x["close"]) for x in c]
    sma60 = safe_mean(closes[-60:]) if len(closes) >= 60 else safe_mean(closes)
    sma180 = safe_mean(closes[-180:]) if len(closes) >= 180 else safe_mean(closes)
    htf_alignment = 1.0 if (sma60 > sma180 and direction > 0) or (sma60 < sma180 and direction < 0) else 0.0

    score_price = min(abs(pct15) / 5.0, 1.0)
    score_vol = min(max((vol_ratio - 1.0) / 2.0, 0.0), 1.0)
    score_mom = max(min(max((mom / 2.0), -1), 1), 0.0)
    score_candle = min(max(candle_quality, 0.0), 1.0)
    score_htf = float(htf_alignment)
    score_depth = 0.5

    final = (WEIGHTS["price"] * score_price +
             WEIGHTS["volume"] * score_vol +
             WEIGHTS["momentum"] * score_mom +
             WEIGHTS["candle_quality"] * score_candle +
             WEIGHTS["htf_alignment"] * score_htf +
             WEIGHTS["depth"] * score_depth)

    breakdown = {
        "pct15": pct15,
        "score_price": round(score_price, 3),
        "vol_ratio": round(vol_ratio, 3),
        "mom": round(mom, 3),
        "candle_quality": round(candle_quality, 3),
        "htf_alignment": score_htf,
        "final_score": round(final, 4),
        "close_now": close_now,
    }
    return final, breakdown, None

# ---------------------------
# WebSocket callbacks
# ---------------------------
def on_open(ws):
    print("🔌 WebSocket connected, subscribing...")
    try:
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
    except Exception as e:
        print(f"❌ Subscription failed: {e}")

def on_error(ws, err):
    print(f"❌ WebSocket error: {err}")

def on_close(ws, code, reason):
    print(f"🔌 WebSocket closed: {code} - {reason}")

def on_message(ws, raw):
    try:
        msg = json.loads(raw)
    except Exception:
        return
    mtype = msg.get("type")
    if mtype and mtype.startswith("candlestick_"):
        symbol = msg.get("symbol")
        if not symbol:
            return
        candle = {
            "open": float(msg["open"]),
            "high": float(msg["high"]),
            "low": float(msg["low"]),
            "close": float(msg["close"]),
            "volume": float(msg.get("volume") or 0),
            "ts": int(msg.get("candle_start_time") or msg.get("timestamp") or int(time.time()*1000))
        }
        candles_1m[symbol].append(candle)
        # Compute scores
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
                if send_telegram_alert(txt):
                    last_alert_ts[symbol] = time.time()
                    print(f"🚨 Alert sent for {symbol}")
                    # ⚡ Optional: Auto-trade (start with tiny size)
                    place_market_order(symbol, size=0.001, side="buy")
        except Exception as e:
            print(f"❌ Score computation error: {e}")
    elif mtype == "v2/ticker":
        symbol = msg.get("symbol")
        if symbol:
            tickers[symbol] = msg

# ---------------------------
# Main run loop
# ---------------------------
def run():
    import signal
    running = True
    ws_instance = None

    def signal_handler(signum, frame):
        nonlocal running, ws_instance
        print("\n🛑 Received interrupt signal (Ctrl+C)")
        running = False
        if ws_instance:
            try:
                ws_instance.close()
            except:
                pass
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
            import ssl
            ws_thread = threading.Thread(
                target=lambda: ws_instance.run_forever(
                    ping_interval=20, 
                    ping_timeout=10,
                    sslopt={"cert_reqs": ssl.CERT_NONE}
                ),
                daemon=True
            )
            ws_thread.start()
            while ws_thread.is_alive() and running:
                time.sleep(1)
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            if not running:
                break
            print("🔄 Reconnecting in 10 seconds...")
            time.sleep(10)

    print("✅ Delta Spike Notifier stopped successfully")

# ---------------------------
# Entry point
# ---------------------------
if __name__ == "__main__":
    print("🚀 Starting Delta Spike Notifier...")
    print(f"📱 Telegram Bot: {TELEGRAM_BOT_TOKEN[:10]}...")
    print(f"💬 Chat ID: {TELEGRAM_CHAT_ID}")
    print(f"🎯 Threshold: {PCT_SPIKE_THRESHOLD}%")
    print(f"📊 Monitoring top {TOP_N_SYMBOLS} symbols")
    print("=" * 50)
    run()
