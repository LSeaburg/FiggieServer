from __future__ import annotations

import json
import threading
from typing import List, Tuple, Dict, Any

from agents.dispatcher import preflight_check, run_game, AgentConfig
from agents.dispatcher import ServerBusyError, ServerQueuePendingError, ServerStatusUnavailable


class PreflightError(Exception):
    pass


def build_agent_configs(rows: List[Tuple[str, str, float, Any]]) -> List[AgentConfig]:
    agents: List[AgentConfig] = []
    for module_name, attr_name, pr, extra in rows:
        if isinstance(extra, (str, bytes, bytearray)):
            try:
                kwargs = json.loads(extra)
            except (ValueError, TypeError):
                kwargs = {}
        elif isinstance(extra, dict):
            kwargs = extra.copy()
        else:
            kwargs = {}
        agents.append(AgentConfig(module_name, attr_name, float(pr), kwargs))
    return agents


def ensure_server_ready(server_url: str) -> None:
    try:
        preflight_check(server_url)
    except ServerBusyError as exc:
        raise PreflightError("Server is busy running a game. Please wait for it to complete.") from exc
    except ServerQueuePendingError as exc:
        raise PreflightError("Server is preparing a game with queued players. Please try again shortly.") from exc
    except ServerStatusUnavailable as exc:
        raise PreflightError(f"Could not reach server at {server_url}: {exc}") from exc


def run_experiment_async(agents: List[AgentConfig], server_url: str, experiment_id: int) -> None:
    threading.Thread(target=run_game, args=(agents, server_url, experiment_id), daemon=True).start()


