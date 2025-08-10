from dash import html


def success(message: str):
    return html.Div(message, className="success-message message-auto-hide")


def error(message: str):
    return html.Div(message, className="error-message message-auto-hide")


def error_list(title: str, items: list[str]):
    return html.Div([
        html.Div(title, className="error-message"),
        html.Ul([html.Li(item) for item in items]),
    ])


