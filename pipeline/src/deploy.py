from prefect import flow

if __name__ == "__main__":
    print("Connecting to Prefect Server and registering deployment...")

    # Load flow from local source so worker reads from its local environment/filesystem
    deployed_flow = flow.from_source(
        source=".",
        entrypoint="src/prefect_flow.py:polydispute_pipeline_flow",
    )

    deployed_flow.deploy(
        name="polydispute-unified-pipeline-production",
        work_pool_name="polydispute-pool",
        cron="0 */4 * * *",  # Example: Run every 4 hours
        build=False,
    )

    print("Deployment successfully registered!")
