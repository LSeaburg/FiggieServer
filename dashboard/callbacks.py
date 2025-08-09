import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate
import plotly.express as px
import plotly.graph_objects as go

from agents.dispatcher import preflight_check, run_game, AgentConfig
from agents.dispatcher import ServerBusyError, ServerQueuePendingError, ServerStatusUnavailable

from .agent_specs import get_params_for_module, AgentSpec, ParamSpec
from .config import FOUR_PLAYER_SERVER, FIVE_PLAYER_SERVER, MIN_POLLING_RATE


def register_callbacks(app: Dash, data_manager, module_to_attr: Dict[str, str], agent_specs: List[AgentSpec]):
    logger = logging.getLogger(__name__)
    # Auto-clear messages
    @app.callback(
        Output('run-output', 'children', allow_duplicate=True),
        Output('run-message-timer', 'disabled', allow_duplicate=True),
        Input('run-message-timer', 'n_intervals'),
        prevent_initial_call=True,
    )
    def clear_run_message(n_intervals):  # noqa: F401
        return "", True

    @app.callback(
        Output('save-output', 'children', allow_duplicate=True),
        Output('save-message-timer', 'disabled', allow_duplicate=True),
        Input('save-message-timer', 'n_intervals'),
        prevent_initial_call=True,
    )
    def clear_save_message(n_intervals):  # noqa: F401
        return "", True

    @app.callback(
        [Output('experiment-dropdown', 'options'), Output('experiments-data', 'children'), Output('last-updated', 'children')],
        Input('interval-component', 'n_intervals'),
        prevent_initial_call=False,
    )
    def update_experiments_list(n_intervals):
        experiments = data_manager.fetch_experiments(force_refresh=True)
        dropdown_options = [{'label': exp['label'], 'value': exp['value']} for exp in experiments]
        timestamp = datetime.now().strftime("%H:%M:%S")
        return dropdown_options, json.dumps(experiments), f"Last updated: {timestamp}"

    @app.callback(
        [Output('results-table', 'data'), Output('metrics-data', 'children'), Output('profit-chart', 'figure')],
        [Input('experiment-dropdown', 'value'), Input('interval-component', 'n_intervals')],
    )
    def update_metrics_and_charts(selected_experiment, n_intervals):  # noqa: F401
        if not selected_experiment:
            empty_fig = go.Figure().add_annotation(text="Select an experiment to view results", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
            return [], "", empty_fig

        df = data_manager.fetch_metrics(selected_experiment)
        if df.empty:
            empty_fig = go.Figure().add_annotation(text="No data available for this experiment", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
            return [], "", empty_fig

        profit_df = data_manager.fetch_individual_profits(selected_experiment)
        if profit_df.empty:
            profit_fig = go.Figure().add_annotation(text="No individual game data available for box plot", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        else:
            profit_fig = px.box(
                profit_df,
                x='agent_name',
                y='profit',
                title='Profit Distribution by Agent',
                labels={'profit': 'Profit per Game', 'agent_name': 'Agent'},
                color='agent_name',
                points='outliers',
            )
            profit_fig.update_layout(height=400, showlegend=False, xaxis_title="Agent", yaxis_title="Profit per Game")

        records = df.to_dict('records')
        for record in records:
            for key, value in record.items():
                if hasattr(value, 'as_tuple'):
                    record[key] = float(value)
                elif pd.isna(value):
                    record[key] = None

        return records, json.dumps(records), profit_fig

    @app.callback(
        Output('experiment-info', 'children'),
        [Input('experiment-dropdown', 'value'), Input('experiments-data', 'children')],
    )
    def update_experiment_info(selected_experiment, experiments_json):  # noqa: F401
        if not selected_experiment or not experiments_json:
            return ""
        try:
            experiments = json.loads(experiments_json)
            experiment = next((exp for exp in experiments if exp['value'] == selected_experiment), None)
            if not experiment:
                return ""
            from .utils import format_timestamp
            return html.Div([
                html.H4(experiment['name']),
                html.P(experiment['description'] or "No description"),
                html.Div([
                    html.Span(f"Games: {experiment['total_games']}", className="stat"),
                    html.Span(f"Agents: {experiment['configured_agents']}", className="stat"),
                ], className="experiment-stats"),
                html.Small(f"Created: {format_timestamp(experiment['created_at'])}"),
            ])
        except Exception:
            logger.exception("Failed to render experiment info")
            return ""

    @app.callback(
        [Output(f'agent-block-{i}', 'style') for i in range(1, 6)],
        Input('num-players', 'value'),
    )
    def update_agent_configs(num_players):  # noqa: F401
        styles = []
        for i in range(1, 6):
            styles.append({'display': 'block'} if i <= (num_players or 0) else {'display': 'none'})
        return styles

    # Parameter input rendering
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

    # Create per-agent dynamic parameter renderers
    def create_agent_params_callback(agent_idx):
        @app.callback(
            Output({"type": "agent-params-container", "idx": agent_idx}, 'children'),
            [Input(f'agent{agent_idx}_module', 'value'), Input('num-players', 'value')],
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

    for i in range(1, 6):
        create_agent_params_callback(i)

    @app.callback(
        Output('agent-config-store', 'data'),
        Input('num-players', 'value'),
        State('agent-config-store', 'data'),
    )
    def initialize_agent_config_store(num_players, current_data):  # noqa: F401
        if current_data and len(current_data) >= (num_players or 0):
            return current_data
        agent_data = []
        for i in range(5):
            if current_data and i < len(current_data):
                agent_data.append(current_data[i])
            else:
                # Default module left as None; UI will populate default selection
                agent_data.append({'module': None, 'polling_rate': 0.25, 'extra_kwargs': ''})
        return agent_data

    @app.callback(
        [Output('save-output', 'children'), Output('save-message-timer', 'disabled')],
        Input('save-button', 'n_clicks'),
        State('experiment-name', 'value'),
        State('experiment-description', 'value'),
        State('num-players', 'value'),
        *[State(f'agent{i}_module', 'value') for i in range(1, 6)],
        *[State(f'agent{i}_polling_rate', 'value') for i in range(1, 6)],
        State({'type': 'agent-param', 'idx': ALL, 'name': ALL}, 'value'),
        State({'type': 'agent-param', 'idx': ALL, 'name': ALL}, 'id'),
    )
    def save_experiment(n_clicks, name, description, num_players, *args):  # noqa: C901
        if not n_clicks:
            return "", True
        if not name:
            return html.Div("Experiment name is required", className="error-message"), True

        modules = args[:5]
        polling_rates = args[5:10]
        dyn_values = args[10] if len(args) > 10 else []
        dyn_ids = args[11] if len(args) > 11 else []

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

            extra_kwargs: Dict[str, Any] = {}
            current_params = get_params_for_module(agent_specs, module)
            for p in current_params:
                pname = p.get('name')
                if pname is None:
                    continue
                ptype = p.get('type', 'text')
                pmin = p.get('min')
                pmax = p.get('max')
                default_val = p.get('default')
                key = f"{i+1}::{pname}"
                value = id_to_value.get(key, default_val)
                try:
                    if ptype == 'int' and value is not None:
                        value = int(value)
                    elif ptype == 'float' and value is not None:
                        value = float(value)
                    elif ptype == 'bool' and value is not None:
                        value = bool(value)
                except (TypeError, ValueError):
                    errors.append(f"Agent {i+1}: Parameter '{pname}' has invalid type")
                    continue
                if ptype in ('int', 'float') and (pmin is not None or pmax is not None) and value is None:
                    errors.append(f"Agent {i+1}: Parameter '{pname}' is required and must be a number")
                    continue
                try:
                    if pmin is not None and value is not None and value < pmin:
                        errors.append(f"Agent {i+1}: '{pname}' must be >= {pmin}")
                    if pmax is not None and value is not None and value > pmax:
                        errors.append(f"Agent {i+1}: '{pname}' must be <= {pmax}")
                except TypeError:
                    pass
                extra_kwargs[pname] = value

            if not errors:
                validated_agents.append((module, attr_name, float(pr_val), extra_kwargs))

        if errors:
            return html.Div([
                html.Div("Invalid configuration. Please fix the following:", className="error-message"),
                html.Ul([html.Li(err) for err in errors]),
            ]), True

        from figgie_server.db import get_connection
        try:
            conn = get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    '''
                    INSERT INTO experiments
                    (name, description, created_at) 
                    VALUES (%s, %s, %s) 
                    RETURNING experiment_id''',
                    (name, description, datetime.now(timezone.utc)),
                )
                exp_id = cursor.fetchone()[0]
                for i, (module, cls_name, pr, extra_kwargs) in enumerate(validated_agents):
                    cursor.execute(
                        '''
                        INSERT INTO experiment_agents
                        (experiment_id, player_index, module_name, attr_name, polling_rate, extra_kwargs) 
                        VALUES (%s, %s, %s, %s, %s, %s)''',
                        (exp_id, i, module, cls_name, pr, json.dumps(extra_kwargs)),
                    )
            conn.commit()
            return html.Div(f"Saved experiment {exp_id}: {name} with {num_players} configured agents", className="success-message message-auto-hide"), False
        except Exception as e:
            logger.exception("Error saving experiment")
            try:
                conn.rollback()  # type: ignore
            except Exception:
                pass
            return html.Div(f"Error saving experiment: {str(e)}", className="error-message message-auto-hide"), False

    @app.callback(
        [Output('run-output', 'children'), Output('run-message-timer', 'disabled')],
        Input('run-button', 'n_clicks'),
        State('experiment-dropdown', 'value'),
    )
    def run_experiment_callback(n_clicks, exp_id):  # noqa: F401
        if not n_clicks:
            return "", True
        if not exp_id:
            return html.Div("Select an experiment to run", className="error-message"), True
        from figgie_server.db import get_connection
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT module_name, attr_name, polling_rate, extra_kwargs FROM experiment_agents WHERE experiment_id = %s ORDER BY player_index;',
                    (exp_id,),
                )
                rows = cur.fetchall()
            if not rows:
                return html.Div("No agents found for this experiment", className="error-message message-auto-hide"), False
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

            server_url = FOUR_PLAYER_SERVER if len(agents) == 4 else FIVE_PLAYER_SERVER
            try:
                preflight_check(server_url)
            except ServerBusyError:
                return html.Div("Server is busy running a game. Please wait for it to complete.", className="error-message message-auto-hide"), False
            except ServerQueuePendingError:
                return html.Div("Server is preparing a game with queued players. Please try again shortly.", className="error-message message-auto-hide"), False
            except ServerStatusUnavailable as exc:
                return html.Div(f"Could not reach server at {server_url}: {exc}", className="error-message message-auto-hide"), False

            threading.Thread(target=run_game, args=(agents, server_url, exp_id), daemon=True).start()
            return html.Div(f"Running experiment {exp_id} with {len(agents)} agents...", className="success-message message-auto-hide"), False
        except Exception as e:
            logger.exception("Error preparing to run experiment")
            return html.Div(f"Error running experiment: {str(e)}", className="error-message message-auto-hide"), False
