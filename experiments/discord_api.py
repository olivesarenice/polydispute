import json
import os
import time
from pprint import pprint as print

import requests

endpoint = "https://discord.com/api/v9/channels/1493015468980568068/messages?limit=100&around=1493015468980568068"
headers_minimal = {
    "authorization": "NjE0MzgzODg2MzYwNjQxNTU2.Gjkk3n.wbX058CObJhZW8lQQW0mqX2U2M-iLt4QUqnkqI"
}


class DiscordClient:
    def __init__(self, auth_token: str):
        self.headers = {"authorization": auth_token}
        self.base_url = "https://discord.com/api/v9"

    def get_json_response(self, url):
        try:
            print(f"GET/ {url}")
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(e)
            return None

    def test_connection(self):
        endpoint = "https://discord.com/api/v9/channels/1493015468980568068/messages?limit=100&around=1493015468980568068"
        test_data = self.get_json_response(endpoint)
        return test_data

    def get_threads_in_channel(self, channel_id: str, limit: int = 100):
        message_type = 18
        page_size = 100  # discord api limits
        endpoint = f"{self.base_url}/channels/{channel_id}/messages?limit={page_size}&message_type={message_type}"

        responses = []
        while True:
            data = self.get_json_response(endpoint)
            responses.extend(data)
            if len(responses) >= limit:
                break
            endpoint = f"{self.base_url}/channels/{channel_id}/messages?limit={page_size}&before={data[-1]['id']}"

        threads = []
        for t in responses:
            if t["type"] == message_type:
                threads.append(t)
        return threads

    def get_messages(self, channel_id: str, limit: int = 100):
        # Safe to assume that a thread always < 100 messages since they keep creating multiple threads for the same dispute
        endpoint = f"{self.base_url}/channels/{channel_id}/messages?limit={limit}"
        data = self.get_json_response(endpoint)
        return data

    def get_guild_threads(self, guild_id: str, limit: int = 100):
        endpoint = f"{self.base_url}/guilds/{guild_id}/threads/active?limit={limit}"
        return self.get_json_response(endpoint)

    def get_guild_members(self, guild_id: str, limit: int = 1000, after: str = None):
        endpoint = (
            f"{self.base_url}/guilds/{guild_id}/members?limit={limit}&after={after}"
        )
        return self.get_json_response(endpoint)


# with open("data/discord/1493015468980568068.json", "w") as f:
#     json.dump(d, f, indent=2)

# print(response_minimal.json())
# print(response_full.json())

# guild : [channels_to_track]
guild_channel_map = {
    "name": "uma-official",
    "id": "718590743446290492",
    "channels": [
        "964000735073284127",  # thread:disputes
    ],
    "name": "polymarket-official",
    "id": "710897173927297116",
    "channels": [
        "1478933105262858321",  # thread:climate
    ],
}


from tqdm import tqdm


def scrape_channel(client: DiscordClient, channel_id: str, max_threads: int = -1):
    run_dir = int(time.time())
    os.makedirs(f"data/discord/{run_dir}", exist_ok=True)
    threads = client.get_threads_in_channel(channel_id, 1000)
    with open(f"data/discord/{run_dir}/channel_{channel_id}.json", "w") as f:
        json.dump(threads, f, indent=4)

    messages = []
    for t in tqdm(threads[0:max_threads], desc="Scraping threads", total=len(threads)):
        t_id = t["id"]
        t_d = client.get_messages(t_id)
        for m in t_d:
            m.update({"thread_id": t_id})
        messages.extend(t_d)
    with open(f"data/discord/{run_dir}/messages_{channel_id}.json", "w") as f:
        json.dump(messages, f, indent=4)


if __name__ == "__main__":
    auth_token = (
        "NjE0MzgzODg2MzYwNjQxNTU2.Gjkk3n.wbX058CObJhZW8lQQW0mqX2U2M-iLt4QUqnkqI"
    )
    client = DiscordClient(auth_token)
    channel_id = "964000735073284127"
    scrape_channel(client, channel_id)
