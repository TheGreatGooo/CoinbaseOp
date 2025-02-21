import http.client
import json, hmac, hashlib, time, base64
import time
import uuid
import math
from decimal import Decimal
import os
import jwt
from cryptography.hazmat.primitives import serialization
import time
import secrets

purchase_allocations = json.loads(os.environ.get('purchase_allocations'))
trade_usd_lower_limit = int(os.environ.get('trade_usd_lower_limit',1))
trade_usd_upper_limit = int(os.environ.get('trade_usd_upper_limit', 50))
trade_interval_seconds = int(os.environ.get('trade_interval_seconds',86400))
last_trade_timestamp = float(os.environ.get('last_trade_timestamp',0))
last_trade_file = os.environ.get('last_trade_file', "/var/CoinbaseOp/last_trade_file")
trade_offset_based_on_24h_percent_change = int(os.environ.get('trade_offset_based_on_24h_percent_change', 10))
conn = http.client.HTTPSConnection("api.coinbase.com")
api_key = os.environ.get('api_key', "test")
api_secret = os.environ.get('api_secret', "test")

def build_jwt(uri):
    global api_secret, api_key, conn
    private_key_bytes = api_secret.encode('utf-8')
    private_key = serialization.load_pem_private_key(private_key_bytes, password=None)
    jwt_payload = {
        'sub': api_key,
        'iss': "cdp",
        'nbf': int(time.time()),
        'exp': int(time.time()) + 120,
        'uri': uri,
    }
    jwt_token = jwt.encode(
        jwt_payload,
        private_key,
        algorithm='ES256',
        headers={'kid': api_key, 'nonce': secrets.token_hex()},
    )
    return jwt_token

def canTrade():
    if time.time() - last_trade_timestamp < trade_interval_seconds :
        trade_paused_till =time.strftime("%A, %D %B %Y, %r",time.localtime(last_trade_timestamp+trade_interval_seconds))
        print(f'Will skip all trading till {trade_paused_till}')
        return False
    else:
        return True

def sendRequest(method, apiEndpoint, payload, headers):
    jwt_token = build_jwt(f"{method} api.coinbase.com{apiEndpoint}")
    headers = headers | {
    'Content-Type': 'application/json',
    'Authorization': f"Bearer {jwt_token}",
    }
    conn.request(method, apiEndpoint, payload, headers)
    res = conn.getresponse()
    data = res.read()
    try:
        return json.loads(data.decode("utf-8"))
    except:
        print(f"we got back bad data from the api {apiEndpoint} data is:")
        print(data.decode("utf-8"))

def getAvailableUSD():
    payload = ''
    headers = {
    'Content-Type': 'application/json'
    }
    response = sendRequest("GET","/api/v3/brokerage/accounts",payload,headers)
    for account in response["accounts"] :
        if account["currency"] == "USD":
            return Decimal(account["available_balance"]["value"])
    return Decimal(0)

def getPrice(currency_pair):
    payload = ''
    headers = {
    'Content-Type': 'application/json'
    }
    response = sendRequest("GET",f"/api/v3/brokerage/products/{currency_pair}",payload,headers)
    return {"price":Decimal(response["price"]), "price_percent_change_24h": Decimal(response["price_percentage_change_24h"]),"step_quote":Decimal(response["quote_increment"]), "step_base":Decimal(response["base_increment"])}

def placeTrades(trades_to_place):
    trades_placed = False
    for trade in trades_to_place:
        currency_pair = trade["currency_pair"]
        dollars = trade["dollars"]
        price_details = getPrice(currency_pair)
        offset_percent = max(price_details["price_percent_change_24h"]*Decimal(trade_offset_based_on_24h_percent_change/100), Decimal(0.1))
        if dollars > 0 :
            limit_price = price_details["price"] - (price_details["price"] * offset_percent/Decimal(100))
            decimal_precision_quote = round(math.log(price_details["step_quote"],10))*-1
            decimal_precision_base = round(math.log(price_details["step_base"],10))*-1
            clean_limit_price = round(limit_price,decimal_precision_quote)
            amount = round(dollars/clean_limit_price,decimal_precision_base)
            order_json_string = json.dumps({"side":"BUY","client_order_id":str(uuid.uuid1()),"product_id":currency_pair,"order_configuration":{"limit_limit_gtc":{"base_size":str(amount),"limit_price":str(clean_limit_price),"post_only":True}}})
            headers = {
            'Content-Type': 'application/json'
            }
            response = sendRequest("POST","/api/v3/brokerage/orders",order_json_string,headers)
            print(response)
            if "error" not in response and "success" in response and response["success"]:
                trades_placed = True
    if trades_placed :
        f = open(last_trade_file, "w")
        f.write(f"last_trade_timestamp={str(time.time())}")
        f.close()


if canTrade() :
    dollars_available = getAvailableUSD()
    dollars_available_post_trade = dollars_available
    if dollars_available > 0 :
        trades_to_place = []
        for currency_pair in purchase_allocations.keys():
            percent_to_allocate = Decimal(purchase_allocations[currency_pair])
            dollars_to_allocate = min(Decimal(trade_usd_upper_limit) , max((percent_to_allocate/Decimal(100.0)) * dollars_available,Decimal(trade_usd_lower_limit)))
            dollars_available_post_trade = dollars_available_post_trade - dollars_to_allocate
            if dollars_available_post_trade < 0 :
                print(f'Will skip trading {currency_pair} because $ {dollars_to_allocate} is out of bounds of the configured limits $ {trade_usd_lower_limit} - $ {trade_usd_upper_limit}')
                continue
            trades_to_place.append({"currency_pair": currency_pair, "dollars": dollars_to_allocate})
    placeTrades(trades_to_place)