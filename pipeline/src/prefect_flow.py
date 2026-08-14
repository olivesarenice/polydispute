from datetime import datetime, timedelta, timezone
from prefect import flow, task, get_run_logger

from pipes.discord.pull import pull_discord_stage
from pipes.discord.load import load_discord_stage
from pipes.polymarket.pull import pull_polymarket_stage
from pipes.polymarket.load import load_polymarket_stage, clean_polymarket_stage
from pipes.umarocks.pull import pull_uma_rocks_signals
from pipes.umarocks.load import load_uma_rocks_stage
from pipes.price_history.pull import pull_dispute_price_history
from pipes.price_history.load import load_price_history_stage
from utils.time_utils import TimeWindow

# --- Tasks ---

@task(name="Discord Pipeline Stage", retries=2, retry_delay_seconds=10)
def run_discord_stage(t0: str | None = None, t1: str | None = None):
    logger = get_run_logger()
    logger.info("Starting Discord stage...")
    now = datetime.now(timezone.utc)
    t1_val = t1 or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    t0_val = t0 or (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_id = f"pipe_dc_{int(now.timestamp())}"
    window = TimeWindow(t0=t0_val, t1=t1_val, run_id=run_id)
    
    pull_discord_stage(window)
    load_discord_stage()
    logger.info("Discord stage completed.")


@task(name="Polymarket Pipeline Stage", retries=2, retry_delay_seconds=10)
def run_polymarket_stage():
    logger = get_run_logger()
    logger.info("Starting Polymarket stage...")
    now = datetime.now(timezone.utc)
    run_id = f"pipe_pm_{int(now.timestamp())}"
    window = TimeWindow(t0=now, t1=now, run_id=run_id)
    
    pull_polymarket_stage(window)
    load_polymarket_stage(window)
    clean_polymarket_stage(run_id)
    logger.info("Polymarket stage completed.")


@task(name="UMA Rocks Stage", retries=2, retry_delay_seconds=10)
def run_uma_stage():
    logger = get_run_logger()
    logger.info("Starting UMA Rocks stage...")
    now = datetime.now(timezone.utc)
    run_id = f"pipe_uma_{int(now.timestamp())}"
    window = TimeWindow(t0=now, t1=now, run_id=run_id)
    
    pull_uma_rocks_signals(window)
    load_uma_rocks_stage(window)
    logger.info("UMA Rocks stage completed.")


@task(name="Price History Stage", retries=2, retry_delay_seconds=10)
def run_price_history_stage(
    limit: int | None = None,
    targets: str = "unresolved",
    fidelity: int = 1,
    backfill_days: int = 14,
    max_threads: int = 8,
):
    logger = get_run_logger()
    logger.info("Starting Price History stage...")
    now = datetime.now(timezone.utc)
    run_id = f"pipe_ph_{int(now.timestamp())}"
    window = TimeWindow(t0=now, t1=now, run_id=run_id)
    
    pull_dispute_price_history(
        window=window,
        limit=limit,
        targets=targets,
        fidelity=fidelity,
        backfill_days=backfill_days,
        max_threads=max_threads,
    )
    load_price_history_stage(window)
    logger.info("Price History stage completed.")


# --- Master Flow ---

@flow(name="polydispute-unified-pipeline")
def polydispute_pipeline_flow(
    discord_t0: str | None = None,
    discord_t1: str | None = None,
    price_history_limit: int | None = None,
    price_history_targets: str = "unresolved",
    price_history_fidelity: int = 1,
    price_history_backfill_days: int = 14,
    price_history_threads: int = 8,
):
    logger = get_run_logger()
    logger.info("Executing Polydispute V3 Master Pipeline Flow...")

    # Phase 1: Discord
    run_discord_stage(t0=discord_t0, t1=discord_t1)

    # Phase 2: Polymarket
    run_polymarket_stage()

    # Phase 3: UMA Rocks
    run_uma_stage()

    # Phase 4: Price History
    run_price_history_stage(
        limit=price_history_limit,
        targets=price_history_targets,
        fidelity=price_history_fidelity,
        backfill_days=price_history_backfill_days,
        max_threads=price_history_threads,
    )

    logger.info("All pipeline phases completed successfully.")


if __name__ == "__main__":
    # Allows direct local testing of the entire flow
    polydispute_pipeline_flow()
