import ast
import os
import json
import threading
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone
import time
from pathlib import Path
import yaml

import dash
from dash import Dash, html, dcc, dash_table
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from agents.dispatcher import preflight_check, run_game, AgentConfig
from agents.dispatcher import ServerBusyError, ServerQueuePendingError, ServerStatusUnavailable
from figgie_server.db import get_connection

# Configuration
FOUR_PLAYER_SERVER = os.getenv("FIGGIE_SERVER_4P_URL", "http://localhost:5050")
FIVE_PLAYER_SERVER = os.getenv("FIGGIE_SERVER_5P_URL", "http://localhost:5051")

DEFAULT_POLLING_RATE = 0.25
MIN_POLLING_RATE = 0.01
REFRESH_INTERVAL = 5000  # 5 seconds

# Load agent specifications from YAML
def _load_agent_specs() -> Tuple[List[Dict[str, Any]], Dict[str, str], List[str]]:
    """Load agent specs from agents/traders.yaml.

    Returns:
        - specs: list of {label, module, attr, params}
        - module_to_attr: mapping module->attr
        - all_param_names: sorted list of all unique parameter names across agents
    """
    # Resolve YAML path relative to repo root
    current_dir = Path(__file__).resolve().parent
    yaml_path = (current_dir / ".." / "agents" / "traders.yaml").resolve()

    specs: List[Dict[str, Any]] = []
    module_to_attr: Dict[str, str] = {}
    all_param_names_set = set()

    try:
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f) or []
        for entry in data:
            name = entry.get("name")
            cls_path = entry.get("class", "")
            # Expect format module.attr
            if "." in cls_path:
                module, attr = cls_path.split(".", 1)
            else:
                module, attr = cls_path, name
            params = entry.get("params", []) or []
            for p in params:
                if isinstance(p, dict) and p.get("name"):
                    all_param_names_set.add(p["name"])
            specs.append({
                "label": name or attr,
                "module": module,
                "attr": attr,
                "params": params,
            })
            if module and attr:
                module_to_attr[module] = attr
    except Exception as exc:
        # Fallback to static definitions if YAML cannot be loaded
        specs = [
            {"label": "Fundamentalist", "module": "fundamentalist", "attr": "Fundamentalist", "params": []},
            {"label": "NoiseTrader", "module": "noise_trader", "attr": "NoiseTrader", "params": []},
            {"label": "BottomFeeder", "module": "bottom_feeder", "attr": "BottomFeeder", "params": []},
        ]
        module_to_attr = {s["module"]: s["attr"] for s in specs}

    all_param_names = sorted(all_param_names_set)
    return specs, module_to_attr, all_param_names


AGENT_SPECS, MODULE_TO_ATTR, ALL_PARAM_NAMES = _load_agent_specs()
# Derived list for dropdowns: (module, label)
TRADERS: List[Tuple[str, str]] = [(s["module"], s["label"]) for s in AGENT_SPECS]

def _get_params_for_module(module_name: str) -> List[Dict[str, Any]]:
    for spec in AGENT_SPECS:
        if spec["module"] == module_name:
            return spec.get("params", [])
    return []

def _format_timestamp(timestamp_str: str) -> str:
    """Format ISO timestamp string to human-readable format"""
    if not timestamp_str:
        return "Unknown"
    
    try:
        # Parse the ISO format timestamp
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        # Format to human-readable string
        return dt.strftime("%B %d, %Y at %I:%M %p")
    except (ValueError, AttributeError):
        return timestamp_str  # Return original if parsing fails

def _render_param_input(agent_index: int, param_spec: Dict[str, Any], value: Any) -> html.Div:
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
        # Use RadioItems for boolean
        return html.Div([
            html.Label(label, className="agent-param-label"),
            dcc.RadioItems(
                id={"type": "agent-param", "idx": agent_index, "name": name},
                options=[{"label": "True", "value": True}, {"label": "False", "value": False}],
                value=bool(value) if value is not None else False,
                inline=True,
                className="radio-group"
            )
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
            className="agent-input"
        )
    ], className="agent-param")

