from __future__ import annotations

import json
from datetime import datetime
from typing import List

from dash import Dash
from dash.dependencies import Input, Output

from dashboard.config.ids import (
    EXPERIMENT_DROPDOWN,
    EXPERIMENTS_DATA,
    LAST_UPDATED,
    INTERVAL,
    EXPERIMENT_INFO,
)


def register_experiment_callbacks(app: Dash, data_manager):
    @app.callback(
        [Output(EXPERIMENT_DROPDOWN, 'options'), Output(EXPERIMENTS_DATA, 'children'), Output(LAST_UPDATED, 'children')],
        Input(INTERVAL, 'n_intervals'),
        prevent_initial_call=False,
    )
    def update_experiments_list(n_intervals):  # noqa: F401
        experiments = data_manager.fetch_experiments(force_refresh=True)
        dropdown_options = [{'label': exp['label'], 'value': exp['value']} for exp in experiments]
        timestamp = datetime.now().strftime("%H:%M:%S")
        return dropdown_options, json.dumps(experiments), f"Last updated: {timestamp}"

    @app.callback(
        Output(EXPERIMENT_INFO, 'children'),
        [Input(EXPERIMENT_DROPDOWN, 'value'), Input(EXPERIMENTS_DATA, 'children')],
    )
    def update_experiment_info(selected_experiment, experiments_json):  # noqa: F401
        if not selected_experiment or not experiments_json:
            return ""
        try:
            experiments = json.loads(experiments_json)
            experiment = next((exp for exp in experiments if exp['value'] == selected_experiment), None)
            if not experiment:
                return ""
            from dashboard.components import format_timestamp
            from dash import html
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
            import logging
            logging.getLogger(__name__).exception("Failed to render experiment info")
            return ""


