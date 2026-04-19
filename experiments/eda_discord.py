import json
import os
from pprint import pprint as print

dir_path = "data/discord/1776096570"

total_threads = 0
total_messages = 0

max_threads = 99999999


import polars as pl

embed_fields = {
    "type": pl.String,
    "url": pl.String,
    "title": pl.String,
}

message_schema = {
    "id": pl.String,
    "thread_id": pl.String,
    "vote": pl.String,
    "content": pl.String,
    "embeds": pl.List(pl.Struct(embed_fields)),
    "timestamp": pl.String,
    "edited_timestamp": pl.String,
    "author_id": pl.String,
    "author_username": pl.String,
}

thread_schema = {
    # no `type` as we assume all will be type=18 from the scrape side.
    "id": pl.String,
    "channel_id": pl.String,  # parent channel id
    "question": pl.String,
    "content": pl.String,
    "timestamp": pl.String,
    "edited_timestamp": pl.String,
    "author_id": pl.String,
    "author_username": pl.String,
    "thread_guild_id": pl.String,  # to be extracted from message_reference.guild_id
    # then subsequent thread related info below
    "thread_last_message_id": pl.String,
    "thread_message_count": pl.Int16,
    "thread_member_count": pl.Int16,
}


def unnest_target(data_obj: dict, target_field: str, extract_fields: list[str]) -> dict:
    target = data_obj.get(target_field, {})
    if isinstance(target, list):
        data = []
        for t in target:
            data.append({field: t.get(field) for field in extract_fields})
        return data  # returns list
    else:
        return {
            field: target.get(field) for field in extract_fields
        }  # returns dict directly


import re


def extract_thread_question(thread_title: str) -> str:
    pattern = "(.+?)(?= - \d{10})"
    match = re.search(pattern, thread_title)
    if match:
        return match.group(1)
    return ""


def extract_message_vote(message_content: str) -> str:
    pattern = "(?i)(?<!\w)(P[1-4])(?!\w)"  # needs to account for case-insensitivity and ignore when the surrounding characters are alhpanumerical..
    match = re.search(pattern, message_content)
    if match:
        return match.group(1).upper()  # first match to be true
    return ""


def load_data(dir_path, max_records):
    messages = []
    threads = []
    from tqdm import tqdm

    for file in tqdm(reversed(os.listdir(dir_path))):
        if not file.endswith(".json"):
            continue
        with open(os.path.join(dir_path, file), "r") as f:
            data = json.load(f)
            # Assuming data is a list of events/messages
            for record in reversed(data):
                # Type 18 or having a "thread" payload indicates a thread header message
                if record.get("type") == 18 or "thread" in record:
                    # threads
                    thread_info = unnest_target(
                        record,
                        "thread",
                        [
                            "guild_id",
                            "last_message_id",
                            "thread_metadata.archived",
                            "message_count",
                            "member_count",
                        ],
                    )

                    author_info = unnest_target(
                        record,
                        "author",
                        ["id", "username"],
                    )
                    record.update(
                        {
                            "question": extract_thread_question(record.get("content")),
                            "author_id": author_info["id"],
                            "author_username": author_info["username"],
                            "thread_guild_id": thread_info["guild_id"],
                            "thread_last_message_id": thread_info["last_message_id"],
                            "thread_message_count": thread_info["message_count"],
                            "thread_member_count": thread_info["member_count"],
                        }
                    )
                    threads.append(record)
                else:
                    # messages
                    embed_info = unnest_target(
                        record,
                        "embeds",
                        list(embed_fields.keys()),
                    )
                    author_info = unnest_target(
                        record,
                        "author",
                        ["id", "username"],
                    )
                    record.update(
                        {
                            "vote": extract_message_vote(record.get("content")),
                            "author_id": author_info["id"],
                            "author_username": author_info["username"],
                            "embeds": embed_info,
                        }
                    )
                    messages.append(record)

                if len(messages) + len(threads) >= max_records:
                    return messages, threads

    return messages, threads


messages, threads = load_data(dir_path, max_threads)

messages_df = pl.from_dicts(messages, schema=message_schema)
threads_df = pl.from_dicts(threads, schema=thread_schema)

print(messages_df)
print(threads_df)

messages_write_path = os.path.join(dir_path, f"_messages.parquet")
messages_df.write_parquet(messages_write_path)

threads_write_path = os.path.join(dir_path, f"_threads.parquet")
threads_df.write_parquet(threads_write_path)
