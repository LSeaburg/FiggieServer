# Figgie Experiment Dashboard

A modern, responsive web dashboard for managing and analyzing Figgie trading experiments.

## Usage

### Starting the Dashboard
```bash
cd dashboard
python app.py
```

The dashboard will be available at `http://localhost:8050`

### Creating Experiments
1. Fill in the experiment name and description
2. Select the number of players (4 or 5)
3. Configure each agent:
   - Choose agent type (Fundamentalist, NoiseTrader, BottomFeeder)
   - Set polling rate
   - Fill in agent-specific parameters (validated and coerced)
4. Click "Save Experiment"

**Note**: The agent configuration form saves all settings including the Extra Configuration JSON to the database. Values are collected via an intermediate data store to avoid callback conflicts.

### Running Experiments
1. Select an existing experiment from the dropdown
2. Click "Run Experiment"
3. The game will start in the background
4. Results will appear automatically once the game completes

### Viewing Results
- **Metrics Table**: Shows detailed performance data for each agent
- **Performance Charts**: Visual representation of agent performance
- **Experiment Info**: Summary statistics and metadata

## Architecture

### Code Organization

The dashboard follows a modular architecture with clear separation of concerns:

```
dashboard/
├── app.py                    # Main application entry point
├── layout.py                 # UI layout components
├── components/               # Reusable UI components
│   ├── charts.py            # Plotly figure builders
│   ├── messages.py          # HTML message helpers
│   └── utils.py             # UI utility functions
├── config/                   # Configuration and constants
│   ├── settings.py          # General settings and env vars
│   ├── ids.py               # Component ID constants
│   └── agent_specs.py       # Agent specification dataclasses
├── services/                 # Business logic and data access
│   ├── data.py              # DataService (caching + data fetching)
│   ├── metrics.py           # Database read operations
│   ├── experiments.py       # Database write operations
│   ├── runner.py            # Game execution orchestration
│   └── queries.py           # Raw SQL queries
├── callbacks/                # Dash callback modules
│   ├── experiments.py       # Experiment list/info callbacks
│   ├── results.py           # Results table/charts callbacks
│   ├── agents.py            # Agent configuration callbacks
│   └── actions.py           # Save/run action callbacks
└── assets/                   # Static assets (CSS, etc.)
```

### Key Components

- **`DataService`**: Provides caching and delegates to services for data operations
- **`AgentSpec`/`ParamSpec`**: Loaded via dataclasses with validation, then exposed as dicts
- **Modular callbacks**: Organized by domain (experiments, results, agents, actions)
- **Service layer**: Separates business logic from UI concerns
- **Component library**: Reusable UI elements (charts, messages, utils)

### Performance Optimizations

- **Smart caching**: 5-second cache for experiment list, 2-second cache for metrics
- **Efficient queries**: Optimized SQL with proper indexing and bundled queries
- **Background processing**: Non-blocking game execution in daemon threads
- **Lazy loading**: Data loaded only when needed
- **Dynamic component handling**: `suppress_callback_exceptions=True` for graceful handling of dynamically created components
- **DataTable virtualization**: Enabled for better performance with large datasets

### User Experience

- **Loading states**: Visual feedback during operations
- **Auto-refresh**: No manual refresh needed
- **Responsive design**: Works on all screen sizes
- **Accessibility**: Proper focus states and keyboard navigation
- **Consistent messaging**: Standardized success/error message components

## Configuration

### Environment Variables
- `FIGGIE_SERVER_4P_URL`: URL for 4-player server (default: http://localhost:5050)
- `FIGGIE_SERVER_5P_URL`: URL for 5-player server (default: http://localhost:5051)

### Settings
- `REFRESH_INTERVAL`: Dashboard refresh rate in milliseconds (default: 5000)
- `DEFAULT_POLLING_RATE`: Default agent polling rate (default: 0.25)
- `MAX_PLAYERS`: Maximum number of players per experiment (default: 5)
- `EXPERIMENTS_CACHE_TTL`: Cache TTL for experiment list in seconds (default: 5)
- `MESSAGE_HIDE_INTERVAL_MS`: Auto-hide interval for messages in milliseconds (default: 5000)

### Database
The dashboard connects to the same PostgreSQL database as the Figgie server. Make sure the database is running and accessible.

## Dependencies

- **Dash**: Web framework for building analytical web applications
- **Plotly**: Interactive plotting library
- **Pandas**: Data manipulation and analysis
- **Psycopg**: PostgreSQL adapter for Python

### Error Messages

- **"Invalid argument options passed into Dropdown"**: This was fixed in the latest version. The dropdown now properly formats options with only `label` and `value` properties.
- **"Object of type datetime is not JSON serializable"**: Fixed by converting datetime objects to ISO format strings.
- **"Output is already in use"**: Fixed by ensuring each callback has unique outputs and removing duplicate output assignments.
- **"A nonexistent object was used in an Output"**: Fixed by removing the redundant `toggle_agent_blocks` callback and handling agent block visibility directly in the `update_agent_configs` callback.
- **"A nonexistent object was used in a State"**: Fixed by simplifying the save experiment callback to not depend on dynamically created agent input elements, using default agent configuration instead. Also enabled `suppress_callback_exceptions=True` to handle dynamic component creation gracefully.
- **"Object of type Decimal is not JSON serializable"**: Fixed by converting Decimal objects to float before JSON serialization in the metrics callback.
- **"Output agent-config-store.data is already in use"**: Fixed by combining duplicate callbacks into one unified callback using `dash.callback_context` to handle both num-players changes and form value updates.

### Debug Mode
Run with debug enabled for detailed error messages:
```bash
python app.py --debug
```

## Development

### Running Tests
```bash
pytest tests/test_dashboard.py -v
```

## Future Enhancements

- [ ] Real-time game monitoring with WebSocket updates
- [ ] Advanced filtering and search for experiments
- [ ] Comparative analysis between experiments
- [ ] Export functionality for experiment configurations
- [ ] Agent performance benchmarking tools
