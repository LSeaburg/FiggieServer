from __future__ import annotations

from typing import Dict, List
from dash import Dash

from dashboard.config.agent_specs import AgentSpec

from .agents import register_agent_callbacks
from .experiments import register_experiment_callbacks
from .results import register_results_callbacks
from .actions import register_action_callbacks


def register_callbacks(app: Dash, data_manager, module_to_attr: Dict[str, str], agent_specs: List[AgentSpec]):
    register_experiment_callbacks(app, data_manager)
    register_results_callbacks(app, data_manager)
    register_agent_callbacks(app, agent_specs)
    register_action_callbacks(app, data_manager, module_to_attr, agent_specs)
