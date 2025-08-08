import ast
import os
import json
import threading
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import time

import dash
from dash import Dash, html, dcc, dash_table
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from agents.dispatcher import run_game, AgentConfig
from figgie_server.db import get_connection

# Configuration
FOUR_PLAYER_SERVER = os.getenv("FIGGIE_SERVER_4P_URL", "http://localhost:5050")
FIVE_PLAYER_SERVER = os.getenv("FIGGIE_SERVER_5P_URL", "http://localhost:5051")

# Available agents for configuration
TRADERS = [
    ("fundamentalist", "Fundamentalist"),
    ("noise_trader", "NoiseTrader"),
    ("bottom_feeder", "BottomFeeder"),
]

DEFAULT_POLLING_RATE = 0.25
REFRESH_INTERVAL = 2000  # 2 seconds

# SQL queries
_FETCH_METRICS_SQL = """
    SELECT
      a.attr_name,
      a.extra_kwargs,
      AVG(r.final_balance - r.initial_balance) AS avg_net_profit,
      MIN(r.final_balance - r.initial_balance) AS min_net_profit,
      MAX(r.final_balance - r.initial_balance) AS max_net_profit,
      COUNT(*) as num_games,
      ROUND((240.0 * a.polling_rate / ro.round_duration)::numeric, 2) AS normalized_polling_rate
    FROM results AS r
    JOIN agents AS a ON r.player_id = a.player_id
    JOIN rounds AS ro ON r.round_id = ro.round_id
    WHERE a.experiment_id = %s
    GROUP BY a.attr_name, a.extra_kwargs, normalized_polling_rate
    ORDER BY avg_net_profit DESC;
"""

