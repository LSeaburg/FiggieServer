"""Centralized component IDs and helper builders for the dashboard UI."""

from typing import Dict


# Static IDs
EXPERIMENT_DROPDOWN = "experiment-dropdown"
EXPERIMENTS_DATA = "experiments-data"
LAST_UPDATED = "last-updated"
EXPERIMENT_INFO = "experiment-info"

RESULTS_TABLE = "results-table"
METRICS_DATA = "metrics-data"
PROFIT_CHART = "profit-chart"

RUN_BUTTON = "run-button"
RUN_OUTPUT = "run-output"

SAVE_BUTTON = "save-button"
SAVE_OUTPUT = "save-output"

EXPERIMENT_NAME = "experiment-name"
EXPERIMENT_DESCRIPTION = "experiment-description"
NUM_PLAYERS = "num-players"

EXPERIMENT_STORE = "experiment-store"
AGENT_CONFIG_STORE = "agent-config-store"
INTERVAL = "interval-component"


# Agent-related ID builders
def agent_block_id(index: int) -> str:
    return f"agent-block-{index}"


def agent_module_id(index: int) -> Dict[str, object]:
    return {"type": "agent-module", "idx": index}


def agent_polling_rate_id(index: int) -> Dict[str, object]:
    return {"type": "agent-polling-rate", "idx": index}


def agent_params_container_id(index: int) -> Dict[str, int]:
    return {"type": "agent-params-container", "idx": index}


def agent_param_id(index: int, name: str) -> Dict[str, object]:
    return {"type": "agent-param", "idx": index, "name": name}


