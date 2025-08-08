from dashboard.app import data_manager, app, update_experiments_list

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
    if experiments:
        dropdown_options, _, _ = update_experiments_list(0, 0)
        for option in dropdown_options:
            assert isinstance(option, dict) and "label" in option and "value" in option
