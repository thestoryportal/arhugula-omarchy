"""Read the native goal store without changing goals or importing counters."""

import sqlite3
from pathlib import Path
from urllib.parse import quote


def read_goal(database, session):
    database = Path(database).resolve()
    with sqlite3.connect(
        "file:" + quote(str(database)) + "?mode=ro", uri=True
    ) as connection:
        columns = [
            row[1] for row in connection.execute("PRAGMA table_info(thread_goals)")
        ]
        if columns != [
            "thread_id",
            "goal_id",
            "objective",
            "status",
            "token_budget",
            "tokens_used",
            "time_used_seconds",
            "created_at_ms",
            "updated_at_ms",
        ]:
            raise ValueError(
                "native goal store schema changed; do not infer accounting"
            )
        row = connection.execute(
            "SELECT * FROM thread_goals WHERE thread_id=?", (session,)
        ).fetchone()
    if row is None:
        # [LAW:types-are-the-program] Absence is an observed state, never zero usage.
        return {
            "goal": None,
            "remainingTokens": None,
            "completionBudgetReport": None,
            "native_store": {
                "path": str(database),
                "thread_id": session,
                "read_only": True,
            },
        }
    values = dict(zip(columns, row))
    goal = dict(
        threadId=values["thread_id"],
        objective=values["objective"],
        status=values["status"],
        tokensUsed=values["tokens_used"],
        timeUsedSeconds=values["time_used_seconds"],
        createdAt=values["created_at_ms"] // 1000,
        updatedAt=values["updated_at_ms"] // 1000,
    )
    if values["token_budget"] is not None:
        goal["tokenBudget"] = values["token_budget"]
    return {
        "goal": goal,
        "remainingTokens": None
        if values["token_budget"] is None
        else values["token_budget"] - values["tokens_used"],
        "completionBudgetReport": None,
        "native_store": {
            "path": str(database),
            "goal_id": values["goal_id"],
            "updated_at_ms": values["updated_at_ms"],
            "read_only": True,
        },
    }
