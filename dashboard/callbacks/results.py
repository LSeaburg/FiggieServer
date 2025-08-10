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

        records = df.to_dict('records')
        for record in records:
            for key, value in record.items():
                if hasattr(value, 'as_tuple'):
                    record[key] = float(value)
                elif pd.isna(value):
                    record[key] = None

        return records, json.dumps(records), profit_fig


