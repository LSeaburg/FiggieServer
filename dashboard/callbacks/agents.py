from __future__ import annotations

from typing import Any, Dict, List

from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State, ALL

from dashboard.config.agent_specs import get_params_for_module, ParamSpec
from dashboard.config.agent_specs import AgentSpec
from dashboard.config import MIN_POLLING_RATE, MAX_PLAYERS, DEFAULT_POLLING_RATE
from dashboard.config.ids import (
    NUM_PLAYERS,
    AGENT_CONFIG_STORE,
    agent_block_id,
    agent_module_id,
    agent_polling_rate_id,
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

    def create_agent_params_callback(agent_idx):
        @app.callback(
            Output(agent_params_container_id(agent_idx), 'children'),
            [Input(agent_module_id(agent_idx), 'value'), Input(NUM_PLAYERS, 'value')],
            [State({'type': 'agent-param', 'idx': agent_idx, 'name': ALL}, 'value'),
             State({'type': 'agent-param', 'idx': agent_idx, 'name': ALL}, 'id')],
            prevent_initial_call=False,
        )
        def render_single_agent_params(module_value, num_players, existing_values, existing_ids):  # noqa: F401
            if agent_idx > (num_players or 0):
                return []
            params = get_params_for_module(agent_specs, module_value) if module_value else []
            existing_param_values: Dict[str, Any] = {}
            if existing_values and existing_ids:
                for val, id_dict in zip(existing_values, existing_ids):
                    if isinstance(id_dict, dict) and 'name' in id_dict:
                        existing_param_values[id_dict['name']] = val
            rendered = []
            for p in params:
                pname = p.get('name')
                value = existing_param_values.get(pname, p.get('default'))
                rendered.append(render_param_input(agent_idx, p, value))
            return rendered
        return render_single_agent_params

    for i in range(1, MAX_PLAYERS + 1):
        create_agent_params_callback(i)

    @app.callback(
        Output(AGENT_CONFIG_STORE, 'data'),
        Input(NUM_PLAYERS, 'value'),
        State(AGENT_CONFIG_STORE, 'data'),
    )
    def initialize_agent_config_store(num_players, current_data):  # noqa: F401
        if current_data and len(current_data) >= (num_players or 0):
            return current_data
        agent_data = []
        for i in range(MAX_PLAYERS):
            if current_data and i < len(current_data):
                agent_data.append(current_data[i])
            else:
                agent_data.append({'module': None, 'polling_rate': DEFAULT_POLLING_RATE, 'extra_kwargs': ''})
        return agent_data


