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
api_key = "test"
api_secret = "test"

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

print(getAvailableUSD())