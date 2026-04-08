"""
Inference Script — DB Repair Environment
==============================================
MANDATORY
- Before submitting, ensure the following variables are defined:
    API_BASE_URL, MODEL_NAME, HF_TOKEN
- Output format must strictly adhere to the exact STDOUT format below.

STDOUT FORMAT
    [START] task=<task_name> env=<benchmark> model=<model_name>
    [STEP]  step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
    [END]   success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...,rn>
"""

import sys
import asyncio
import json
import os
import textwrap
from typing import Any, Dict, List, Optional

from openai import OpenAI

from models import DBQueryAction, DBRepairObservation
from client import DBRepairEnv

LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")
HF_TOKEN = os.getenv("HF_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")

TASKS = os.getenv("DB_REPAIR_TASKS", "easy,medium,hard").split(",")
BENCHMARK = "db_repair_env"
MAX_STEPS = 10
TEMPERATURE = 0.3
MAX_TOKENS = 500

SYSTEM_PROMPT = textwrap.dedent("""
You are an expert Autonomous Database Administrator (DBA).
You are connected to an active SQLite database. Your goal is to explore the database, identify the corrupted or breached data according to your current objective, and execute SQL commands to repair the state.

Rules:
1. You can freely execute any SQLite command (SELECT, UPDATE, DELETE).
2. Begin by exploring schemas and SELECTing data to understand the layout and pinpoint issues.
3. Once you identify the anomaly, issue the correct UPDATE or DELETE statement.
4. When you believe the database is successfully repaired to meet the objective, you MUST set "is_final" to true in your JSON output.

Output format MUST be EXACTLY a JSON object with two fields (and nothing else):
{
  "query": "SELECT * FROM users LIMIT 5",
  "is_final": false
}
""").strip()

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )

def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.2f} rewards={rewards_str}",
        flush=True,
    )

def parse_model_response(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
        return {
            "query": data.get("query", ""),
            "is_final": bool(data.get("is_final", False))
        }
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
                return {
                    "query": data.get("query", ""),
                    "is_final": bool(data.get("is_final", False))
                }
            except json.JSONDecodeError:
                pass
    return {"query": "", "is_final": False}

def get_sql_response(client: OpenAI, obs: DBRepairObservation, conversation: list) -> Dict[str, Any]:
    user_prompt = f"""[Environment Status]
Objective & Feedback: {obs.feedback}
Schema:
{obs.schema_info}
---
[Last Query Results]
Rows fetched: {len(obs.query_result)}
Sample: {json.dumps(obs.query_result[:5], indent=2)}

[Errors]
{obs.query_error if obs.query_error else 'None'}

What is your next SQL command? Remember formatting rules."""

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation + [{"role": "user", "content": user_prompt}]
    
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        text = (completion.choices[0].message.content or "").strip()
        parsed = parse_model_response(text)
        
        # update conversation stream
        conversation.append({"role": "user", "content": user_prompt})
        conversation.append({"role": "assistant", "content": json.dumps(parsed)})
        
        return parsed
    except Exception as exc:
        print(f"[DEBUG] Model request failed: {exc}", file=sys.stderr, flush=True)
        return {"query": "", "is_final": False}

async def run_task(client: OpenAI, env: DBRepairEnv, task_name: str) -> float:
    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    log_start(task=f"db-repair-{task_name}", env=BENCHMARK, model=MODEL_NAME)

    try:
        result = await env.reset(task=task_name)
        obs = result.observation
        done = result.done

        conversation = []

        for step in range(1, MAX_STEPS + 1):
            if done:
                break

            action_data = get_sql_response(client, obs, conversation)
            query = action_data.get("query", "")
            is_final = action_data.get("is_final", False)
            
            # format truncated string for logging safe output
            action_log = f"query({query[:30]}...)|final={is_final}" if len(query) > 30 else f"query({query})|final={is_final}"

            action = DBQueryAction(query=query, is_final=is_final)
            result = await env.step(action)

            obs = result.observation
            reward = result.reward or 0.0
            done = result.done
            error = obs.query_error if obs.query_error else None

            rewards.append(reward)
            steps_taken = step

            log_step(step=step, action=action_log, reward=reward, done=done, error=error)

            if done:
                break

        score = sum(rewards)
        score = min(max(score, 0.0), 1.0)
        success = score >= 1.0

    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

    return score

async def main() -> None:
    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

    if LOCAL_IMAGE_NAME:
        env = await DBRepairEnv.from_docker_image(LOCAL_IMAGE_NAME)
    else:
        base_url = os.getenv("ENV_BASE_URL", "http://localhost:8000")
        env = DBRepairEnv(base_url=base_url)

    try:
        scores = {}
        for task in TASKS:
            task = task.strip()
            if task:
                score = await run_task(client, env, task)
                scores[task] = score

        if scores:
            avg = sum(scores.values()) / len(scores)
            print(f"\n[SUMMARY] Average score across all tasks: {avg:.3f}", file=sys.stderr, flush=True)
            for t, s in scores.items():
                print(f"  {t}: {s:.3f}", file=sys.stderr, flush=True)
    finally:
        try:
            await env.close()
        except Exception as e:
            print(f"[DEBUG] env.close() error: {e}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    asyncio.run(main())
