from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

from dash import Dash, html
from dash.dependencies import Input, Output, State, ALL

from dashboard.config import FOUR_PLAYER_SERVER, FIVE_PLAYER_SERVER, MIN_POLLING_RATE, MAX_PLAYERS
from dashboard.config.ids import (
    RUN_OUTPUT,
    SAVE_OUTPUT,
    RUN_BUTTON,
    SAVE_BUTTON,
    EXPERIMENT_DROPDOWN,
    EXPERIMENT_NAME,
    EXPERIMENT_DESCRIPTION,
    NUM_PLAYERS,
    agent_module_id,
    agent_polling_rate_id,
)
from dashboard.services import create_experiment, get_experiment_agents
from dashboard.services.runner import (
    build_agent_configs,
    ensure_server_ready,
    run_experiment_async,
    PreflightError,
)
from dashboard.config.agent_specs import validate_params, get_spec_by_module, AgentSpec
from dashboard.components.messages import success, error, error_list


def register_action_callbacks(app: Dash, data_manager, module_to_attr: Dict[str, str], agent_specs: List[AgentSpec]):
    logger = logging.getLogger(__name__)

    @app.callback(
        Output(SAVE_OUTPUT, 'children'),
        Input(SAVE_BUTTON, 'n_clicks'),
        State(EXPERIMENT_NAME, 'value'),
        State(EXPERIMENT_DESCRIPTION, 'value'),
        State(NUM_PLAYERS, 'value'),
        *[State(agent_module_id(i), 'value') for i in range(1, MAX_PLAYERS + 1)],
        *[State(agent_polling_rate_id(i), 'value') for i in range(1, MAX_PLAYERS + 1)],
        State({'type': 'agent-param', 'idx': ALL, 'name': ALL}, 'value'),
        State({'type': 'agent-param', 'idx': ALL, 'name': ALL}, 'id'),
        prevent_initial_call=True,
    )
    def save_experiment(n_clicks, name, description, num_players, *args):  # noqa: C901
        if not name:
            return error("Experiment name is required")

        modules = args[:MAX_PLAYERS]
        polling_rates = args[MAX_PLAYERS: 2 * MAX_PLAYERS]
        dyn_values = args[2 * MAX_PLAYERS] if len(args) > 2 * MAX_PLAYERS else []
        dyn_ids = args[2 * MAX_PLAYERS + 1] if len(args) > 2 * MAX_PLAYERS + 1 else []

        mapping = dict(module_to_attr)
        errors: List[str] = []

        id_to_value: Dict[str, Any] = {}
        try:
            for cid, val in zip(dyn_ids or [], dyn_values or []):
                if isinstance(cid, dict):
                    key = f"{cid.get('idx')}::{cid.get('name')}"
                    id_to_value[key] = val
        except Exception:
            id_to_value = {}

        validated_agents: List[Tuple[str, str, float, Dict[str, Any]]] = []
        for i in range(num_players or 0):
            module = modules[i]
            if not module:
                errors.append(f"Agent {i+1}: Missing agent module")
                continue
            attr_name = mapping.get(module)
            if not attr_name:
                errors.append(f"Agent {i+1}: Unknown module '{module}'")
                continue
            raw_pr = polling_rates[i] if i < len(polling_rates) else None
            try:
                pr_val = float(raw_pr) if raw_pr is not None else None
            except (TypeError, ValueError):
                pr_val = None
            if pr_val is None or pr_val <= 0:
                errors.append(f"Agent {i+1}: Polling rate is required and must be > 0")

            # Use centralized validation
            spec = get_spec_by_module(agent_specs, module)
            if spec is not None:
                # Build flat kwargs from collected ids
                flat_kwargs: Dict[str, Any] = {}
                for p in spec.get('params', []):
                    pname = p.get('name')
                    if not pname:
                        continue
                    key = f"{i+1}::{pname}"
                    flat_kwargs[pname] = id_to_value.get(key, p.get('default'))
                coerced, val_errors = validate_params(flat_kwargs, spec)
                if val_errors:
                    errors.extend([f"Agent {i+1}: {msg}" for msg in val_errors])
                extra_kwargs = coerced
            else:
                extra_kwargs = {}

            if not errors:
                validated_agents.append((module, attr_name, float(pr_val), extra_kwargs))

        if errors:
            return error_list("Invalid configuration. Please fix the following:", errors)

        try:
            exp_id = create_experiment(name, description, validated_agents)
            return success(f"Saved experiment {exp_id}: {name} with {num_players} configured agents")
        except Exception as e:
            logger.exception("Error saving experiment")
            return error(f"Error saving experiment: {str(e)}")

    @app.callback(
        Output(RUN_OUTPUT, 'children'),
        Input(RUN_BUTTON, 'n_clicks'),
        State(EXPERIMENT_DROPDOWN, 'value'),
        prevent_initial_call=True,
    )
    def run_experiment_callback(n_clicks, exp_id):  # noqa: F401
        if not exp_id:
            return error("Select an experiment to run")
        try:
            rows = get_experiment_agents(exp_id)
            if not rows:
                return error("No agents found for this experiment")

            agents = build_agent_configs(rows)
            server_url = FOUR_PLAYER_SERVER if len(agents) == 4 else FIVE_PLAYER_SERVER
            try:
                ensure_server_ready(server_url)
            except PreflightError as exc:
                return error(str(exc))

            run_experiment_async(agents, server_url, exp_id)
            return success(f"Running experiment {exp_id} with {len(agents)} agents...")
        except Exception as e:
            logger.exception("Error preparing to run experiment")
            return error(f"Error running experiment: {str(e)}")


