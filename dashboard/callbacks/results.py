from __future__ import annotations

import json
from typing import List

import pandas as pd
from dash import Dash
from dash.dependencies import Input, Output

from dashboard.config.ids import (
    EXPERIMENT_DROPDOWN,
    INTERVAL,
    RESULTS_TABLE,
    METRICS_DATA,
    PROFIT_CHART,
)
from dashboard.components.charts import empty_centered_message, profit_box_plot


def register_results_callbacks(app: Dash, data_manager):
    @app.callback(
        [Output(RESULTS_TABLE, 'data'), Output(METRICS_DATA, 'children'), Output(PROFIT_CHART, 'figure')],
        [Input(EXPERIMENT_DROPDOWN, 'value'), Input(INTERVAL, 'n_intervals')],
    )
    def update_metrics_and_charts(selected_experiment, n_intervals):  # noqa: F401
        if not selected_experiment:
            empty_fig = empty_centered_message("Select an experiment to view results")
            return [], "", empty_fig

        df = data_manager.fetch_metrics(selected_experiment)
        if df.empty:
            empty_fig = empty_centered_message("No data available for this experiment")
            return [], "", empty_fig

        profit_df = data_manager.fetch_individual_profits(selected_experiment)
        profit_fig = profit_box_plot(profit_df)

        # Minimal sanitization for DataTable/JSON
        if 'avg_profit' in df.columns:
            df['avg_profit'] = pd.to_numeric(df['avg_profit'], errors='coerce')
        df = df.where(pd.notna(df), None)

        records = df.to_dict('records')

        return records, json.dumps(records), profit_fig


