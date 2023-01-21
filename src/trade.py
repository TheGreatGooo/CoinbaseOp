import http.client
import json, hmac, hashlib, time, base64
import time
import uuid
import math
from decimal import Decimal
import os

purchase_allocations = json.loads(os.environ['purchase_allocations']) or {"BTC-USD":1.6,"ETH-USD":1.6}
trade_usd_lower_limit = int(os.environ['trade_usd_lower_limit']) or 1
trade_usd_upper_limit = int(os.environ['trade_usd_upper_limit']) or 50
trade_interval_seconds = int(os.environ['trade_interval_seconds']) or  86400
last_trade_timestamp = float(os.environ['last_trade_timestamp']) or 0
last_trade_file = os.environ['last_trade_file'] or "/var/CoinbaseOp/last_trade_file"
trade_offset_based_on_24h_percent_change = int(os.environ['trade_offset_based_on_24h_percent_change']) or 10
conn = http.client.HTTPSConnection("api.coinbase.com")
api_key = os.environ['api_key'] or "test"
api_secret = os.environ['api_secret'] or "test"

def canTrade():
    if time.time() - last_trade_timestamp < trade_interval_seconds :
        print(f'Will skip all trading till {time.strftime("%A, %D %B %Y, %r, %nMOTY:%m %nDOTY:% j",time.localtime(last_trade_timestamp+trade_interval_seconds))}')
        return False
    else:
        return True

def sendRequest(method, apiEndpoint, payload, headers):
    global api_secret, api_key, conn
    timestamp = str(int(time.time()))
    message = timestamp + method + apiEndpoint.split('?')[0] + str(payload or '')
    signature = hmac.new(api_secret, message, hashlib.sha256).hexdigest()
    headers = headers + {
    'Content-Type': 'application/json',
    'CB-ACCESS-KEY': api_key,
    'CB-ACCESS-SIGN': signature,
    'CB-ACCESS-TIMESTAMP': timestamp
    }
    conn.request(method, apiEndpoint, payload, headers)
    res = conn.getresponse()
    data = res.read()
    return json.loads(data.decode("utf-8"))

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
    response = sendRequest("GET",f"api/v3/brokerage/products/{currency_pair}",payload,headers)
    return {"price":Decimal(response["price"]), "price_percent_change_24h": Decimal(response["price_percentage_change_24h"]),"step_quote":Decimal(response["quote_increment"]), "step_base":Decimal(response["base_increment"])}

def placeTrades(trades_to_place):
    trades_placed = False
    for trade in trades_to_place:
        currency_pair = trade["currency_pair"]
        dollars = trade["dollars"]
        price_details = getPrice(currency_pair)
        offset_percent = price_details["price_percent_change_24h"]*Decimal(trade_offset_based_on_24h_percent_change/100)
        if dollars > 0 :
            limit_price = price_details["price"] - (price_details["price"] * offset_percent/Decimal(100))
            decimal_precision_quote = round(math.log(price_details["step_quote"],10))*-1
            decimal_precision_base = round(math.log(price_details["step_base"],10))*-1
            clean_limit_price = round(limit_price,decimal_precision_quote)
            amount = round(dollars/clean_limit_price,decimal_precision_base)
            order_json_string = json.dumps({"side":"BUY","client_order_id":str(uuid.uuid1()),"product_id":currency_pair,"order_configuration":{"limit_limit_gtd":{"base_size":str(amount),"limit_price":str(clean_limit_price),"post_only":"true"}}})
            headers = {
            'Content-Type': 'application/json'
            }
            response = sendRequest("POST","/api/v3/brokerage/orders",order_json_string,headers)
            trades_placed = True
    if trades_placed :
        f = open(last_trade_file, "w")
        f.write(f"last_trade_timestamp=\"{str(time.time())}\"")
        f.close()


if canTrade() :
    dollars_available = getAvailableUSD()
    if dollars_available > 0 :
        trades_to_place = []
        for currency_pair in purchase_allocations.keys():
            percent_to_allocate = Decimal(purchase_allocations[currency_pair])
            dollars_to_allocate = (percent_to_allocate/Decimal(100.0)) * dollars_available
            if dollars_to_allocate > Decimal(trade_usd_upper_limit) or dollars_to_allocate < Decimal(trade_usd_lower_limit) :
                print(f'Will skip trading {currency_pair} because $ {dollars_to_allocate} is out of bounds of the configured limits $ {trade_usd_lower_limit} - $ {trade_usd_upper_limit}')
                continue
            trades_to_place.append({"currency_pair": currency_pair, "dollars": dollars_to_allocate})
    placeTrades(trades_to_place)