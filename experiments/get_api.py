PM_HOST = "https://gamma-api.polymarket.com/"

import json
from datetime import datetime, timedelta
from pprint import pprint as print

import requests


def get_events(start_date, end_date, offset, limit=500):
    events_filters = f"end_date_max={end_date}&end_date_min={start_date}&limit={limit}&offset={offset}"
    response = requests.get(PM_HOST + "events?" + events_filters)
    return response.json()


now = datetime.now()
today = now.strftime("%Y-%m-%dT%H:%M:%SZ")
start = (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
limit = 500
print(start)
print(today)

collected_items = []
offset = 0

returned_items = get_events(start, today, offset)
collected_items.extend(returned_items)
with open(f"markets_{offset}.json", "w") as f:
    json.dump(returned_items, f, indent=2)
while len(returned_items) == limit:
    offset += limit
    print(f"Calling API for offset={offset}")
    returned_items = get_events(start, today, offset)
    print(f"Found {len(returned_items)} items")
    print(
        f"{returned_items[0]['id']} - {returned_items[0]['ticker']} - {returned_items[0]['endDate']}"
    )
    print(
        f"{returned_items[-1]['id']} - {returned_items[-1]['ticker']} - {returned_items[-1]['endDate']}"
    )
    with open(f"markets_{offset}.json", "w") as f:
        json.dump(returned_items, f, indent=2)
    # collected_items.extend(returned_items)

# print(f"Total items found: {len(collected_items)}")