_FETCH_EXPERIMENT_STATS_SQL = """
    SELECT 
        e.experiment_id,
        e.name,
        e.description,
        e.created_at,
        COUNT(DISTINCT r.round_id) as total_games,
        COUNT(DISTINCT a.player_id) as total_agents,
        AVG(r.final_balance - r.initial_balance) as avg_profit
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
                exp_id, name, description, created_at, total_games, total_agents, avg_profit = row
                experiments.append({
                    'label': f"{exp_id}: {name} ({total_games} games, {total_agents} agents)",
                    'value': exp_id,
                    'name': name,
                    'description': description,
                    'created_at': created_at.isoformat() if created_at else None,
                    'total_games': total_games or 0,
                    'total_agents': total_agents or 0,
                    'avg_profit': float(avg_profit) if avg_profit else 0.0
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
                                html.Label("Agent Type"),
                                dcc.Dropdown(
                                    id=f'agent{i}_module',
                                    options=[{'label': mod, 'value': mod} for mod, _ in TRADERS],
                                    value=TRADERS[0][0],
                                    clearable=False,
                                    className="agent-dropdown"
                                ),
                                html.Label("Polling Rate"),
                                dcc.Input(
                                    id=f'agent{i}_polling_rate', 
                                    type='number', 
                                    value=0.25, 
                                    step=0.01,
                                    className="agent-input"
                                ),
                                html.Label("Extra Configuration (JSON)"),
                                dcc.Input(
                                    id=f'agent{i}_extra_kwargs',
                                    type='text',
                                    value='',
                                    placeholder='{"buy_ratio": 1.2}',
                                    className="agent-input"
                                ),
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
                    html.Button(
                        "Run Experiment", 
                        id='run-button', 
                        n_clicks=0,
                        className="btn btn-success"
                    ),
                ], className="button-group"),
                
                html.Div(id='save-output', className="output-message"),
                html.Div(id='run-output', className="output-message"),
            ], className="section"),
        ], className="left-panel"),
        
        # Right panel - Results and visualizations
        html.Div([
            # Metrics table
            html.Div([
                html.H3("Experiment Results", className="section-title"),
                html.Div([
                    html.Button([
                        html.I(className="fas fa-download"),
                        " Export CSV"
                    ], id="export-button", className="btn btn-secondary"),
                    html.Span("Auto-refresh every 2 seconds", className="auto-refresh-note")
                ], className="table-controls"),
                html.Div(id="export-output", className="output-message"),
    dash_table.DataTable(
        id='results-table',
        columns=[
                        {'name': 'Agent Type', 'id': 'attr_name'},
                        {'name': 'Config', 'id': 'extra_kwargs'},
                        {'name': 'Polling Rate', 'id': 'normalized_polling_rate'},
                        {'name': 'Games', 'id': 'num_games'},
                        {'name': 'Avg Profit', 'id': 'avg_net_profit', 'type': 'numeric', 'format': {'specifier': '.0f'}},
                        {'name': 'Min Profit', 'id': 'min_net_profit', 'type': 'numeric', 'format': {'specifier': '.0f'}},
                        {'name': 'Max Profit', 'id': 'max_net_profit', 'type': 'numeric', 'format': {'specifier': '.0f'}},
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
            
            # Charts
    html.Div([
                html.H3("Performance Charts", className="section-title"),
                dcc.Graph(id='profit-chart', className="chart"),
                dcc.Graph(id='games-chart', className="chart")
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
    
    # Store for experiment data
    dcc.Store(id='experiment-store'),
    
    # Store for agent configuration data
    dcc.Store(id='agent-config-store', data={}),
    

])

# Callbacks
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
     Output('profit-chart', 'figure'),
     Output('games-chart', 'figure')],
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
        return [], "", empty_fig, empty_fig
    
    df = data_manager.fetch_metrics(selected_experiment)
    
    if df.empty:
        empty_fig = go.Figure().add_annotation(
            text="No data available for this experiment",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return [], "", empty_fig, empty_fig
    
    # Create profit chart
    profit_fig = px.bar(
        df, 
        x='attr_name', 
        y='avg_net_profit',
        color='normalized_polling_rate',
        title='Average Net Profit by Agent Type',
        labels={'avg_net_profit': 'Average Net Profit', 'attr_name': 'Agent Type'},
        color_continuous_scale='RdYlGn'
    )
    profit_fig.update_layout(height=400)
    
    # Create games chart
    games_fig = px.bar(
        df,
        x='attr_name',
        y='num_games',
        title='Number of Games by Agent Type',
        labels={'num_games': 'Number of Games', 'attr_name': 'Agent Type'},
        color='avg_net_profit',
        color_continuous_scale='RdYlGn'
    )
    games_fig.update_layout(height=400)
    
    # Convert Decimal objects to float for JSON serialization
    records = df.to_dict('records')
    for record in records:
        for key, value in record.items():
            if hasattr(value, 'as_tuple'):  # Check if it's a Decimal
                record[key] = float(value)
            elif pd.isna(value):  # Handle NaN values
                record[key] = None
    
    return records, json.dumps(records), profit_fig, games_fig

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
                html.Span(f"Agents: {experiment['total_agents']}", className="stat"),
                html.Span(f"Avg Profit: {experiment['avg_profit']:.0f}", className="stat"),
            ], className="experiment-stats"),
            html.Small(f"Created: {experiment['created_at']}")
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
    Output('save-output', 'children'),
    Input('save-button', 'n_clicks'),
    State('experiment-name', 'value'),
    State('experiment-description', 'value'),
    State('num-players', 'value'),
    *[State(f'agent{i}_module', 'value') for i in range(1, 6)],
    *[State(f'agent{i}_polling_rate', 'value') for i in range(1, 6)],
    *[State(f'agent{i}_extra_kwargs', 'value') for i in range(1, 6)]
)
def save_experiment(n_clicks, name, description, num_players, *args):
    """Save new experiment to database with form agent configuration"""
    if not n_clicks:
        return ""
    
    if not name:
        return html.Div("Experiment name is required", className="error-message")
    
    # Unpack the args: modules, polling_rates, extra_kwargs
    modules = args[:5]
    polling_rates = args[5:10]
    extra_kwargs_list = args[10:15]
    
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
            
            # Create agents based on form configuration
            mapping = {mod: cls for mod, cls in TRADERS}
            
            for i in range(num_players):
                module = modules[i] if modules[i] else TRADERS[0][0]
                cls_name = mapping.get(module, '')
                pr = polling_rates[i] if polling_rates[i] else DEFAULT_POLLING_RATE
                
                # Parse extra kwargs
                extra_kwargs = {}
                extra_kwargs_str = extra_kwargs_list[i] if extra_kwargs_list[i] else ''
                if extra_kwargs_str and extra_kwargs_str.strip():
                    try:
                        extra_kwargs = json.loads(extra_kwargs_str)
                    except (ValueError, TypeError) as e:
                        return html.Div(f"Invalid JSON in agent {i+1} extra configuration: {str(e)}", className="error-message")
                
                # Add polling rate to extra kwargs
                extra_kwargs['polling_rate'] = pr
                
                cursor.execute('''
                    INSERT INTO experiment_agents
                    (experiment_id, player_index, module_name, attr_name, polling_rate, extra_kwargs) 
                    VALUES (%s, %s, %s, %s, %s, %s)''',
                    (exp_id, i, module, cls_name, pr, json.dumps(extra_kwargs))
                )
            conn.commit()
        
        return html.Div(f"Saved experiment {exp_id}: {name} with {num_players} configured agents", className="success-message")
        
    except Exception as e:
        return html.Div(f"Error saving experiment: {str(e)}", className="error-message")

@app.callback(
    Output('run-output', 'children'),
    Input('run-button', 'n_clicks'),
    State('experiment-dropdown', 'value')
)
def run_experiment_callback(n_clicks, exp_id):
    """Run selected experiment"""
    if not n_clicks:
        return ""
    
    if not exp_id:
        return html.Div("Select an experiment to run", className="error-message")
    
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                'SELECT module_name, attr_name, polling_rate, extra_kwargs FROM experiment_agents WHERE experiment_id = %s ORDER BY player_index;',
                (exp_id,)
            )
            rows = cur.fetchall()
        
        if not rows:
            return html.Div("❌ No agents found for this experiment", className="error-message")
        
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
        
        # Run game in background thread
        threading.Thread(
            target=run_game,
            args=(agents, server_url, exp_id),
            daemon=True,
        ).start()
        
        return html.Div(f"Running experiment {exp_id} with {len(agents)} agents...", className="success-message")
        
    except Exception as e:
        return html.Div(f"Error running experiment: {str(e)}", className="error-message")

@app.callback(
    Output('export-output', 'children'),
    Input('export-button', 'n_clicks'),
    State('metrics-data', 'children')
)
def export_csv(n_clicks, metrics_json):
    """Export metrics data to CSV"""
    if not n_clicks or not metrics_json:
        return ""
    
    try:
        data = json.loads(metrics_json)
        df = pd.DataFrame(data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"figgie_metrics_{timestamp}.csv"
        df.to_csv(filename, index=False)
        return html.Div(f"Exported data to {filename}", className="success-message")
    except Exception as e:
        return html.Div(f"Export failed: {str(e)}", className="error-message")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8050, debug=True)
