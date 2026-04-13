import json
import os
from pprint import pprint as print

dir_path = "data/1775970891"

total_markets = 0
total_events = 0

max_events = 99999999

# market_fields = {
#     "id": int,
#     "ticker": string,
#     "slug": string,
#     "title": string,
#     "description": string,
#     ""
# }


def from_string_list(string_list: string):
    # Only for clobTokenIds, outcomes, outcomePrices, umaResolutionStatuses
    try:
        return json.loads(string_list)
    except:
        return []


def get_tag_slugs(tags: list(dict)):
    return [tag.get("slug") for tag in tags]


def load_data(dir_path, max_events):
    events = []
    markets = []
    from tqdm import tqdm

    for file in tqdm(reversed(os.listdir(dir_path))):  # Load the newest file first

        if not file.endswith(".json"):
            print(f"Found invalid file: {file}, skipping.")
            continue
        with open(f"{dir_path}/{file}", "r") as f:
            data = json.load(f)
            for event in reversed(data):  # Load latest event first

                if event.get("tags"):
                    event.update({"tags": get_tag_slugs(event["tags"])})
                else:
                    event.update({"tags": []})
                events.append(event)
                if len(events) == max_events:
                    return events, markets
                else:
                    for market in event["markets"]:
                        market_data = {"event_id": event["id"]}
                        market_data.update(market)

                        # Unnest
                        market_tags = []
                        if market.get("tags"):
                            market_tags = get_tag_slugs(market["tags"])
                        market_data.update(
                            {
                                "tags": market_tags,
                            }
                        )

                        # Deserialize
                        deser_fields = [
                            "clobTokenIds",
                            "outcomes",
                            "outcomePrices",
                            "umaResolutionStatuses,",
                        ]
                        for field in deser_fields:
                            deser_ls = []
                            if market.get(field):
                                deser_data = from_string_list(market[field])
                                # print(deser_data)
                            market_data.update(
                                {
                                    field: deser_data,
                                }
                            )
                        markets.append(market_data)

    return events, markets


from dataclasses import dataclass

import polars as pl
from dacite import from_dict

event_schema = {
    "id": pl.String,
    "ticker": pl.String,
    "slug": pl.String,
    "title": pl.String,
    "description": pl.String,
    # "resolutionSource": pl.String,
    "startDate": pl.String,
    "creationDate": pl.String,
    "endDate": pl.String,
    "active": pl.Boolean,
    "closed": pl.Boolean,
    "archived": pl.Boolean,
    "new": pl.Boolean,
    "featured": pl.Boolean,
    "restricted": pl.Boolean,
    "volume": pl.Float64,
    "volume1wk": pl.Float64,
    "volume1mo": pl.Float64,
    "volume1yr": pl.Float64,
    "openInterest": pl.Float64,
    "createdAt": pl.String,
    "updatedAt": pl.String,
    "enableOrderBook": pl.Boolean,
    "negRisk": pl.Boolean,
    "commentCount": pl.Int64,
    "tags": pl.List(pl.String),
    "cyom": pl.Boolean,
    "closedTime": pl.String,
    "automaticallyResolved": pl.Boolean,
    "enableNegRisk": pl.Boolean,
    "automaticallyActive": pl.Boolean,
    "eventDate": pl.String,
    "startTime": pl.String,
    "period": pl.String,
    "live": pl.Boolean,
    "ended": pl.Boolean,
    "finishedTimestamp": pl.String,
    "negRiskAugmented": pl.Boolean,
    "pendingDeployment": pl.Boolean,
    "deploying": pl.Boolean,
}

market_schema = {
    "event_id": pl.String,
    "id": pl.String,
    "question": pl.String,
    "conditionId": pl.String,
    "slug": pl.String,
    "resolutionSource": pl.String,
    "endDate": pl.String,
    "startDate": pl.String,
    "description": pl.String,
    "outcomes": pl.List(pl.String),
    "outcomePrices": pl.List(pl.String),
    "volumeNum": pl.Float64,
    "volume1wk": pl.Float64,
    "volume1mo": pl.Float64,
    "volume1yr": pl.Float64,
    "active": pl.Boolean,
    "closed": pl.Boolean,
    "marketMakerAddress": pl.String,
    "createdAt": pl.String,
    "updatedAt": pl.String,
    "closedTime": pl.String,
    "new": pl.Boolean,
    "featured": pl.Boolean,
    "submitted_by": pl.String,
    "archived": pl.Boolean,
    "resolvedBy": pl.String,
    "restricted": pl.Boolean,
    "questionID": pl.String,
    "umaEndDate": pl.String,
    "enableOrderBook": pl.Boolean,
    "orderPriceMinTickSize": pl.Float64,
    "orderMinSize": pl.Float64,
    "umaResolutionStatus": pl.String,
    "endDateIso": pl.String,
    "startDateIso": pl.String,
    "hasReviewedDates": pl.Boolean,
    "clobTokenIds": pl.List,
    "umaBond": pl.Float64,
    "umaReward": pl.Float64,
    "customLiveness": pl.Float64,
    "acceptingOrders": pl.Boolean,
    "negRisk": pl.Boolean,
    "negRiskRequestID": pl.String,
    "ready": pl.Boolean,
    "funded": pl.Boolean,
    "acceptingOrdersTimestamp": pl.String,
    "cyom": pl.Boolean,
    "pagerDutyNotificationEnabled": pl.Boolean,
    "approved": pl.Boolean,
    "rewardsMinSize": pl.Float64,
    "rewardsMaxSpread": pl.Float64,
    "spread": pl.Float64,
    "automaticallyResolved": pl.Boolean,
    "oneDayPriceChange": pl.Float64,
    "oneWeekPriceChange": pl.Float64,
    "lastTradePrice": pl.Float64,
    "bestBid": pl.Float64,
    "bestAsk": pl.Float64,
    "automaticallyActive": pl.Boolean,
    "clearBookOnStart": pl.Boolean,
    "manualActivation": pl.Boolean,
    "negRiskOther": pl.Boolean,
    "umaResolutionStatuses": pl.List(pl.String),
    "pendingDeployment": pl.Boolean,
    "deploying": pl.Boolean,
    "deployingTimestamp": pl.String,
    "rfqEnabled": pl.Boolean,
    "holdingRewardsEnabled": pl.Boolean,
    "feesEnabled": pl.Boolean,
    "requiresTranslation": pl.Boolean,
    "feeType": pl.String,
}


events, markets = load_data(dir_path, max_events)
# print(events)
# print(markets)
markets_df = pl.from_dicts(markets, schema=market_schema)
events_df = pl.from_dicts(events, schema=event_schema)

# print(events[0].keys())
# print(markets[0].keys())

print(markets_df)
print(events_df)

events_write_path = dir_path + f"/_events_{max_events}.parquet"
events_df.write_parquet(
    events_write_path,
    # partition_by=["watermark"],
)

markets_write_path = dir_path + f"/_markets_{max_events}.parquet"
markets_df.write_parquet(
    markets_write_path,
    # partition_by=["watermark"],
)
