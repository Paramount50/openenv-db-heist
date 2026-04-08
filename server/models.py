"""
Data models for the DB Repair Environment — Server-side.
"""

from typing import Any, Dict, List
from pydantic import Field

from openenv.core.env_server.types import Observation


class DBRepairServerObservation(Observation):
    """
    Server-side Observation with custom fields that are serialized to the HTTP client.
    """
    query_result: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Rows returned from the SQL query"
    )
    query_error: str = Field(default="", description="SQLite error message if the query failed")
    schema_info: str = Field(default="", description="The current DDL definitions of the database tables")
    task_name: str = Field(default="", description="Current task identifier")
    step: int = Field(default=0, description="Current step number")
    feedback: str = Field(default="", description="Any system feedback")
