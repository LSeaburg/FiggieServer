from typing import Any

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


def empty_centered_message(message: str) -> go.Figure:
    fig = go.Figure().add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
    )
    return fig


def profit_box_plot(profit_df: pd.DataFrame) -> go.Figure:
    if profit_df.empty:
        return empty_centered_message("No individual game data available for box plot")
    fig = px.box(
        profit_df,
        x="agent_name",
        y="profit",
        title="Profit Distribution by Agent",
        labels={"profit": "Profit per Game", "agent_name": "Agent"},
        color="agent_name",
        points="outliers",
    )
    fig.update_layout(height=400, showlegend=False, xaxis_title="Agent", yaxis_title="Profit per Game")
    return fig


