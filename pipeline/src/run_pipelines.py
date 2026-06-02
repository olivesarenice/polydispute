import argparse
import sys
from loguru import logger

from pull_api import run_incremental, run_historical

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Polydispute V3 Data Pipeline")
    parser.add_argument(
        "--step", 
        type=str, 
        choices=["pull_api", "transform", "data_test"], 
        required=True,
        help="Step to run: pull_api, transform, or data_test"
    )
    parser.add_argument("--mode", type=str, choices=["incremental", "historical", "sync"], default="incremental", help="Run mode for pull_api")
    parser.add_argument("--client", type=str, choices=["polymarket", "discord"], help="Target client for pull_api")
    parser.add_argument("--t0", type=str, help="Start date (YYYY-MM-DD) for historical mode")
    parser.add_argument("--t1", type=str, help="End date (YYYY-MM-DD) for historical mode")
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    logger.info(f"Starting pipeline step={args.step}")
    try:
        match args.step:
            case "pull_api":
                if not args.client:
                    raise ValueError("--client is required for pull_api step")
                    
                match args.mode:
                    case "incremental":
                        run_incremental(args.client)
                    case "historical":
                        if not args.t0 or not args.t1:
                            raise ValueError("--t0 and --t1 are required in historical mode")
                        run_historical(args.client, args.t0, args.t1)
                    case "sync":
                        # We need to import run_sync first
                        from pull_api import run_sync
                        run_sync(args.client)
                    case _:
                        raise ValueError(f"Unknown mode: {args.mode}")
            
            case "transform":
                logger.info("Step 2: Running transformations and moving to clean...")

            case "data_test":
                logger.info("Step 3: Running data validation tests...")
            
            case _:
                raise ValueError(f"Unknown step: {args.step}")
            
        logger.success(f"Completed step: {args.step}")
        return 0
    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
