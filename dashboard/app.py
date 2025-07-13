import ast
from typing import List, Optional

import dash
from dash import Dash, html, dcc
from dash.dependencies import Input, Output
from dash import dash_table
import pandas as pd

from figgie_server.db import get_connection

_FETCH_EXPERIMENT_IDS_SQL = """
    SELECT DISTINCT experiment_id
      FROM agents
    ORDER BY experiment_id;
"""

_FETCH_METRICS_SQL = """
    SELECT
      a.attr_name,
      a.extra_kwargs,
      AVG(r.final_balance - r.initial_balance) AS avg_net_profit,
      MIN(r.final_balance - r.initial_balance) AS min_net_profit,
      MAX(r.final_balance - r.initial_balance) AS max_net_profit,
      ROUND((240.0 * a.polling_rate / ro.round_duration)::numeric, 2) AS normalized_polling_rate
    FROM results AS r
    JOIN agents AS a
      ON r.player_id = a.player_id
    JOIN rounds AS ro
      ON r.round_id = ro.round_id
    WHERE a.experiment_id = %s
    GROUP BY a.attr_name, a.extra_kwargs, normalized_polling_rate;
"""

def fetch_experiment_ids() -> List[int]:
    """Return all experiment IDs, ordered ascending."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(_FETCH_EXPERIMENT_IDS_SQL)
        return [row[0] for row in cur.fetchall()]

def parse_extra_kwargs(val: str) -> Optional[float]:
    """Extract buy_ratio from the stored kwargs, if present."""
    try:
        data = ast.literal_eval(val)
        return data.get('buy_ratio')
    except (ValueError, SyntaxError):
        return None

def fetch_metrics(experiment_id: int) -> pd.DataFrame:
    """Fetch and massage metrics DataFrame for a given experiment."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(_FETCH_METRICS_SQL, (experiment_id,))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        df = pd.DataFrame(rows, columns=cols)

    if 'extra_kwargs' in df:
        df['extra_kwargs'] = df['extra_kwargs'].astype(str)
        df['buy_ratio'] = df['extra_kwargs'].apply(parse_extra_kwargs)
        df.sort_values(['attr_name', 'buy_ratio'], inplace=True, na_position='last')
        df.drop(columns=['buy_ratio'], inplace=True)

    return df

# Initialize Dash app
app = dash.Dash(__name__)

# Fetch dropdown options
experiment_ids = fetch_experiment_ids()

# Layout definition
app.layout = html.Div([
    html.H1("Experiment Metrics Dashboard"),
    dcc.Dropdown(
        id='experiment-dropdown',
        options=[{'label': str(e), 'value': e} for e in experiment_ids],
        value=experiment_ids[0] if experiment_ids else None,
        clearable=False
    ),
    dash_table.DataTable(
        id='results-table',
        columns=[
            {'name': 'Attribute Name', 'id': 'attr_name'},
            {'name': 'Extra Args', 'id': 'extra_kwargs'},
            {'name': 'Normalized Polling Rate', 'id': 'normalized_polling_rate'},
            {'name': 'Avg Net Profit', 'id': 'avg_net_profit'},
            {'name': 'Min Net Profit', 'id': 'min_net_profit'},
            {'name': 'Max Net Profit', 'id': 'max_net_profit'},
        ],
        data=[],
        page_size=10,
        style_table={'overflowX': 'auto'},
    )
])

# Callback to update table based on selected experiment
@app.callback(
    Output('results-table', 'data'),
    Input('experiment-dropdown', 'value')
)
def update_table(selected_experiment):
    if selected_experiment is None:
        return []
    df = fetch_metrics(selected_experiment)
    return df.to_dict('records')

# Run server
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8050, debug=True)
