PM_HOST = "https://gamma-api.polymarket.com/"

import json
from datetime import datetime, timedelta
from pprint import pprint as print

import requests
from loguru import logger


def get_events(from_date, to_date, offset, limit=500, exclude_tags=None):

    events_filters = f"start_date_max={to_date}&start_date_min={from_date}&limit={limit}&offset={offset}"
    tag_filter = ""
    if exclude_tags:
        for tag in exclude_tags:
            tag_filter += f"&exclude_tag_id={tag}"
    request_string = "events?" + events_filters + tag_filter
    response = requests.get(PM_HOST + request_string)
    logger.info(f"GET/ {request_string}")
    return response.json()


exclude_tags = [102127, 1312]
day_delta = 365
now = datetime.now()
to_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")
from_date = (now - timedelta(days=day_delta)).strftime("%Y-%m-%dT%H:%M:%SZ")
limit = 500
print(from_date)
print(to_date)

collected_items = []
offset = 0

returned_items = get_events(from_date, to_date, offset, exclude_tags=exclude_tags)
collected_items.extend(returned_items)

# Create a data folder for the runtime:

import time
from pathlib import Path

data_path = f"data/{int(time.time())}"
Path(data_path).mkdir(parents=True, exist_ok=True)
with open(f"{data_path}/markets_{offset}.json", "w") as f:
    json.dump(returned_items, f, indent=2)
while len(returned_items) == limit:
    offset += limit
    print(f"Calling API for offset={offset}")
    returned_items = get_events(from_date, to_date, offset, exclude_tags=exclude_tags)
    print(f"Found {len(returned_items)} items")
    print(
        f"{returned_items[0]['id']} - {returned_items[0]['ticker']} - {returned_items[0]['endDate']}"
    )
    print(
        f"{returned_items[-1]['id']} - {returned_items[-1]['ticker']} - {returned_items[-1]['endDate']}"
    )
    with open(f"{data_path}/markets_{offset}.json", "w") as f:
        json.dump(returned_items, f, indent=2)
    # collected_items.extend(returned_items)

# print(f"Total items found: {len(collected_items)}")
