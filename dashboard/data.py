import logging
import json
import time
from typing import Any, Dict, List, Optional

import pandas as pd

from figgie_server.db import get_connection
from .sql import (
    FETCH_EXPERIMENT_STATS_SQL,
    FETCH_AGENT_STATS_SQL,
    FETCH_INDIVIDUAL_PROFITS_SQL,
)

class DashboardDataManager:
    """Manages data fetching and caching for the dashboard"""

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self._experiments_cache: Optional[List[Dict[str, Any]]] = None
        self._last_experiments_update: float = 0
        self._cache_ttl: int = 5  # seconds

    def fetch_experiments(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        current_time = time.time()
        if (
            not force_refresh
            and self._experiments_cache is not None
            and current_time - self._last_experiments_update < self._cache_ttl
        ):
            return self._experiments_cache

        try:
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

            self._experiments_cache = experiments
            self._last_experiments_update = current_time
            return experiments
        except Exception:
            self._logger.exception("Error fetching experiments")
            return []

    def fetch_metrics(self, experiment_id: int) -> pd.DataFrame:
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(FETCH_AGENT_STATS_SQL, (experiment_id,))
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
                df = pd.DataFrame(rows, columns=cols)

            # Ensure DataTable-friendly types
            if not df.empty and "extra_kwargs" in df.columns:
                def _to_str(val: Any) -> str:
                    if isinstance(val, (dict, list)):
                        try:
                            return json.dumps(val)
                        except Exception:
                            return str(val)
                    if val is None:
                        return ""
                    return str(val)
                df["extra_kwargs"] = df["extra_kwargs"].apply(_to_str)

            return df
        except Exception:
            self._logger.exception("Error fetching metrics for experiment_id=%s", experiment_id)
            return pd.DataFrame()

    def fetch_individual_profits(self, experiment_id: int) -> pd.DataFrame:
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(FETCH_INDIVIDUAL_PROFITS_SQL, (experiment_id,))
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
                df = pd.DataFrame(rows, columns=cols)
            return df
        except Exception:
            self._logger.exception("Error fetching individual profits for experiment_id=%s", experiment_id)
            return pd.DataFrame()


