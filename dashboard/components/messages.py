from dash import html
import datetime


def success(message: str):
    return html.Div([
        html.Div([
            html.I(className="fas fa-check-circle", style={'marginRight': '8px'}),
            html.Span(message)
        ], className="message-content")
    ], className="message-popup message-success message-auto-hide", key=f"msg-success-{datetime.datetime.now().timestamp()}")


def error(message: str):
    return html.Div([
        html.Div([
            html.I(className="fas fa-exclamation-circle", style={'marginRight': '8px'}),
            html.Span(message)
        ], className="message-content")
    ], className="message-popup message-error message-auto-hide", key=f"msg-error-{datetime.datetime.now().timestamp()}")


def error_list(title: str, items: list[str]):
    return html.Div([
        html.Div([
            html.Div([
                html.I(className="fas fa-exclamation-circle", style={'marginRight': '8px'}),
                html.Span(title)
            ], className="message-popup-header"),
            html.Ul([
                html.Li([
                    html.I(className="fas fa-times", style={'marginRight': '6px', 'fontSize': '0.8em'}),
                    html.Span(item)
                ]) for item in items
            ], className="message-popup-list")
        ], className="message-content")
    ], className="message-popup message-error-list", key=f"msg-error-list-{datetime.datetime.now().timestamp()}")


