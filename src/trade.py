import http.client
import json, hmac, hashlib, time, base64
import time
from decimal import Decimal

purchase_allocations = {"BTC-USD":1.6,"ETH-USD":1.6}
trade_usd_lower_limit = 1
trade_usd_upper_limit = 50
trade_interval_seconds = 86400
last_trade_timestamp = time.time()
conn = http.client.HTTPSConnection("api.coinbase.com")

def canTrade():
    if time.time() - last_trade_timestamp < trade_interval_seconds :
        print(f'Will skip all trading till {time.strftime("%A, %D %B %Y, %r, %nMOTY:%m %nDOTY:% j",time.localtime(last_trade_timestamp+trade_interval_seconds))}')
        return False
    else:
        return True

def getAvailableUSD():
    payload = ''
    headers = {
    'Content-Type': 'application/json'
    }
    message = timestamp + request.method + request.path_url.split('?')[0] + str(request.body or '')
    conn.request("GET", "/api/v3/brokerage/accounts", payload, headers)
    res = conn.getresponse()
    data = res.read()
    for account in json.loads(data.decode("utf-8"))["accounts"] :
        if account["currency"] == "USD":
            return Decimal(account["available_balance"]["value"])

if canTrade() :
    dollars_available = getAvailableUSD()
    if dollars_available > 0 :
        trades_to_place = []
        for currency_pair in purchase_allocations.keys():
            percent_to_allocate = purchase_allocations[currency_pair]
            dollars_to_allocate = (percent_to_allocate/100.0) * dollars_available
            if dollars_to_allocate > trade_usd_upper_limit or dollars_to_allocate < trade_usd_lower_limit :
                print(f'Will skip trading {currency_pair} because $ {dollars_to_allocate} is out of bounds of the configured limits $ {trade_usd_lower_limit} - $ {trade_usd_upper_limit}')
                continue
            trades_to_place.append({"currency_pair": currency_pair, "dollars": dollars_to_allocate})
    placeTrades(trades_to_place)
