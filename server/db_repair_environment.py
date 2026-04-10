"""
DB Repair Environment - Server-side implementation.

A dynamic OpenEnv environment where an AI agent connects to a "corrupted" SQLite
database. The agent must use SQL queries (exploration + DML) to fix the data.
Three tasks:
  1. easy: Delete leaked API key in logs.
  2. medium: Fix altered balances using auth origin cross-referencing.
  3. hard: Find a rogue transaction based on anomalous timeframes and ban user.
"""

import sqlite3
import uuid
from typing import Any, Optional, Tuple

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import Action, State
from server.models import DBRepairServerObservation

# ─── Task Data ────────────────────────────────────────────────────────────────

def init_db_easy() -> Tuple[sqlite3.Connection, str]:
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE server_logs (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            log_level TEXT,
            message TEXT
        );
        INSERT INTO server_logs (timestamp, log_level, message) VALUES ('2026-04-08T08:00:00Z', 'INFO', 'Server started successfully.');
        INSERT INTO server_logs (timestamp, log_level, message) VALUES ('2026-04-08T08:05:22Z', 'ERROR', 'Failed to connect to redis.');
        INSERT INTO server_logs (timestamp, log_level, message) VALUES ('2026-04-08T08:12:11Z', 'WARNING', 'High memory usage detected.');
        INSERT INTO server_logs (timestamp, log_level, message) VALUES ('2026-04-08T08:15:33Z', 'DEBUG', 'Connected using API_KEY=pk_live_8f7b3a9c1e0d2f4b...');
        INSERT INTO server_logs (timestamp, log_level, message) VALUES ('2026-04-08T08:20:00Z', 'INFO', 'Scheduled backup completed.');
    """)
    desc = "EASY: Find the leaked Stripe API key (starts with 'pk_live_') in the `server_logs` table and DELETE that specific row to secure the system."
    return db, desc

def check_db_easy(db: sqlite3.Connection) -> float:
    # Check if the row with API key is deleted, and others remain.
    cur = db.execute("SELECT COUNT(*) as c FROM server_logs")
    count = cur.fetchone()['c']
    cur = db.execute("SELECT COUNT(*) as c FROM server_logs WHERE message LIKE '%pk_live_%'")
    leaks = cur.fetchone()['c']
    if leaks == 0 and count == 4:
        return 0.99
    return 0.01


def init_db_medium() -> Tuple[sqlite3.Connection, str]:
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER
        );
        CREATE TABLE auth_logs (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            ip_address TEXT,
            user_agent TEXT
        );
        INSERT INTO users (id, username, balance) VALUES (1, 'alice123', 500);
        INSERT INTO users (id, username, balance) VALUES (2, 'bob_builder', 9999);
        INSERT INTO users (id, username, balance) VALUES (3, 'carol_d', 150);
        INSERT INTO users (id, username, balance) VALUES (4, 'dave_sec', 9999);
        
        INSERT INTO auth_logs (user_id, ip_address, user_agent) VALUES (1, '192.168.1.1', 'Mozilla/5.0');
        INSERT INTO auth_logs (user_id, ip_address, user_agent) VALUES (2, '10.0.0.9', 'AnonymousProxy/v1');
        INSERT INTO auth_logs (user_id, ip_address, user_agent) VALUES (3, '172.16.0.5', 'Safari/5.0');
        INSERT INTO auth_logs (user_id, ip_address, user_agent) VALUES (4, '10.0.0.12', 'AnonymousProxy/v1');
    """)
    desc = "MEDIUM: A hacker manipulated balances to 9999 for accounts they compromised via an 'AnonymousProxy'. Find these users by joining `users` and `auth_logs` where user_agent like 'AnonymousProxy%', and UPDATE their balances to 0."
    return db, desc

def check_db_medium(db: sqlite3.Connection) -> float:
    # Check balances of the compromised users are 0 and innocent users are intact
    cur = db.execute("SELECT id, balance FROM users")
    rows = cur.fetchall()
    scores = 0.0
    for r in rows:
        uid, bal = r['id'], r['balance']
        if uid in (2, 4) and bal == 0:
            scores += 0.25
        elif uid == 1 and bal == 500:
            scores += 0.25
        elif uid == 3 and bal == 150:
            scores += 0.25
            
    # Max score 0.99, strictly within (0, 1)
    raw_score = (scores / 0.75) if scores > 0 else 0.0
    if raw_score >= 1.0:
        return 0.99
    elif raw_score <= 0.0:
        return 0.01
    return raw_score


