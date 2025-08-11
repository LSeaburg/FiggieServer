from __future__ import annotations

from typing import Any, Dict, List

import dash
from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State, ALL

from dashboard.config.agent_specs import get_params_for_module, ParamSpec
from dashboard.config.agent_specs import AgentSpec
from dashboard.config import MIN_POLLING_RATE, MAX_PLAYERS, DEFAULT_POLLING_RATE
from dashboard.config.ids import (
    NUM_PLAYERS,
    agent_block_id,
    agent_module_id,
    agent_params_container_id,
)


def register_agent_callbacks(app: Dash, agent_specs: List[AgentSpec]):
    @app.callback(
        [Output(agent_block_id(i), 'style') for i in range(1, MAX_PLAYERS + 1)],
        Input(NUM_PLAYERS, 'value'),
    )
    def update_agent_configs(num_players):  # noqa: F401
        styles = []
        for i in range(1, MAX_PLAYERS + 1):
            styles.append({'display': 'block'} if i <= (num_players or 0) else {'display': 'none'})
        return styles

    def render_param_input(agent_index: int, param_spec: ParamSpec, value: Any) -> html.Div:
        name = param_spec.get("name")
        label = name.replace("_", " ").title() if isinstance(name, str) else str(name)
        ptype = param_spec.get("type", "text")
        min_val = param_spec.get("min")
        max_val = param_spec.get("max")
        step = None
        input_type = 'text'
        if ptype == 'int':
            input_type = 'number'
            step = 1
        elif ptype == 'float':
            input_type = 'number'
            step = 0.01
        elif ptype == 'bool':
            return html.Div([
                html.Label(label, className="agent-param-label"),
                dcc.RadioItems(
                    id={"type": "agent-param", "idx": agent_index, "name": name},
                    options=[{"label": "True", "value": True}, {"label": "False", "value": False}],
                    value=bool(value) if value is not None else False,
                    inline=True,
                    className="radio-group",
                ),
            ], className="agent-param")
        return html.Div([
            html.Label(label, className="agent-param-label"),
            dcc.Input(
                id={"type": "agent-param", "idx": agent_index, "name": name},
                type=input_type,
                value=value,
                min=min_val,
                max=max_val,
                step=step,
                className="agent-input",
            ),
        ], className="agent-param")

    @app.callback(
        Output({'type': 'agent-params-container', 'idx': ALL}, 'children'),
        Input({'type': 'agent-module', 'idx': ALL}, 'value'),
        State(NUM_PLAYERS, 'value'),
        State({'type': 'agent-param', 'idx': ALL, 'name': ALL}, 'value'),
        State({'type': 'agent-param', 'idx': ALL, 'name': ALL}, 'id'),
        prevent_initial_call=False,
    )
    def render_agent_params(module_values, num_players, param_values, param_ids):
        triggered_id = dash.callback_context.triggered_id
        
        changed_agent_idx = None
        if isinstance(triggered_id, dict):
            changed_agent_idx = triggered_id.get('idx')

        current_params = {}
        if param_ids and param_values:
            for id_dict, value in zip(param_ids, param_values):
                agent_idx = id_dict['idx']
                param_name = id_dict['name']
                if agent_idx not in current_params:
                    current_params[agent_idx] = {}
                current_params[agent_idx][param_name] = value
        
        params_to_render = []
        for i, module_value in enumerate(module_values):
            agent_idx = i + 1
            if agent_idx > (num_players or 0):
                params_to_render.append([])
                continue
            
            params = get_params_for_module(agent_specs, module_value) if module_value else []
            rendered = []
            
            # If this is the agent whose type was just changed, we want to render the new
            # params with their default values.
            if agent_idx == changed_agent_idx:
                 rendered = [render_param_input(agent_idx, p, p.get('default')) for p in params]
            else:
                # Otherwise, we use the existing values from the UI
                agent_current_params = current_params.get(agent_idx, {})
                for p in params:
                    name = p.get('name')
                    value = agent_current_params.get(name, p.get('default'))
                    rendered.append(render_param_input(agent_idx, p, value))

            params_to_render.append(rendered)
            
        return params_to_render


