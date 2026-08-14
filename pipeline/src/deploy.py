import argparse
import os
from prefect_flow import polydispute_pipeline_flow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register Polydispute Pipeline Deployment")
    parser.add_argument(
        "--target",
        choices=["local", "dev"],
        default="dev",
        help="Deployment target: local (polydispute-worker:local on polydispute-local) or dev (ghcr.io image on polydispute-dev)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.target == "local":
        image_name = "polydispute-worker:local"
        pool_name = "polydispute-local"
        deployment_name = "polydispute-pipeline-local"
        cron_schedule = None
    else:
        image_name = "ghcr.io/olivesarenice/polydispute-worker:latest"
        pool_name = "polydispute-dev"
        deployment_name = "polydispute-pipeline-dev"
        cron_schedule = "0 */4 * * *"

    print(f"Connecting to Prefect Server and registering [{deployment_name}] on pool [{pool_name}] using image ({image_name})...")

    # Pass DOPPLER_TOKEN into job_variables so Prefect Docker Worker injects it into spawned containers
    doppler_token = os.environ.get("DOPPLER_TOKEN", "")
    job_vars = {}
    if doppler_token:
        job_vars["env"] = {"DOPPLER_TOKEN": doppler_token}

    polydispute_pipeline_flow.deploy(
        name=deployment_name,
        work_pool_name=pool_name,
        cron=cron_schedule,
        image=image_name,
        build=False,
        job_variables=job_vars,
    )

    print(f"✅ Deployment [{deployment_name}] successfully registered!")
