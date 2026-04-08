"""
DB Repair Environment Client.
"""

from typing import Any, Dict

from openenv.core.client_types import StepResult
from openenv.core.env_client import EnvClient
from openenv.core.env_server.types import State

from models import DBQueryAction, DBRepairObservation


class DBRepairEnv(EnvClient[DBQueryAction, DBRepairObservation, State]):
    """
    Client for DB Repair Environment.
    """

    def _step_payload(self, action: DBQueryAction) -> Dict[str, Any]:
        if isinstance(action, dict):
            return action
        if hasattr(action, "model_dump"):
            return action.model_dump()
        return dict(action)

    def _parse_result(self, payload: Dict[str, Any]) -> StepResult[DBRepairObservation]:
        obs_data = payload.get("observation", {})
        reward = payload.get("reward")
        done = payload.get("done", False)

        observation = DBRepairObservation(
            query_result=obs_data.get("query_result", []),
            query_error=obs_data.get("query_error", ""),
            schema_info=obs_data.get("schema_info", ""),
            task_name=obs_data.get("task_name", ""),
            step=obs_data.get("step", 0),
            feedback=obs_data.get("feedback", ""),
            done=done,
            reward=reward,
        )

        return StepResult(
            observation=observation,
            reward=reward,
            done=done,
        )

    def _parse_state(self, payload: Dict[str, Any]) -> State:
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
        )
