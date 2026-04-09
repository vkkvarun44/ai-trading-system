import yfinance as yf

def fetch_eu_data(tickers):
    data = yf.download(
        tickers=tickers,
        period="1d",
        interval="1d",
        group_by="ticker",
        progress=False
    )

    return data

def compute_eu_top_movers(tickers):
    data = fetch_eu_data(tickers)

    movers = []

    for ticker in tickers:
        try:
            df = data[ticker]

            open_price = df["Open"].iloc[-1]
            close_price = df["Close"].iloc[-1]

            change_pct = ((close_price - open_price) / open_price) * 100

            movers.append({
                "ticker": ticker,
                "price": float(close_price),
                "change_pct": float(change_pct)
            })

        except:
            continue

        gainers = sorted(movers, key=lambda x: x["change_pct"], reverse=True)[:10]
        losers = sorted(movers, key=lambda x: x["change_pct"])[:10]

        return {
            "gainers": gainers,
            "losers":losers
        }