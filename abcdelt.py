# import time
# import hmac
# import hashlib
# import requests
# import json

# # ---------------------------
# # Replace these with your keys
# API_KEY = "cgCYh2dZfpozKKTkeBygVpuZsoELlD"
# API_SECRET = "RCWft2ptKL6kKRuY7Az8dZvdCB6TGg6O6IMreRRzUe7VACCmWXC2hlcy4BOP"
# # ---------------------------

# BASE_URL = "https://api.india.delta.exchange"

# def generate_signature(method, path, body=""):
#     """
#     Generate HMAC-SHA256 signature for Delta private endpoints
#     """
#     timestamp = str(int(time.time()))
#     message = f"{method}{timestamp}{path}{body}"
#     signature = hmac.new(
#         API_SECRET.encode(), message.encode(), hashlib.sha256
#     ).hexdigest()
#     return signature, timestamp

# def place_order(product_id=27, size=1, side="buy", order_type="market_order"):
#     """
#     Example: place a market order
#     """
#     path = "/v2/orders"
#     method = "POST"
#     body_dict = {
#         "product_id": product_id,
#         "size": size,
#         "side": side,
#         "order_type": order_type
#     }
#     body_json = json.dumps(body_dict)

#     signature, timestamp = generate_signature(method, path, body_json)

#     headers = {
#         "api-key": API_KEY,
#         "signature": signature,
#         "timestamp": timestamp,
#         "User-Agent": "delta-python-bot",
#         "Content-Type": "application/json"
#     }

#     url = BASE_URL + path
#     response = requests.post(url, headers=headers, data=body_json)
#     return response.json()

# def get_account_info():
#     """
#     Fetch your account information
#     """
#     path = "/v2/accounts"
#     method = "GET"
#     signature, timestamp = generate_signature(method, path)
#     headers = {
#         "api-key": API_KEY,
#         "signature": signature,
#         "timestamp": timestamp,
#         "User-Agent": "delta-python-bot"
#     }
#     url = BASE_URL + path
#     response = requests.get(url, headers=headers)
#     return response.json()

# # ---------------------------
# # Run examples
# # ---------------------------

# if __name__ == "__main__":
#     # 1️⃣ Fetch account info
#     account_info = get_account_info()
#     print("Account Info:")
#     print(json.dumps(account_info, indent=2))

#     # 2️⃣ Place a test order (use very small size to test safely!)
#     order_result = place_order(product_id=27, size=0.001, side="buy", order_type="market_order")
#     print("\nOrder Result:")
#     print(json.dumps(order_result, indent=2))

# check if api key and secret is working

# import requests
# import time
# import hmac
# import hashlib

# API_KEY = "cgCYh2dZfpozKKTkeBygVpuZsoELlD"
# API_SECRET = "RCWft2ptKL6kKRuY7Az8dZvdCB6TGg6O6IMreRRzUe7VACCmWXC2hlcy4BOP"
# BASE = "https://api.india.delta.exchange"

# timestamp = str(int(time.time()))
# method = "GET"
# path = "/v2/products"
# body = ""

# # Create signature
# signature = hmac.new(
#     API_SECRET.encode(), 
#     f"{timestamp}{method}{path}{body}".encode(), 
#     hashlib.sha256
# ).hexdigest()

# headers = {
#     "api-key": API_KEY,
#     "signature": signature,
#     "timestamp": timestamp
# }

# resp = requests.get(BASE + path, headers=headers)
# print(resp.json())


#!/usr/bin/env python3

# import json
# import time
# import websocket
# import ssl
# import certifi

# WS_URL = "wss://socket.india.delta.exchange"

# def on_open(ws):
#     print("🔌 Connected to Delta Exchange WebSocket")
#     # Subscribe to BTCUSD ticker
#     sub_msg = {
#         "type": "subscribe",
#         "payload": {
#             "channels": [
#                 {"name": "v2/ticker", "symbols": ["all"]}
#             ]
#         }
#     }
#     ws.send(json.dumps(sub_msg))
#     print("✅ Subscribed to BTCUSD ticker")

# def on_message(ws, raw):
#     msg = json.loads(raw)
#     if msg.get("type") == "v2/ticker":
#         print("📈 Ticker Update:", msg)

# def on_error(ws, err):
#     print("❌ WebSocket error:", err)

# def on_close(ws, code, reason):
#     print(f"🔌 WebSocket closed: {code} - {reason}")

# if __name__ == "__main__":
#     ws_app = websocket.WebSocketApp(
#         WS_URL,
#         on_open=on_open,
#         on_message=on_message,
#         on_error=on_error,
#         on_close=on_close
#     )
#     ws_app.run_forever(ping_interval=20, ping_timeout=10 , sslopt={"cert_reqs": ssl.CERT_NONE})



#!/usr/bin/env python3
import json
import time
import websocket
import ssl
import requests
import certifi

WS_URL = "wss://socket.india.delta.exchange"
REST_BASE = "https://api.india.delta.exchange"

# -----------------------------
# 1️⃣ Fetch only perpetual futures
# -----------------------------
def fetch_futures_symbols():
    url = f"{REST_BASE}/v2/tickers"
    params = {"contract_types": "perpetual_futures"}  # only futures
    resp = requests.get(url, params=params)
    data = resp.json()
    symbols = [t["symbol"] for t in data.get("result", []) if t.get("contract_type") == "perpetual_futures"]
    return symbols

# -----------------------------
# 2️⃣ WebSocket callbacks
# -----------------------------
def on_open(ws):
    print("🔌 Connected to Delta Exchange WebSocket")
    futures_symbols = fetch_futures_symbols()
    print("📊 Subscribing only to perpetual futures:", futures_symbols[:10], "...")  # show first 10

    sub_msg = {
        "type": "subscribe",
        "payload": {
            "channels": [
                {"name": "v2/ticker", "symbols": futures_symbols}
            ]
        }
    }
    ws.send(json.dumps(sub_msg))
    print("✅ Subscribed to perpetual futures tickers")

def on_message(ws, raw):
    msg = json.loads(raw)
    if msg.get("type") == "v2/ticker":
        print("📈 Ticker Update:", msg)

def on_error(ws, err):
    print("❌ WebSocket error:", err)

def on_close(ws, code, reason):
    print(f"🔌 WebSocket closed: {code} - {reason}")

# -----------------------------
# 3️⃣ Run WebSocket
# -----------------------------
if __name__ == "__main__":
    ws_app = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws_app.run_forever(
        ping_interval=20,
        ping_timeout=10,
        sslopt={"ca_certs": certifi.where()}
    )