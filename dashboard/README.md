# Figgie Experiment Dashboard

A modern, responsive web dashboard for managing and analyzing Figgie trading experiments.

## Features

### 🚀 **Real-time Updates**
- **Auto-refresh**: Data automatically updates every 2 seconds
- **Live experiment list**: New experiments appear immediately when created
- **Real-time metrics**: Results update as games are running

### 📊 **Enhanced Analytics**
- **Interactive charts**: Visualize agent performance with Plotly charts
- **Comprehensive metrics**: Average, min, max profits with game counts
- **Export functionality**: Download results as CSV files

### 🎨 **Modern UI/UX**
- **Responsive design**: Works on desktop, tablet, and mobile
- **Modern styling**: Glassmorphism design with smooth animations
- **Intuitive layout**: Two-panel design for easy navigation
- **Visual feedback**: Clear success/error messages with icons

### 🔧 **Improved Functionality**
- **Better error handling**: Comprehensive error messages and validation
- **Data caching**: Efficient data fetching with smart caching
- **Background processing**: Games run in background threads
- **Form validation**: Input validation and user feedback
- **Agent configuration**: Proper saving of all agent settings including JSON configuration

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
   - Add extra configuration as JSON (e.g., `{"buy_ratio": 1.2}`)
4. Click "Save Experiment"

**Note**: The agent configuration form now properly saves all settings including the Extra Configuration JSON to the database. Values are collected via an intermediate data store to avoid callback conflicts.

### Running Experiments
1. Select an existing experiment from the dropdown
2. Click "Run Experiment"
3. The game will start in the background
4. Results will appear automatically as the game progresses

### Viewing Results
- **Metrics Table**: Shows detailed performance data for each agent
- **Performance Charts**: Visual representation of agent performance
- **Experiment Info**: Summary statistics and metadata

## Technical Improvements

### Code Organization
- **DataManager class**: Centralized data fetching with caching
- **Modular callbacks**: Separated concerns for better maintainability
- **Error handling**: Comprehensive try-catch blocks
- **Type hints**: Full type annotations for better code quality

### Performance
- **Smart caching**: 5-second cache for experiment list
- **Efficient queries**: Optimized SQL with proper indexing
- **Background processing**: Non-blocking game execution
- **Lazy loading**: Data loaded only when needed
- **Dynamic component handling**: `suppress_callback_exceptions=True` for graceful handling of dynamically created components

### User Experience
- **Loading states**: Visual feedback during operations
- **Auto-refresh**: No manual refresh needed
- **Responsive design**: Works on all screen sizes
- **Accessibility**: Proper focus states and keyboard navigation

## Configuration

### Environment Variables
- `FIGGIE_SERVER_4P_URL`: URL for 4-player server (default: http://localhost:5050)
- `FIGGIE_SERVER_5P_URL`: URL for 5-player server (default: http://localhost:5051)

### Database
The dashboard connects to the same PostgreSQL database as the Figgie server. Make sure the database is running and accessible.

## Dependencies

- **Dash**: Web framework for building analytical web applications
- **Plotly**: Interactive plotting library
- **Pandas**: Data manipulation and analysis
- **Psycopg**: PostgreSQL adapter for Python

## Browser Support

- Chrome/Chromium (recommended)
- Firefox
- Safari
- Edge

## Troubleshooting

### Common Issues

1. **Dashboard not loading**: Check if the database is running and accessible
2. **Experiments not appearing**: Verify database connection and table structure
3. **Games not running**: Ensure Figgie servers are running on the correct ports
4. **Charts not displaying**: Check browser console for JavaScript errors
5. **Dropdown errors**: Ensure database datetime fields are properly formatted

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

## Future Enhancements

- [ ] Real-time game monitoring with WebSocket updates
- [ ] Advanced filtering and search for experiments
- [ ] Comparative analysis between experiments
- [ ] Agent performance trends over time
- [ ] Export to additional formats (Excel, JSON)
- [ ] User authentication and experiment sharing
