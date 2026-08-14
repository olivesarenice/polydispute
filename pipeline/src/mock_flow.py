from prefect import flow, task, get_run_logger

@task
def extract_mock_data():
    logger = get_run_logger()
    logger.info("Extracting mock data...")
    return {"status": "ok", "items": 42}

@flow(name="polydispute-mock-flow")
def mock_pipeline_flow():
    logger = get_run_logger()
    logger.info("Starting mock pipeline flow...")
    
    data = extract_mock_data()
    
    logger.info(f"Pipeline finished successfully with data: {data}")

if __name__ == "__main__":
    # This allows you to test the flow locally without the server
    mock_pipeline_flow()