# SQL queries
_FETCH_METRICS_SQL = """
    SELECT DISTINCT ON (ea.experiment_id, ea.player_index)
      ea.experiment_id,
      ea.player_index,
      ea.attr_name,
      ea.extra_kwargs,
      ea.polling_rate as normalized_polling_rate,
      ea.attr_name || (ea.player_index + 1) AS agent_name,
      COALESCE(
        (SELECT COUNT(*) 
         FROM agents a2 
         JOIN results r2 ON r2.player_id = a2.player_id
         WHERE a2.experiment_id = ea.experiment_id 
           AND a2.attr_name = ea.attr_name
           AND a2.extra_kwargs::text = ea.extra_kwargs::text), 
        0
      ) as num_games
    FROM experiment_agents AS ea
    WHERE ea.experiment_id = %s
    ORDER BY ea.player_index;
"""

_FETCH_EXPERIMENT_STATS_SQL = """
    SELECT 
        e.experiment_id,
        e.name,
        e.description,
        e.created_at,
        COUNT(DISTINCT r.round_id) as total_games,
        COUNT(DISTINCT ea.player_index) as configured_agents
    FROM experiments e
    LEFT JOIN experiment_agents ea ON e.experiment_id = ea.experiment_id
    LEFT JOIN agents a ON ea.experiment_id = a.experiment_id
    LEFT JOIN results r ON a.player_id = r.player_id
    GROUP BY e.experiment_id, e.name, e.description, e.created_at
    ORDER BY e.created_at DESC;
"""

