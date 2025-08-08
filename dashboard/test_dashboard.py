#!/usr/bin/env python3
"""
Simple test script to verify dashboard functionality
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import data_manager, app
import json

def test_data_manager():
    """Test the data manager functionality"""
    print("Testing DataManager...")
    
    try:
        # Test fetching experiments
        experiments = data_manager.fetch_experiments(force_refresh=True)
        print(f"Found {len(experiments)} experiments")
        
        if experiments:
            # Test fetching metrics for first experiment
            first_exp = experiments[0]['value']
            metrics = data_manager.fetch_metrics(first_exp)
            print(f"Found {len(metrics)} metric rows for experiment {first_exp}")
        
        print("DataManager tests passed")
        return True
    except Exception as e:
        print(f"DataManager test failed: {e}")
        return False

def test_app_layout():
    """Test that the app layout can be created"""
    print("Testing app layout...")
    
    try:
        # This will test that all components can be created
        layout = app.layout
        print("App layout created successfully")
    except Exception as e:
        print(f"App layout creation failed: {e}")
        return False
    
    return True

def test_callbacks():
    """Test that callbacks can be registered"""
    print("Testing callbacks...")
    
    try:
        # Check that callbacks are registered
        callback_count = len(app.callback_map)
        print(f"{callback_count} callbacks registered")
        
        # Verify no duplicate outputs
        all_outputs = []
        for callback in app.callback_map.values():
            if hasattr(callback, 'outputs'):
                all_outputs.extend(callback.outputs)
        
        # Check for duplicate outputs
        output_counts = {}
        for output in all_outputs:
            output_str = str(output)
            output_counts[output_str] = output_counts.get(output_str, 0) + 1
        
        duplicates = [output for output, count in output_counts.items() if count > 1]
        if duplicates:
            print(f"Found duplicate outputs: {duplicates}")
            return False
        else:
            print("No duplicate outputs found")
        
        # Test dropdown options format
        from app import update_experiments_list
        experiments = data_manager.fetch_experiments(force_refresh=True)
        if experiments:
            try:
                dropdown_options, _, _ = update_experiments_list(0, 0)
                for option in dropdown_options:
                    if not isinstance(option, dict) or 'label' not in option or 'value' not in option:
                        print("Dropdown options format is incorrect")
                        return False
                print("Dropdown options format is correct")
            except Exception as e:
                print(f"Dropdown options test failed: {e}")
                return False
        else:
            print("No experiments found (database may not be running)")
            print("Dropdown structure test skipped")
        
    except Exception as e:
        print(f"Callback registration failed: {e}")
        return False
    
    return True

def main():
    """Run all tests"""
    print("Testing Figgie Dashboard...")
    print("=" * 50)
    
    tests = [
        test_data_manager,
        test_app_layout,
        test_callbacks,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"Test failed with exception: {e}")
    
    print("=" * 50)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("All tests passed! Dashboard is ready to use.")
        return 0
    else:
        print("Some tests failed. Please check the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
