import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

app = FastAPI(title="Polydispute V3 API")

# Add CORS middleware if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "version": "v3-hybrid"}

@app.get("/api/signals/arb")
def get_arb_signals() -> dict[str, list]:
    # Placeholder: fetch from backend/data/app.db
    return {"signals": []}

@app.get("/api/signals/discord")
def get_discord_stances(market_id: str) -> dict[str, str | list]:
    # Placeholder: fetch from backend/data/app.db
    return {"market_id": market_id, "stances": []}

# Mount static files for the frontend SPA
# This MUST be mounted last so API routes take precedence
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../frontend"))
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    @app.get("/")
    def index() -> dict[str, str]:
        return {"message": "Frontend not found"}

if __name__ == "__main__":
    logger.info("Starting FastAPI server on port 8000")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
