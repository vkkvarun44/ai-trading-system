import requests
import time

BASE_URL = "https://www.nseindia.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive"
}

session = requests.Session()
session.headers.update(HEADERS)

indices = [
    "NIFTY",
    "BANKNIFTY",
    "NIFTYNEXT50",
    "FINNIFTY"
]


def initialize_session():
    """
    VERY IMPORTANT: This sets cookies
    """
    session.get(BASE_URL, timeout=5)

def fetch_index_stocks(index_name: str):
    url = f"https://www.nseindia.com/api/live-analysis-variations?index={index_name}"

    try:
        response = session.get(url, timeout=10)

        if response.status_code != 200:
            print(f"NSE index error: {response.status_code}")
            return []

        data = response.json()

        stocks = []

        # 🔥 IMPORTANT: index key is dynamic
        index_data = data.get(index_name, {}).get("data", [])

        for item in index_data:
            symbol = item.get("symbol")

            if symbol:
                stocks.append(f"{symbol}.NS")

        return stocks

    except Exception as e:
        print(f"Index fetch error: {e}")
        return []


def fetch_top_movers(index_type="gainers"):
    url = f"https://www.nseindia.com/api/live-analysis-variations?index={index_type}"

    try:
        response = session.get(url, timeout=10)

        if response.status_code != 200:
            print(f"NSE error: {response.status_code}")
            return []

        data = response.json()

        stocks = []

        market_data = data.get("allSec", {}).get("data", [])

        for item in market_data:
            symbol = item.get("symbol")
            change = item.get("pChange")
            price = item.get("lastPrice")

            if symbol:
                stocks.append({
                    "ticker": f"{symbol}.NS",
                    "price": price,
                    "change_pct": change
                })

        return stocks

    except Exception as e:
        print(f"NSE fetch error: {e}")
        return []


def get_nse_top_movers():
    initialize_session()

    # 🔥 Step 1: Collect index stocks
    universe = set()

    for index in indices:
        stocks = fetch_index_stocks(index)
        universe.update(stocks)

    # 🔥 Step 2: Add top movers
    gainers = fetch_top_movers("gainers")
    time.sleep(1)
    losers = fetch_top_movers("losers")

    for stock in gainers + losers:
        ticker = stock.get("ticker")
        if ticker:
            universe.add(ticker)

    return {
        "gainers": gainers,
        "losers": losers,
        "universe": list(universe)   # 🔥 NEW
    }

def get_india_market_universe():
    data = get_nse_top_movers()

    return data.get("universe", [])