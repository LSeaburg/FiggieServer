import logging
import json
import time
from typing import Any, Dict, List, Optional

import pandas as pd

from figgie_server.db import get_connection
from ..config.settings import EXPERIMENTS_CACHE_TTL
from .queries import (
    FETCH_EXPERIMENT_STATS_SQL,
    FETCH_AGENT_STATS_SQL,
    FETCH_INDIVIDUAL_PROFITS_SQL,
)
from .metrics import (
    list_experiments as svc_list_experiments,
    fetch_metrics_df as svc_fetch_metrics_df,
    fetch_individual_profits_df as svc_fetch_individual_profits_df,
    fetch_results_bundle as svc_fetch_results_bundle,
)

class DataService:
    """Manages data fetching and caching for the dashboard"""

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self._experiments_cache: Optional[List[Dict[str, Any]]] = None
        self._last_experiments_update: float = 0
        self._cache_ttl: int = EXPERIMENTS_CACHE_TTL
        self._metrics_cache: Dict[int, Dict[str, Any]] = {}

    def fetch_experiments(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        current_time = time.time()
        if (
            not force_refresh
            and self._experiments_cache is not None
            and current_time - self._last_experiments_update < self._cache_ttl
        ):
            return self._experiments_cache

        try:
            experiments = svc_list_experiments()
            self._experiments_cache = experiments
            self._last_experiments_update = current_time
            return experiments
        except Exception:
            self._logger.exception("Error fetching experiments")
            return []

    def fetch_metrics(self, experiment_id: int) -> pd.DataFrame:
        try:
            cached = self._metrics_cache.get(experiment_id)
            if cached and (time.time() - cached.get("ts", 0) < 2):
                df = cached["metrics"].copy()
            else:
                df, profits = svc_fetch_results_bundle(experiment_id)
                self._metrics_cache[experiment_id] = {"metrics": df.copy(), "profits": profits.copy(), "ts": time.time()}
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
            cached = self._metrics_cache.get(experiment_id)
            if cached and (time.time() - cached.get("ts", 0) < 2):
                return cached["profits"].copy()
            # If not cached, fetch both to populate cache
            df_metrics, df_profits = svc_fetch_results_bundle(experiment_id)
            self._metrics_cache[experiment_id] = {"metrics": df_metrics.copy(), "profits": df_profits.copy(), "ts": time.time()}
            return df_profits
        except Exception:
            self._logger.exception("Error fetching individual profits for experiment_id=%s", experiment_id)
            return pd.DataFrame()
