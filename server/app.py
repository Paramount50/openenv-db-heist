"""
FastAPI application for the DB Repair Environment.

Exposes the DBRepairEnvironment over HTTP endpoints.
"""
import sys
import os

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openenv.core.env_server.http_server import create_app

from server.db_repair_environment import DBRepairEnvironment
from server.models import DBRepairServerObservation
from models import DBQueryAction

# Create the app using OpenEnv's standard factory
app = create_app(
    DBRepairEnvironment, DBQueryAction, DBRepairServerObservation, env_name="db_repair_env"
)

def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