class DashboardDataManager:
    """Manages data fetching and caching for the dashboard"""
    
    def __init__(self):
        self._experiments_cache = None
        self._last_experiments_update = 0
        self._cache_ttl = 5  # 5 seconds cache
    
    def fetch_experiments(self, force_refresh=False) -> List[Dict[str, Any]]:
        """Fetch experiments with caching"""
        current_time = time.time()
        
        if (not force_refresh and 
            self._experiments_cache and 
            current_time - self._last_experiments_update < self._cache_ttl):
            return self._experiments_cache
        
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(_FETCH_EXPERIMENT_STATS_SQL)
                rows = cur.fetchall()
                
            experiments = []
            for row in rows:
                exp_id, name, description, created_at, total_games, configured_agents = row
                experiments.append({
                    'label': f"{exp_id}: {name} ({total_games} games, {configured_agents} agents)",
                    'value': exp_id,
                    'name': name,
                    'description': description,
                    'created_at': created_at.isoformat() if created_at else None,
                    'total_games': total_games or 0,
                    'configured_agents': configured_agents or 0
                })
            
            self._experiments_cache = experiments
            self._last_experiments_update = current_time
            return experiments
            
        except Exception as e:
            print(f"Error fetching experiments: {e}")
            return []
    
    def fetch_metrics(self, experiment_id: int) -> pd.DataFrame:
        """Fetch metrics for a specific experiment"""
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(_FETCH_METRICS_SQL, (experiment_id,))
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
                df = pd.DataFrame(rows, columns=cols)
            
            if not df.empty and 'extra_kwargs' in df.columns:
                df['extra_kwargs'] = df['extra_kwargs'].astype(str)
                df['buy_ratio'] = df['extra_kwargs'].apply(self._parse_extra_kwargs)
                df.sort_values(['attr_name', 'buy_ratio'], inplace=True, na_position='last')
                df.drop(columns=['buy_ratio'], inplace=True)
            
            return df
            
        except Exception as e:
            print(f"Error fetching metrics: {e}")
            return pd.DataFrame()
    
    def _parse_extra_kwargs(self, val: str) -> Optional[float]:
        """Parse stored kwargs to extract buy_ratio"""
        try:
            data = ast.literal_eval(val)
            return data.get('buy_ratio')
        except (ValueError, SyntaxError):
            return None
    
    def fetch_individual_profits(self, experiment_id: int) -> pd.DataFrame:
        """Fetch individual game profits for box plot"""
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        ea.attr_name || (ea.player_index + 1) AS agent_name,
                        ea.attr_name,
                        ea.player_index,
                        r.final_balance - r.initial_balance AS profit
                    FROM experiment_agents AS ea
                    JOIN agents AS a ON a.experiment_id = ea.experiment_id 
                        AND a.attr_name = ea.attr_name
                        AND a.extra_kwargs::text = ea.extra_kwargs::text
                    JOIN results AS r ON r.player_id = a.player_id
                    WHERE ea.experiment_id = %s
                    ORDER BY ea.player_index, r.round_id;
                """, (experiment_id,))
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
                df = pd.DataFrame(rows, columns=cols)
            
            return df
            
        except Exception as e:
            print(f"Error fetching individual profits: {e}")
            return pd.DataFrame()

# Initialize data manager
data_manager = DashboardDataManager()

# Initialize Dash app
app = Dash(__name__, 
           external_stylesheets=[
               'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css'
           ],
           suppress_callback_exceptions=True)

# App layout
app.layout = html.Div([
    # Header
    html.Div([
        html.H1([
            html.I(className="fas fa-chart-line", style={'marginRight': '10px'}),
            "Figgie Experiment Dashboard"
        ], className="dashboard-header"),
        html.Div([
            html.Button([
                html.I(className="fas fa-sync-alt"),
                " Refresh"
            ], id="refresh-button", className="refresh-btn"),
            html.Div(id="last-updated", className="last-updated")
        ], className="header-controls")
    ], className="header-container"),
    
    # Main content
    html.Div([
        # Left panel - Experiment selection and configuration
        html.Div([
            # Experiment selection
            html.Div([
                html.H3("Select Experiment", className="section-title"),
    dcc.Dropdown(
        id='experiment-dropdown',
                    options=[
                        {'label': exp['label'], 'value': exp['value']} 
                        for exp in data_manager.fetch_experiments()
                    ],
        value=None,
        placeholder='Select experiment to view or run',
                    clearable=False,
                    className="experiment-dropdown"
                ),
                html.Div(id="experiment-info", className="experiment-info")
            ], className="section"),
            
            # Experiment Results moved here
            html.Div([
                html.H3("Experiment Results", className="section-title"),
                html.Div([
                    html.Button(
                        "Run Experiment", 
                        id='run-button', 
                        n_clicks=0,
                        className="btn btn-success"
                    ),
                    html.Span(f"Auto-refresh every {REFRESH_INTERVAL // 1000} seconds", className="auto-refresh-note")
                ], className="table-controls"),
                html.Div(id='run-output', className="output-message"),
    dash_table.DataTable(
        id='results-table',
        columns=[
                        {'name': 'Agent Name', 'id': 'agent_name'},
                        {'name': 'Config', 'id': 'extra_kwargs'},
                        {'name': 'Polling Rate', 'id': 'normalized_polling_rate'},
                        {'name': 'Games', 'id': 'num_games'},
        ],
        data=[],
        page_size=10,
                    style_table={'overflowX': 'auto', 'borderRadius': '12px', 'overflow': 'hidden', 'boxShadow': '0 4px 15px rgba(0, 0, 0, 0.1)'},
                    style_cell={'textAlign': 'center'},
                    style_header={
                        'backgroundColor': '#2c3e50',
                        'color': 'white',
                        'fontWeight': 'bold'
                    },
                    style_data_conditional=[
                        {
                            'if': {'row_index': 'odd'},
                            'backgroundColor': '#f8f9fa'
                        }
                    ]
                ),
            ], className="section"),
            
            # Performance Charts moved here
            html.Div([
                html.H3("Performance Charts", className="section-title"),
                dcc.Graph(id='profit-chart', className="chart"),
            ], className="section"),
        ], className="left-panel"),
        
        # Right panel - Create New Experiment moved here
        html.Div([
            # New experiment configuration
            html.Div([
                html.H3("Create New Experiment", className="section-title"),
                html.Div([
                    html.Label("Experiment Name"),
                    dcc.Input(
                        id='experiment-name', 
                        type='text', 
                        value='', 
                        placeholder='Enter experiment name',
                        className="input-field"
                    ),
                    html.Label("Description"),
                    dcc.Textarea(
                        id='experiment-description', 
                        value='', 
                        placeholder='Enter experiment description',
                        className="textarea-field"
                    ),
                ], className="form-group"),
                
                html.Div([
                    html.Label("Number of Players"),
                    dcc.RadioItems(
                        id='num-players',
                        options=[
                            {'label': '4 Players', 'value': 4},
                            {'label': '5 Players', 'value': 5}
                        ],
                        value=4,
                        inline=True,
                        className="radio-group"
                    ),
                ], className="form-group"),
                
                # Agent configuration
                html.Div([
                    html.H4("Agent Configuration", className="subsection-title"),
                    html.Div(id='agent-configs', className="agent-configs", children=[
                        # Initialize with 5 agent blocks (all hidden initially)
                        html.Div([
                            html.H5(f"Agent {i}", className="agent-title"),
                            html.Div([
                                # Fixed configuration section
                                html.Div([
                                    html.Div([
                                        html.Div([
                                            html.Label("Agent Type"),
                                            dcc.Dropdown(
                                                id=f'agent{i}_module',
                                                options=[{'label': label, 'value': module} for module, label in TRADERS],
                                                value=TRADERS[0][0],
                                                clearable=False,
                                                className="agent-dropdown"
                                            ),
                                        ], className="agent-config-section"),
                                        html.Div([
                                            html.Label("Polling Rate"),
                                            dcc.Input(
                                                id=f'agent{i}_polling_rate', 
                                                type='number', 
                                                value=0.25, 
                                                step=0.01,
                                                min=MIN_POLLING_RATE,
                                                className="agent-input"
                                            ),
                                        ], className="agent-config-section"),
                                    ], className="agent-config-row"),
                                ], className="agent-config-section"),
                                # Dynamic parameters section
                                html.Div([
                                    html.Div(id={"type": "agent-params-container", "idx": i}, className="agent-params-container"),
                                ], className="agent-config-section"),
                            ], className="agent-config")
                        ], id=f'agent-block-{i}', className="agent-block", style={'display': 'block' if i <= 4 else 'none'})
                        for i in range(1, 6)
                    ])
                ], className="form-group"),
                
                html.Div([
                    html.Button(
                        "Save Experiment", 
                        id='save-button', 
                        n_clicks=0,
                        className="btn btn-primary"
                    ),
                ], className="button-group"),
                
                html.Div(id='save-output', className="output-message"),
            ], className="section"),
        ], className="right-panel"),
    ], className="main-container"),
    
    # Hidden divs for storing data
    html.Div(id='experiments-data', style={'display': 'none'}),
    html.Div(id='metrics-data', style={'display': 'none'}),
    
    # Interval component for auto-refresh
    dcc.Interval(
        id='interval-component',
        interval=REFRESH_INTERVAL,
        n_intervals=0,
        disabled=False
    ),
    
    # Hidden interval components for auto-clearing messages
    dcc.Interval(
        id='run-message-timer',
        interval=3000,  # 3 seconds
        n_intervals=0,
        disabled=True
    ),
    
    dcc.Interval(
        id='save-message-timer',
        interval=3000,  # 3 seconds
        n_intervals=0,
        disabled=True
    ),
    
    # Store for experiment data
    dcc.Store(id='experiment-store'),
    
    # Store for agent configuration data
                    dcc.Store(id='agent-config-store', data={}),
    

])

# Callbacks

# Auto-clear message callbacks
@app.callback(
    Output('run-output', 'children', allow_duplicate=True),
    Output('run-message-timer', 'disabled', allow_duplicate=True),
    Input('run-message-timer', 'n_intervals'),
    prevent_initial_call=True
)
def clear_run_message(n_intervals):
    """Clear run experiment message after timer expires"""
    return "", True

@app.callback(
    Output('save-output', 'children', allow_duplicate=True),
    Output('save-message-timer', 'disabled', allow_duplicate=True),
    Input('save-message-timer', 'n_intervals'),
    prevent_initial_call=True
)
def clear_save_message(n_intervals):
    """Clear save experiment message after timer expires"""
    return "", True

@app.callback(
    [Output('experiment-dropdown', 'options'),
     Output('experiments-data', 'children'),
     Output('last-updated', 'children')],
    [Input('interval-component', 'n_intervals'),
     Input('refresh-button', 'n_clicks')],
    prevent_initial_call=False
)
def update_experiments_list(n_intervals, n_clicks):
    """Update experiments list with auto-refresh"""
    experiments = data_manager.fetch_experiments(force_refresh=True)
    
    # Create dropdown options with only label and value
    dropdown_options = [
        {'label': exp['label'], 'value': exp['value']} 
        for exp in experiments
    ]
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    return dropdown_options, json.dumps(experiments), f"Last updated: {timestamp}"

@app.callback(
    [Output('results-table', 'data'),
     Output('metrics-data', 'children'),
     Output('profit-chart', 'figure')],
    [Input('experiment-dropdown', 'value'),
     Input('interval-component', 'n_intervals')]
)
def update_metrics_and_charts(selected_experiment, n_intervals):
    """Update metrics table and charts when experiment is selected"""
    if not selected_experiment:
        empty_fig = go.Figure().add_annotation(
            text="Select an experiment to view results",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return [], "", empty_fig
    
    df = data_manager.fetch_metrics(selected_experiment)
    
    if df.empty:
        empty_fig = go.Figure().add_annotation(
            text="No data available for this experiment",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return [], "", empty_fig
    
    # Create profit box plot
    profit_df = data_manager.fetch_individual_profits(selected_experiment)
    
    if profit_df.empty:
        profit_fig = go.Figure().add_annotation(
            text="No individual game data available for box plot",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
    else:
        profit_fig = px.box(
            profit_df, 
            x='agent_name', 
            y='profit',
            title='Profit Distribution by Agent',
            labels={'profit': 'Profit per Game', 'agent_name': 'Agent'},
            color='agent_name',
            points='outliers'  # Show outlier points
        )
        profit_fig.update_layout(
            height=400,
            showlegend=False,  # Hide legend since x-axis already shows agent names
            xaxis_title="Agent",
            yaxis_title="Profit per Game"
        )
    
    # Removed games chart
    
    # Convert Decimal objects to float for JSON serialization
    records = df.to_dict('records')
    for record in records:
        for key, value in record.items():
            if hasattr(value, 'as_tuple'):  # Check if it's a Decimal
                record[key] = float(value)
            elif pd.isna(value):  # Handle NaN values
                record[key] = None
    
    return records, json.dumps(records), profit_fig

@app.callback(
    Output('experiment-info', 'children'),
    [Input('experiment-dropdown', 'value'),
     Input('experiments-data', 'children')]
)
def update_experiment_info(selected_experiment, experiments_json):
    """Display information about the selected experiment"""
    if not selected_experiment or not experiments_json:
        return ""
    
    try:
        experiments = json.loads(experiments_json)
        experiment = next((exp for exp in experiments if exp['value'] == selected_experiment), None)
        
        if not experiment:
            return ""
        
        return html.Div([
            html.H4(experiment['name']),
            html.P(experiment['description'] or "No description"),
            html.Div([
                html.Span(f"Games: {experiment['total_games']}", className="stat"),
                html.Span(f"Agents: {experiment['configured_agents']}", className="stat"),
            ], className="experiment-stats"),
            html.Small(f"Created: {_format_timestamp(experiment['created_at'])}")
        ])
    except:
        return ""

@app.callback(
    [Output(f'agent-block-{i}', 'style') for i in range(1, 6)],
    Input('num-players', 'value')
)
def update_agent_configs(num_players):
    """Show/hide agent configuration blocks based on number of players"""
    styles = []
    
    for i in range(1, 6):
        if i <= num_players:
            styles.append({'display': 'block'})
        else:
            styles.append({'display': 'none'})
    
    return styles


# Individual callbacks for each agent's parameter container to prevent cross-contamination
def create_agent_params_callback(agent_idx):
    @app.callback(
        Output({"type": "agent-params-container", "idx": agent_idx}, 'children'),
        [Input(f'agent{agent_idx}_module', 'value'),
         Input('num-players', 'value')],
        [State({'type': 'agent-param', 'idx': agent_idx, 'name': dash.dependencies.ALL}, 'value'),
         State({'type': 'agent-param', 'idx': agent_idx, 'name': dash.dependencies.ALL}, 'id')],
        prevent_initial_call=False
    )
    def render_single_agent_params(module_value, num_players, existing_values, existing_ids):
        # Only render if this agent is within the selected number of players
        if agent_idx > (num_players or 0):
            return []
        
        params = _get_params_for_module(module_value) if module_value else []
        
        # Build a map of existing parameter name -> value
        existing_param_values = {}
        if existing_values and existing_ids:
            for val, id_dict in zip(existing_values, existing_ids):
                if isinstance(id_dict, dict) and 'name' in id_dict:
                    param_name = id_dict['name']
                    existing_param_values[param_name] = val
        
        rendered = []
        for p in params:
            param_name = p.get('name')
            # Use existing value if available, otherwise use default
            if param_name in existing_param_values:
                value = existing_param_values[param_name]
            else:
                value = p.get('default')
            rendered.append(_render_param_input(agent_idx, p, value))
        return rendered
    
    return render_single_agent_params

# Create the callbacks for each agent
for i in range(1, 6):
    create_agent_params_callback(i)

# Initialize agent config store when num-players changes
@app.callback(
    Output('agent-config-store', 'data'),
    Input('num-players', 'value'),
    State('agent-config-store', 'data')
)
def initialize_agent_config_store(num_players, current_data):
    """Initialize agent configuration store when num-players changes"""
    # If we have current data, preserve it, otherwise use defaults
    if current_data and len(current_data) >= num_players:
        return current_data
    
    # Initialize with defaults
    agent_data = []
    for i in range(5):
        if current_data and i < len(current_data):
            # Preserve existing data
            agent_data.append(current_data[i])
        else:
            # Use defaults for new agents
            agent_data.append({
                'module': TRADERS[0][0],
                'polling_rate': 0.25,
                'extra_kwargs': ''
            })
    
    return agent_data

@app.callback(
    [Output('save-output', 'children'),
     Output('save-message-timer', 'disabled')],
    Input('save-button', 'n_clicks'),
    State('experiment-name', 'value'),
    State('experiment-description', 'value'),
    State('num-players', 'value'),
    *[State(f'agent{i}_module', 'value') for i in range(1, 6)],
    *[State(f'agent{i}_polling_rate', 'value') for i in range(1, 6)],
    State({'type': 'agent-param', 'idx': dash.dependencies.ALL, 'name': dash.dependencies.ALL}, 'value'),
    State({'type': 'agent-param', 'idx': dash.dependencies.ALL, 'name': dash.dependencies.ALL}, 'id')
)
def save_experiment(n_clicks, name, description, num_players, *args):
    """Save new experiment to database with form agent configuration"""
    if not n_clicks:
        return "", True
    
    if not name:
        return html.Div("Experiment name is required", className="error-message"), True
    
    # Unpack the args: modules, polling_rates, extra_kwargs
    modules = args[:5]
    polling_rates = args[5:10]
    # Last two args are flat lists for all dynamic controls
    dyn_values = args[10] if len(args) > 10 else []
    dyn_ids = args[11] if len(args) > 11 else []
    
    # Server-side validation before any DB writes
    mapping = dict(MODULE_TO_ATTR)
    errors: List[str] = []

    # Build a lookup from dynamic control id -> value once
    id_to_value: Dict[str, Any] = {}
    try:
        for cid, val in zip(dyn_ids or [], dyn_values or []):
            if isinstance(cid, dict):
                key = f"{cid.get('idx')}::{cid.get('name')}"
                id_to_value[key] = val
    except Exception:
        id_to_value = {}

    # Collect validated agents to insert
    validated_agents: List[Tuple[str, str, float, Dict[str, Any]]] = []

    for i in range(num_players):
        module = modules[i] if modules[i] else (TRADERS[0][0] if TRADERS else None)
        if not module:
            errors.append(f"Agent {i+1}: Missing agent module")
            continue

        attr_name = mapping.get(module)
        if not attr_name:
            errors.append(f"Agent {i+1}: Unknown module '{module}'")
            continue

        # Validate polling rate
        raw_pr = polling_rates[i] if i < len(polling_rates) else None
        pr_val: Optional[float]
        try:
            pr_val = float(raw_pr) if raw_pr is not None else None
        except (TypeError, ValueError):
            pr_val = None
        if pr_val is None or pr_val <= 0:
            errors.append(f"Agent {i+1}: Polling rate is required and must be > 0")

        # Build and validate extra kwargs using YAML spec
        extra_kwargs: Dict[str, Any] = {}
        current_params = _get_params_for_module(module)
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

            # Type coercion
            try:
                if ptype == 'int' and value is not None:
                    value = int(value)
                elif ptype == 'float' and value is not None:
                    value = float(value)
                elif ptype == 'bool' and value is not None:
                    # RadioItems already yields booleans; leave as-is
                    value = bool(value)
            except (TypeError, ValueError):
                errors.append(f"Agent {i+1}: Parameter '{pname}' has invalid type")
                continue

            # If a numeric param declares bounds, a None value is invalid
            if ptype in ('int', 'float') and (pmin is not None or pmax is not None) and value is None:
                errors.append(f"Agent {i+1}: Parameter '{pname}' is required and must be a number")
                continue

            # Range validation
            try:
                if pmin is not None and value is not None and value < pmin:
                    errors.append(f"Agent {i+1}: '{pname}' must be >= {pmin}")
                if pmax is not None and value is not None and value > pmax:
                    errors.append(f"Agent {i+1}: '{pname}' must be <= {pmax}")
            except TypeError:
                # Skip range check if incomparable types
                pass

            extra_kwargs[pname] = value

        if not errors:
            # pr_val is validated to be a float > 0 above
            validated_agents.append((module, attr_name, float(pr_val), extra_kwargs))

    if errors:
        # Do not write anything; show all validation errors
        return html.Div([
            html.Div("Invalid configuration. Please fix the following:", className="error-message"),
            html.Ul([html.Li(err) for err in errors])
        ]), True

    # Proceed with DB writes in a transaction
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO experiments
                (name, description, created_at) 
                VALUES (%s, %s, %s) 
                RETURNING experiment_id''',
                (name, description, datetime.now(timezone.utc))
            )
            exp_id = cursor.fetchone()[0]

            for i, (module, cls_name, pr, extra_kwargs) in enumerate(validated_agents):
                cursor.execute('''
                    INSERT INTO experiment_agents
                    (experiment_id, player_index, module_name, attr_name, polling_rate, extra_kwargs) 
                    VALUES (%s, %s, %s, %s, %s, %s)''',
                    (exp_id, i, module, cls_name, pr, json.dumps(extra_kwargs))
                )
        conn.commit()

        return html.Div(f"Saved experiment {exp_id}: {name} with {num_players} configured agents", className="success-message message-auto-hide"), False
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return html.Div(f"Error saving experiment: {str(e)}", className="error-message message-auto-hide"), False

@app.callback(
    [Output('run-output', 'children'),
     Output('run-message-timer', 'disabled')],
    Input('run-button', 'n_clicks'),
    State('experiment-dropdown', 'value')
)
def run_experiment_callback(n_clicks, exp_id):
    """Run selected experiment"""
    if not n_clicks:
        return "", True
    
    if not exp_id:
        return html.Div("Select an experiment to run", className="error-message"), True
    
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                'SELECT module_name, attr_name, polling_rate, extra_kwargs FROM experiment_agents WHERE experiment_id = %s ORDER BY player_index;',
                (exp_id,)
            )
            rows = cur.fetchall()
        
        if not rows:
            return html.Div("No agents found for this experiment", className="error-message message-auto-hide"), False
        
        agents = []
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
            # polling_rate is modeled explicitly in AgentConfig now
            agents.append(AgentConfig(module_name, attr_name, float(pr), kwargs))
        
        # Determine server URL based on number of agents
        server_url = FOUR_PLAYER_SERVER if len(agents) == 4 else FIVE_PLAYER_SERVER
        
        # Pre-flight server status check to gracefully handle busy server
        try:
            preflight_check(server_url)
        except ServerBusyError:
            return html.Div("Server is busy running a game. Please wait for it to complete.", className="error-message message-auto-hide"), False
        except ServerQueuePendingError:
            return html.Div("Server is preparing a game with queued players. Please try again shortly.", className="error-message message-auto-hide"), False
        except ServerStatusUnavailable as exc:
            return html.Div(f"Could not reach server at {server_url}: {exc}", className="error-message message-auto-hide"), False

        # Run game in background thread
        threading.Thread(
            target=run_game,
            args=(agents, server_url, exp_id),
            daemon=True,
        ).start()
        
        return html.Div(f"Running experiment {exp_id} with {len(agents)} agents...", className="success-message message-auto-hide"), False
        
    except Exception as e:
        return html.Div(f"Error running experiment: {str(e)}", className="error-message message-auto-hide"), False


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8050, debug=True)
