import argparse
import os

from prefect_flow import polydispute_pipeline_flow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register Polydispute Pipeline Deployment"
    )
    parser.add_argument(
        "--target",
        choices=["local", "dev"],
        default="dev",
        help="Deployment target: local (polydispute-worker:local on polydispute-local) or dev (ghcr.io image on polydispute-dev)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    doppler_token = os.environ.get("DOPPLER_TOKEN", "")

    if args.target == "local":
        pool_name = "polydispute-local"
        deployment_name = "polydispute-pipeline-local"
        image_name = "polydispute-worker:local"

        job_vars = {}
        if doppler_token:
            job_vars["env"] = {"DOPPLER_TOKEN": doppler_token}

        print(
            f"Connecting to Prefect Server and registering [{deployment_name}] on docker pool [{pool_name}] using image ({image_name})..."
        )

        polydispute_pipeline_flow.deploy(
            name=deployment_name,
            work_pool_name=pool_name,
            image=image_name,
            build=False,
            job_variables=job_vars,
        )
    else:
        pool_name = "polydispute-dev"
        deployment_name = "polydispute-pipeline-dev"

        print(
            f"Connecting to Prefect Server and registering [{deployment_name}] on process pool [{pool_name}] via GitHub storage..."
        )

        from prefect import flow

        flow.from_source(
            source="https://github.com/olivesarenice/polydispute.git",
            entrypoint="pipeline/src/prefect_flow.py:polydispute_pipeline_flow",
        ).deploy(
            name=deployment_name,
            work_pool_name=pool_name,
            cron="0 */4 * * *",
        )

    print(f"✅ Deployment [{deployment_name}] successfully registered!")
