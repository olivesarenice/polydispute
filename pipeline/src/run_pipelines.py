import argparse
import sys
from datetime import datetime, timedelta, timezone

from loguru import logger

from pipes.discord.pull import pull_discord_stage
from pipes.discord.load import load_discord_stage
from pipes.polymarket.pull import pull_polymarket_stage
from pipes.polymarket.load import load_polymarket_stage, clean_polymarket_stage
from pipes.umarocks.pull import pull_uma_rocks_signals
from pipes.umarocks.load import load_uma_rocks_stage
from pipes.price_history.pull import pull_dispute_price_history
from pipes.price_history.load import load_price_history_stage
from utils.time_utils import TimeWindow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Polydispute V3 Unified Pipeline Orchestrator")
    parser.add_argument(
        "--phase",
        type=str,
        required=True,
        choices=[
            "1", "1_discord", "discord",
            "2", "2_polymarket", "polymarket",
            "3", "3_uma", "uma", "uma_rocks", "umarocks",
            "4", "4_price_history", "price_history",
        ],
        help="Pipeline phase: 1 (Discord), 2 (Polymarket), 3 (UMA Rocks), 4 (Price History)",
    )
    parser.add_argument(
        "--op",
        "--operation",
        type=str,
        dest="operation",
        choices=["pull", "load", "all"],
        default="all",
        help="Operation to execute: pull, load, or all (default: all)",
    )
    parser.add_argument("--t0", type=str, help="Start date/timestamp (ISO8601 or YYYY-MM-DD); required for Discord pull", default=None)
    parser.add_argument("--t1", type=str, help="End date/timestamp (ISO8601 or YYYY-MM-DD); required for Discord pull", default=None)
    parser.add_argument("--limit", type=int, default=None, help="Market limit for price history ingestion (default: None, unlimited)")
    parser.add_argument("--targets", type=str, choices=["unresolved", "all"], default="unresolved", help="Price history target filter: unresolved (default) or all (full backfill)")
    parser.add_argument("--fidelity", type=int, default=1, help="CLOB price history sampling resolution in minutes (default: 1)")
    parser.add_argument("--backfill-days", type=int, default=14, help="Maximum pre-dispute backfill window in days for initial pulls (default: 14)")
    parser.add_argument("--threads", "--max-threads", type=int, dest="max_threads", default=8, help="Number of parallel worker threads for price history pulling (default: 8)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    phase_raw = args.phase.lower()
    if phase_raw == "1" or "discord" in phase_raw:
        phase = "1_discord"
    elif phase_raw == "2" or "polymarket" in phase_raw:
        phase = "2_polymarket"
    elif phase_raw == "3" or "uma" in phase_raw:
        phase = "3_uma"
    elif phase_raw == "4" or "price" in phase_raw:
        phase = "4_price_history"
    else:
        logger.error(f"Unknown phase: {args.phase}")
        return 1

    op = args.operation.lower()
    do_pull = op in ("pull", "all")
    do_load = op in ("load", "all")

    logger.info(f"Starting Unified Pipeline: phase={phase} op={op} (pull={do_pull}, load={do_load})")

    try:
        now = datetime.now(timezone.utc)
        run_timestamp = int(now.timestamp())

        match phase:
            case "1_discord":
                if do_pull:
                    if not args.t0 or not args.t1:
                        logger.info("Discord pull requested without --t0/--t1 dates. Defaulting to last 1 day.")
                        t1_val = args.t1 or now.strftime("%Y-%m-%dT%H:%M:%SZ")
                        t0_val = args.t0 or (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
                    else:
                        t0_val, t1_val = args.t0, args.t1

                    run_id = f"pipe_dc_{run_timestamp}"
                    window = TimeWindow(t0=t0_val, t1=t1_val, run_id=run_id)
                    pull_discord_stage(window)

                if do_load:
                    load_discord_stage()

            case "2_polymarket":
                run_id = f"pipe_pm_{run_timestamp}"
                window = TimeWindow(t0=now, t1=now, run_id=run_id)

                if do_pull:
                    pull_polymarket_stage(window)

                if do_load:
                    load_polymarket_stage(window if do_pull else None)
                    clean_polymarket_stage(run_id)

            case "3_uma":
                run_id = f"pipe_uma_{run_timestamp}"
                window = TimeWindow(t0=now, t1=now, run_id=run_id)

                if do_pull:
                    pull_uma_rocks_signals(window)

                if do_load:
                    load_uma_rocks_stage(window if do_pull else None)

            case "4_price_history":
                run_id = f"pipe_ph_{run_timestamp}"
                window = TimeWindow(t0=now, t1=now, run_id=run_id)

                if do_pull:
                    pull_dispute_price_history(
                        window=window,
                        limit=args.limit,
                        targets=args.targets,
                        fidelity=args.fidelity,
                        backfill_days=args.backfill_days,
                        max_threads=args.max_threads,
                    )

                if do_load:
                    load_price_history_stage(window if do_pull else None)

        logger.success(f"Unified Pipeline completed successfully for phase={phase} op={op}")
        return 0

    except Exception as e:
        logger.exception(f"Pipeline failed for phase={phase}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
