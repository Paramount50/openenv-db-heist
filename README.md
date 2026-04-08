---
title: DB Repair Environment
emoji: "\u26A0\uFE0F"
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 8000
---

# Database Repair Environment (DB Heist)

A dynamic, stateful OpenEnv environment where an AI acts as an Autonomous Database Administrator (DBA). The agent is given access to a "breached" or "corrupted" SQLite database and must run live SQL queries to explore schemas, identify anomalies, and execute `UPDATE` or `DELETE` statements to neutralize threats and restore data integrity.

## Motivation

While many LLM environments focus on text manipulation or web browsing, deep backend system management is a frontier for autonomous agents. This environment tests **System 2 reasoning** and **stateful execution**: the agent must inspect a database it doesn't know, trace logical errors across joined tables, and write strictly valid SQL DML to fix it without destroying good data.

## Environment Mechanics

On reset, an in-memory `sqlite3` database is initialized with realistic tables depending on the difficulty. The agent issues **one action per step**: a SQL query string.

- If `is_final` is `False`, the environment executes the SQL and returns up to 50 rows (for `SELECT`) or the number of rows affected (for `UPDATE`/`DELETE`). SQLite syntax errors are returned in the observation.
- If `is_final` is `True`, the environment runs a hidden validation check against the database state to calculate the final reward (0.0 to 1.0).

## Action Space

```python
class DBQueryAction(Action):
    query: str       # e.g., "SELECT * FROM users LIMIT 10"
    is_final: bool   # Set to True to finish and be graded
```

## Observation Space

```python
class DBRepairObservation(Observation):
    query_result: List[Dict]  # Rows returned by the latest query
    query_error: str          # SQLite error traceback (if any)
    schema_info: str          # Current table DDLs
    task_name: str
    step: int
    feedback: str             # Success counts, task objectives, or errors
```

## Tasks

### Task 1: Easy - The Leaked Token
**Scenario**: A sensitive API key was accidentally logged.
**Objective**: Query the `server_logs` table, identify the leaked Stripe API key (starts with `pk_live_`), and `DELETE` that specific row to prevent credential scraping.

### Task 2: Medium - The Proxy Hacker
**Scenario**: A bad actor breached accounts and inflated balances.
**Objective**: Identify which users logged in via `AnonymousProxy` in the `auth_logs` table. Join that with the `users` table and `UPDATE` only those compromised accounts' balances back to `0`.

### Task 3: Hard - The Time Paradox (Forged Sessions)
**Scenario**: An attacker forged a token and forced a transaction without logging in.
**Objective**: Cross-reference timestamps in `logins` and `transactions` tables. Find the single user who executed a transaction *before* their login timestamp. Execute an `UPDATE` in the `accounts` table setting their `status` to `'banned'`.

## Reward Validation

When `is_final = True` triggers the grading phase:
- The environment runs a secure, invisible query to verify whether the attacker's row is gone while innocent rows persist, or whether compromised accounts are reset properly.
- Output is strictly 1.0 (Success), Partial (0.0-0.9), or 0.0 (Failure).

## Setup and Usage

### Local Runtime
```bash
uv lock
pip install -e .
```

### Run Server Locally
```bash
uvicorn server.app:app --host 0.0.0.0 --port 8000
```

### Run Inference Client
```bash
export HF_TOKEN=your_token_here
export API_BASE_URL=https://router.huggingface.co/v1
export MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
python inference.py
```

## License

BSD 3-Clause License