def init_db_hard() -> Tuple[sqlite3.Connection, str]:
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE accounts (
            user_id INTEGER PRIMARY KEY,
            status TEXT
        );
        CREATE TABLE logins (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            login_time TEXT
        );
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            amount INTEGER,
            timestamp TEXT
        );
        
        INSERT INTO accounts (user_id, status) VALUES (101, 'active');
        INSERT INTO accounts (user_id, status) VALUES (102, 'active');
        INSERT INTO accounts (user_id, status) VALUES (103, 'active');
        
        INSERT INTO logins (user_id, login_time) VALUES (101, '2026-04-08 10:00:00');
        INSERT INTO logins (user_id, login_time) VALUES (102, '2026-04-08 11:30:00');
        INSERT INTO logins (user_id, login_time) VALUES (103, '2026-04-08 14:00:00');
        
        INSERT INTO transactions (user_id, amount, timestamp) VALUES (101, 50, '2026-04-08 10:15:00');
        -- Rogue transaction happens BEFORE login (hacked session)
        INSERT INTO transactions (user_id, amount, timestamp) VALUES (102, 10000, '2026-04-08 09:12:00');
        INSERT INTO transactions (user_id, amount, timestamp) VALUES (102, 500, '2026-04-08 11:45:00');
        INSERT INTO transactions (user_id, amount, timestamp) VALUES (103, 100, '2026-04-08 14:05:00');
    """)
    desc = "HARD: A user executed a transaction *before* they logged in, indicating a forged session token. Cross-reference `transactions` and `logins` to find the rogue internal user_id, then UPDATE only their account `status` to 'banned' in the `accounts` table."
    return db, desc

def check_db_hard(db: sqlite3.Connection) -> float:
    # User 102 should be 'banned', 101/103 'active'
    cur = db.execute("SELECT user_id, status FROM accounts")
    rows = cur.fetchall()
    mapping = {r['user_id']: r['status'] for r in rows}
    
    if mapping.get(102) == 'banned' and mapping.get(101) == 'active' and mapping.get(103) == 'active':
        return 0.99
    return 0.01


class DBRepairEnvironment(Environment):
    """
    DB Repair Environment.
    
    The AI acts as a DBA investigating and patching corruption using SQL.
    """

    def __init__(self):
        super().__init__()
        self._episode_id: str = str(uuid.uuid4())
        self._step_count: int = 0
        self._task: str = "easy"
        self._db: Optional[sqlite3.Connection] = None
        self._done: bool = False
        self._last_feedback: str = ""

    def _get_schema(self) -> str:
        if not self._db:
            return ""
        try:
            cur = self._db.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
            tables = cur.fetchall()
            return "\n".join([f"-- Table: {t['name']}\n{t['sql']};" for t in tables])
        except Exception:
            return ""

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs: Any,
    ) -> DBRepairServerObservation:
        task = kwargs.get("task", "easy")
        if task not in ["easy", "medium", "hard"]:
            task = "easy"

        if self._db:
            self._db.close()

        self._episode_id = episode_id or str(uuid.uuid4())
        self._step_count = 0
        self._task = task
        self._done = False
        
        if task == "easy":
            self._db, desc = init_db_easy()
        elif task == "medium":
            self._db, desc = init_db_medium()
        else:
            self._db, desc = init_db_hard()

        self._last_feedback = f"Task: {task.upper()}\nObjective: {desc}\nYou can execute standard SQLite SQL statements (SELECT, UPDATE, DELETE). Set is_final=True when repairs are complete."

        return DBRepairServerObservation(
            done=False,
            reward=0.0,
            query_result=[],
            query_error="",
            schema_info=self._get_schema(),
            task_name=self._task,
            step=0,
            feedback=self._last_feedback
        )

    def step(
        self,
        action: Action,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> DBRepairServerObservation:
        self._step_count += 1

        if self._done or not self._db:
            return DBRepairServerObservation(
                done=True,
                reward=0.0,
                task_name=self._task,
                step=self._step_count,
                feedback="Episode already finished.",
            )

        # Parse submitted action
        if hasattr(action, 'model_dump'):
            action_data = action.model_dump()
        elif isinstance(action, dict):
            action_data = action
        else:
            action_data = {}

        sql = action_data.get("query", "").strip()
        is_final = action_data.get("is_final", False)

        error_msg = ""
        results = []

        if is_final:
            # Grading
            if self._task == "easy":
                score = check_db_easy(self._db)
            elif self._task == "medium":
                score = check_db_medium(self._db)
            else:
                score = check_db_hard(self._db)
                
            self._done = True
            
            if score >= 0.99:
                self._last_feedback = "SUCCESS! Database repairs are perfectly applied."
            elif score > 0.01:
                self._last_feedback = f"PARTIAL SUCCESS. Score: {score}. Database is slightly cleaner but not perfect."
            else:
                self._last_feedback = "FAILED. The final database state does not match the expected repaired state."
                
            return DBRepairServerObservation(
                done=True,
                reward=score,
                query_result=[],
                query_error="",
                schema_info=self._get_schema(),
                task_name=self._task,
                step=self._step_count,
                feedback=self._last_feedback,
            )

        # Execute query if not final
        if sql:
            try:
                cur = self._db.execute(sql)
                if sql.upper().startswith("SELECT"):
                    fetched = cur.fetchall()
                    # Limit to ~50 rows for safety and context limits
                    results = [dict(row) for row in fetched[:50]]
                    self._last_feedback = f"Query executed successfully. Returned {len(fetched)} rows."
                    if len(fetched) > 50:
                        self._last_feedback += " (Results truncated to 50)"
                else:
                    self._db.commit()
                    self._last_feedback = f"Query executed successfully. {cur.rowcount} row(s) affected."
            except sqlite3.Error as e:
                error_msg = str(e)
                self._last_feedback = f"SQLite Error: {error_msg}"
            except Exception as e:
                error_msg = str(e)
                self._last_feedback = f"System Error: {error_msg}"

        return DBRepairServerObservation(
            done=False,
            reward=0.0,
            query_result=results,
            query_error=error_msg,
            schema_info=self._get_schema(),
            task_name=self._task,
            step=self._step_count,
            feedback=self._last_feedback
        )

    @property
    def state(self) -> State:
        return State(
            episode_id=self._episode_id,
            step_count=self._step_count,
        )

    def close(self) -> None:
        if self._db:
            self._db.close()
            self._db = None
