from pprint import pprint as print

import pmxt

poly = pmxt.Polymarket()
kalshi = pmxt.Kalshi()
# limitless = pmxt.Limitless()  # Requires API key for authenticated operations

# Search for markets
markets = poly.fetch_markets(query="Iran")

for market in markets[-5:]:
    print(market)
