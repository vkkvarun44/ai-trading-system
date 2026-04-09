import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://finance.yahoo.com/",
    "Origin": "https://finance.yahoo.com",
    "DNT": "1",
}

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://finance.yahoo.com/",
    "Connection": "keep-alive"
})

session.get("https://finance.yahoo.com/", timeout=5)

def fetch_yahoo_tickers(url: str) -> list[str]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        tickers = []

        # Yahoo uses <a> tags with data-test="quoteLink"
        for a in soup.select('a[data-test="quoteLink"]'):
            ticker = a.text.strip()
            if ticker:
                tickers.append(ticker)

        return list(set(tickers))
    
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return []

def fetch_yahoo_tickers_api(scr_id="most_actives", count=100):
    url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"

    for attempt in range(3):
        try:
            response = session.get(
                url,
                params={"scrIds": scr_id, "count": count},
                timeout=10
            )

            if response.status_code == 429:
                wait = 3 + random.uniform(2, 5)
                print(f"429 hit. Sleeping {wait:.2f}s...")
                time.sleep(wait)
                continue

            if response.status_code != 200:
                time.sleep(2)
                continue

            data = response.json()
            quotes = data["finance"]["result"][0]["quotes"]

            return [q["symbol"] for q in quotes if "symbol" in q]

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(2)

    return []


def get_us_market_universe():
    urls = [
        "https://finance.yahoo.com/most-active",
        "https://finance.yahoo.com/gainers",
        "https://finance.yahoo.com/losers"
    ]

    all_tickers = set()

    for url in urls:
        tickers = fetch_yahoo_tickers_api(scr_id)
        all_tickers.update(tickers)

    return list(all_tickers)