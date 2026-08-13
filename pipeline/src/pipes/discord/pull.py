import json
import os
from datetime import datetime
from typing import Optional

from config import DiscordConfig, PipelineConfig
from connectors.discord import DiscordClient
from loguru import logger
from tqdm import tqdm
from utils.time_utils import TimeWindow, get_stage_output_path


def pull_discord_stage(window: TimeWindow) -> str:
    """
    Phase 1 Pull: Scrapes Discord thread starters and messages from the UMA #disputes channel.
    Bounded strictly by window bounds [t0, t1].
    Saves payload to pipeline/data/raw/discord/output_{runtime_unix}.json.
    """
    dc_client = DiscordClient()
    channel_id = DiscordConfig.DISPUTES_CHANNEL_ID

    out_file = get_stage_output_path("discord", window.runtime_unix, "json")

    logger.info(
        f"Phase 1 Pull: Fetching Discord threads from channel {channel_id} (window: {window.iso_t0} -> {window.iso_t1})..."
    )

    threads = dc_client.get_thread_starters(
        channel_id=channel_id,
        limit=DiscordConfig.DEFAULT_LIMIT,
        t0_str=window.iso_t0,
        t1_str=window.iso_t1,
    )

    all_data = []
    for t in tqdm(threads, desc="Fetching Discord threads"):
        thread_dict = t.model_dump()
        messages = dc_client.get_messages(t.id, limit=100)
        thread_dict["messages"] = [m.model_dump() for m in messages]
        all_data.append(thread_dict)

    with open(out_file, "w") as f:
        json.dump(all_data, f, indent=2)

    logger.success(f"Phase 1 Pull Complete: Staged {len(all_data)} Discord threads to {out_file}")
    return out_file
