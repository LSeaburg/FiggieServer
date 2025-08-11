from dashboard.app import data_manager, app
from dashboard.components import format_timestamp
from dashboard.services import DataService
from dashboard.config.agent_specs import load_agent_specs, get_spec_by_module, validate_params
from unittest.mock import patch, MagicMock
import pandas as pd

def test_data_manager():
    """Test the data manager functionality"""
    experiments = data_manager.fetch_experiments(force_refresh=True)
    # Should return a list even if DB is unavailable
    assert isinstance(experiments, list)

def test_app_layout():
    """Test that the app layout can be created"""
    # This will test that all components can be created
    layout = app.layout
    assert layout is not None

def test_callbacks():
    """Test that callbacks are registered and outputs are unique"""
    # Check that callbacks are registered
    callback_count = len(app.callback_map)
    assert callback_count > 0

    # Verify no duplicate outputs
    all_outputs = []
    for callback in app.callback_map.values():
        if hasattr(callback, "outputs"):
            all_outputs.extend(callback.outputs)

    # Check for duplicate outputs
    output_counts = {}
    for output in all_outputs:
        output_str = str(output)
        output_counts[output_str] = output_counts.get(output_str, 0) + 1

    duplicates = [output for output, count in output_counts.items() if count > 1]
    assert not duplicates, f"Found duplicate outputs: {duplicates}"

    # Test dropdown options format
    experiments = data_manager.fetch_experiments(force_refresh=True)
    # The dropdown is expected to contain options with label/value built from experiments
    dropdown_options = [{'label': exp['label'], 'value': exp['value']} for exp in experiments]
    for option in dropdown_options:
        assert isinstance(option, dict) and "label" in option and "value" in option


def test_agent_specs_loading_and_validation():
    specs, mapping = load_agent_specs()
    assert isinstance(specs, list)
    assert isinstance(mapping, dict)
    # if any spec exists, validate param coercion path is stable
    if specs:
        spec = specs[0]
        coerced, errors = validate_params({}, spec)
        assert isinstance(coerced, dict)
        assert isinstance(errors, list)

def test_format_timestamp_graceful():
    ts = '2024-01-02T03:04:05Z'
    human = format_timestamp(ts)
    assert '2024' in human
    assert 'January' in human
    # bad input returns original
    assert format_timestamp('not-a-date') == 'not-a-date'

def test_data_manager_logs_on_errors(monkeypatch):
    dm = DataService()
    fake_conn = MagicMock()
    fake_cur = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cur
    # force execute to raise
    fake_cur.execute.side_effect = RuntimeError('boom')
    with patch('dashboard.services.data.get_connection', return_value=fake_conn):
        # these should swallow exceptions and return empty structures
        assert dm.fetch_experiments(force_refresh=True) == []
        assert isinstance(dm.fetch_metrics(1), pd.DataFrame)
        assert dm.fetch_metrics(1).empty
        assert isinstance(dm.fetch_individual_profits(1), pd.DataFrame)
        assert dm.fetch_individual_profits(1).empty
