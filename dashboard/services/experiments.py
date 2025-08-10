from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from figgie_server.db import get_connection


def create_experiment(
    name: str,
    description: str | None,
    validated_agents: List[Tuple[str, str, float, Dict[str, Any]]],
) -> int:
    """Insert an experiment and its configured agents, returning experiment_id.

    validated_agents: list of tuples (module_name, attr_name, polling_rate, extra_kwargs)
    """
    conn = get_connection()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO experiments
            (name, description, created_at)
            VALUES (%s, %s, %s)
            RETURNING experiment_id
            """,
            (name, description, datetime.now(timezone.utc)),
        )
        exp_id = cursor.fetchone()[0]
        for i, (module, cls_name, pr, extra_kwargs) in enumerate(validated_agents):
            cursor.execute(
                """
                INSERT INTO experiment_agents
                (experiment_id, player_index, module_name, attr_name, polling_rate, extra_kwargs)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (exp_id, i, module, cls_name, pr, json.dumps(extra_kwargs)),
            )
    conn.commit()
    return exp_id


def get_experiment_agents(experiment_id: int) -> List[Tuple[str, str, float, Any]]:
    """Return (module_name, attr_name, polling_rate, extra_kwargs) rows for an experiment."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            'SELECT module_name, attr_name, polling_rate, extra_kwargs FROM experiment_agents WHERE experiment_id = %s ORDER BY player_index;',
            (experiment_id,),
        )
        rows = cur.fetchall()
    return rows


