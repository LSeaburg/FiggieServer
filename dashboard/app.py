from typing import List, Tuple

from dash import Dash

from dashboard.agent_specs import load_agent_specs
from dashboard.data import DashboardDataManager
from dashboard.layout import build_app_layout
from dashboard.callbacks import register_callbacks


# Load agent specs and derived data
AGENT_SPECS, MODULE_TO_ATTR = load_agent_specs()

# Initialize data manager and app
data_manager = DashboardDataManager()
app = Dash(
    __name__,
    external_stylesheets=['https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css'],
    suppress_callback_exceptions=True,
)

# Layout
app.layout = build_app_layout(AGENT_SPECS, data_manager.fetch_experiments())

# Callbacks
register_callbacks(app, data_manager, MODULE_TO_ATTR, AGENT_SPECS)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8050, debug=True)
