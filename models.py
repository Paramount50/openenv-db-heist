"""
Data models for the DB Repair Environment.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from openenv.core.env_server.types import Action, Observation


class DBQueryAction(Action):
    """
    Action representing an SQL query to execute on the database.
    """
    query: str = Field(description="The SQL query to execute")
    is_final: bool = Field(default=False, description="Set to true when the repairs are finished to trigger grading")


class DBRepairObservation(BaseModel):
    """
    Client-side Observation returning the results of a query and database schema.
    """
    query_result: List[Dict[str, Any]] = Field(default_factory=list, description="Rows returned from the SQL query")
    query_error: str = Field(default="", description="SQLite error message if the query failed")
    schema_info: str = Field(default="", description="The current DDL definitions of the database tables")
    task_name: str = Field(default="", description="Current difficulty task")
    step: int = Field(default=0, description="Current step number")
    feedback: str = Field(default="", description="Any system feedback")
    done: bool = Field(default=False, description="Whether the episode is done")
    reward: Optional[float] = Field(default=None, description="Reward achieved (if done)")
