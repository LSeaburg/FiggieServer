from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import pandas as pd

from figgie_server.db import get_connection
from dashboard.services.queries import (
    FETCH_EXPERIMENT_STATS_SQL,
    FETCH_AGENT_STATS_SQL,
    FETCH_INDIVIDUAL_PROFITS_SQL,
)


def list_experiments() -> List[Dict[str, Any]]:
    """Return experiment summaries for the dropdown and info panel."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(FETCH_EXPERIMENT_STATS_SQL)
        rows = cur.fetchall()

    experiments: List[Dict[str, Any]] = []
    for row in rows:
        exp_id, name, description, created_at, total_games, configured_agents = row
        experiments.append(
            {
                "label": f"{exp_id}: {name} ({total_games} games, {configured_agents} agents)",
                "value": exp_id,
                "name": name,
                "description": description,
                "created_at": created_at.isoformat() if created_at else None,
                "total_games": total_games or 0,
                "configured_agents": configured_agents or 0,
            }
        )
    return experiments


def fetch_metrics_df(experiment_id: int) -> pd.DataFrame:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(FETCH_AGENT_STATS_SQL, (experiment_id,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        df = pd.DataFrame(rows, columns=cols)
    return df


def fetch_individual_profits_df(experiment_id: int) -> pd.DataFrame:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(FETCH_INDIVIDUAL_PROFITS_SQL, (experiment_id,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        df = pd.DataFrame(rows, columns=cols)
    return df


def fetch_results_bundle(experiment_id: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch both metrics and individual profits in one connection for efficiency."""
    conn = get_connection()
    with conn.cursor() as cur:
        # Metrics
        cur.execute(FETCH_AGENT_STATS_SQL, (experiment_id,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        metrics_df = pd.DataFrame(rows, columns=cols)

        # Profits
        cur.execute(FETCH_INDIVIDUAL_PROFITS_SQL, (experiment_id,))
        rows2 = cur.fetchall()
        cols2 = [d[0] for d in cur.description]
        profits_df = pd.DataFrame(rows2, columns=cols2)
    return metrics_df, profits_df


