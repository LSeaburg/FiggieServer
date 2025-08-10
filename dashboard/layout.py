from typing import Any, Dict, List
from dash import dcc, html, dash_table

from .config import REFRESH_INTERVAL, MIN_POLLING_RATE, MAX_PLAYERS, MESSAGE_HIDE_INTERVAL_MS, DEFAULT_POLLING_RATE
from .config.ids import (
    EXPERIMENT_DROPDOWN,
    EXPERIMENT_INFO,
    EXPERIMENTS_DATA,
    METRICS_DATA,
    RESULTS_TABLE,
    PROFIT_CHART,
    RUN_BUTTON,
    RUN_OUTPUT,
    SAVE_BUTTON,
    SAVE_OUTPUT,
    LAST_UPDATED,
    INTERVAL,
    RUN_MESSAGE_TIMER,
    SAVE_MESSAGE_TIMER,
    EXPERIMENT_STORE,
    AGENT_CONFIG_STORE,
    NUM_PLAYERS,
    EXPERIMENT_NAME,
    EXPERIMENT_DESCRIPTION,
    agent_block_id,
    agent_module_id,
    agent_polling_rate_id,
    agent_params_container_id,
)
from .config.agent_specs import AgentSpec


def build_app_layout(
    agent_specs: List[AgentSpec],
    fetch_experiments_initial: List[Dict[str, Any]],
) -> html.Div:
    traders_options = [{'label': s.get('label'), 'value': s.get('module')} for s in (agent_specs or [])]
    default_module = traders_options[0]['value'] if traders_options else None
    return html.Div([
        html.Div([
            html.H1([
                html.I(className="fas fa-chart-line", style={'marginRight': '10px'}),
                "Figgie Experiment Dashboard",
            ], className="dashboard-header"),
            html.Div([
                html.Div(id=LAST_UPDATED, className="last-updated"),
            ], className="header-controls"),
        ], className="header-container"),

        html.Div([
            html.Div([
                html.Div([
                    html.H3("Select Experiment", className="section-title"),
                    dcc.Dropdown(
                        id=EXPERIMENT_DROPDOWN,
                        options=[{'label': exp['label'], 'value': exp['value']} for exp in fetch_experiments_initial],
                        value=None,
                        placeholder='Select experiment to view or run',
                        clearable=False,
                        className="experiment-dropdown",
                    ),
                    html.Div(id=EXPERIMENT_INFO, className="experiment-info"),
                ], className="section"),

                html.Div([
                    html.H3("Experiment Results", className="section-title"),
                    html.Div([
                        html.Button("Run Experiment", id=RUN_BUTTON, n_clicks=0, className="btn btn-success"),
                        html.Span(f"Auto-refresh every {REFRESH_INTERVAL // 1000} seconds", className="auto-refresh-note"),
                    ], className="table-controls"),
                    html.Div(id=RUN_OUTPUT, className="output-message"),
                    dash_table.DataTable(
                        id=RESULTS_TABLE,
                        columns=[
                            {'name': 'Agent Name', 'id': 'agent_name'},
                            {'name': 'Config', 'id': 'extra_kwargs'},
                            {'name': 'Polling Rate', 'id': 'normalized_polling_rate'},
                            {'name': 'Games', 'id': 'num_games'},
                        ],
                        data=[],
                        page_size=10,
                        virtualization=True,
                        fixed_rows={'headers': True},
                        style_table={'overflowX': 'auto', 'borderRadius': '12px', 'overflow': 'hidden', 'boxShadow': '0 4px 15px rgba(0, 0, 0, 0.1)'},
                        style_cell={'textAlign': 'center'},
                        style_header={'backgroundColor': '#2c3e50', 'color': 'white', 'fontWeight': 'bold'},
                        style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#f8f9fa'}],
                    ),
                ], className="section"),

                html.Div([
                    html.H3("Performance Charts", className="section-title"),
                    dcc.Graph(id=PROFIT_CHART, className="chart"),
                ], className="section"),
            ], className="left-panel"),

            html.Div([
                html.Div([
                    html.H3("Create New Experiment", className="section-title"),
                    html.Div([
                        html.Label("Experiment Name"),
                        dcc.Input(id=EXPERIMENT_NAME, type='text', value='', placeholder='Enter experiment name', className="input-field"),
                        html.Label("Description"),
                        dcc.Textarea(id=EXPERIMENT_DESCRIPTION, value='', placeholder='Enter experiment description', className="textarea-field"),
                    ], className="form-group"),

                    html.Div([
                        html.Label("Number of Players"),
                        dcc.RadioItems(
                            id=NUM_PLAYERS,
                            options=[{'label': '4 Players', 'value': 4}, {'label': '5 Players', 'value': 5}],
                            value=4,
                            inline=True,
                            className="radio-group",
                        ),
                    ], className="form-group"),

                    html.Div([
                        html.H4("Agent Configuration", className="subsection-title"),
                        html.Div(
                            id='agent-configs',
                            className="agent-configs",
                            children=[
                                html.Div([
                                    html.H5(f"Agent {i}", className="agent-title"),
                                    html.Div([
                                        html.Div([
                                            html.Div([
                                                html.Label("Agent Type"),
                                                dcc.Dropdown(
                                                    id=agent_module_id(i),
                                                    options=traders_options,
                                                    value=default_module,
                                                    clearable=False,
                                                    className="agent-dropdown",
                                                ),
                                            ], className="agent-config-section"),
                                            html.Div([
                                                html.Label("Polling Rate"),
                                                dcc.Input(
                                                    id=agent_polling_rate_id(i),
                                                    type='number',
                                                    value=DEFAULT_POLLING_RATE,
                                                    step=0.01,
                                                    min=MIN_POLLING_RATE,
                                                    className="agent-input",
                                                ),
                                            ], className="agent-config-section"),
                                        ], className="agent-config-row"),
                                        html.Div([
                                            html.Div(id=agent_params_container_id(i), className="agent-params-container"),
                                        ], className="agent-config-section"),
                                    ], className="agent-config"),
                                ], id=agent_block_id(i), className="agent-block", style={'display': 'block' if i <= 4 else 'none'})
                                for i in range(1, MAX_PLAYERS + 1)
                            ],
                        ),
                    ], className="form-group"),

                    html.Div([
                        html.Button("Save Experiment", id=SAVE_BUTTON, n_clicks=0, className="btn btn-primary"),
                    ], className="button-group"),

                    html.Div(id=SAVE_OUTPUT, className="output-message"),
                ], className="section"),
            ], className="right-panel"),
        ], className="main-container"),

        html.Div(id=EXPERIMENTS_DATA, style={'display': 'none'}),
        html.Div(id=METRICS_DATA, style={'display': 'none'}),
        dcc.Interval(id=INTERVAL, interval=REFRESH_INTERVAL, n_intervals=0, disabled=False),
        dcc.Interval(id=RUN_MESSAGE_TIMER, interval=MESSAGE_HIDE_INTERVAL_MS, n_intervals=0, disabled=True),
        dcc.Interval(id=SAVE_MESSAGE_TIMER, interval=MESSAGE_HIDE_INTERVAL_MS, n_intervals=0, disabled=True),
        dcc.Store(id=EXPERIMENT_STORE),
        dcc.Store(id=AGENT_CONFIG_STORE, data={}),
    ])


