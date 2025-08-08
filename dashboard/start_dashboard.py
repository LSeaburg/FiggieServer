#!/usr/bin/env python3
"""
Startup script for the Figgie Experiment Dashboard
"""

import os
import sys
import argparse
from pathlib import Path

def check_dependencies():
    """Check if all required dependencies are available"""
    try:
        import dash
        import plotly
        import pandas
        import psycopg
        print("All dependencies are available")
        return True
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Please install required packages: pip install -r ../requirements-dev.txt")
        return False

def check_database():
    """Check if database is accessible"""
    try:
        from figgie_server.db import get_connection
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        print("Database connection successful")
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        print("Please ensure the PostgreSQL database is running and accessible")
        return False

def main():
    parser = argparse.ArgumentParser(description="Start the Figgie Experiment Dashboard")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8050, help="Port to bind to (default: 8050)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--no-check", action="store_true", help="Skip dependency and database checks")
    
    args = parser.parse_args()
    
    print("Starting Figgie Experiment Dashboard...")
    print("=" * 50)
    
    # Add parent directory to path
    parent_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(parent_dir))
    
    if not args.no_check:
        print("Checking dependencies...")
        if not check_dependencies():
            return 1
        
        print("Checking database connection...")
        if not check_database():
            return 1
    
    try:
        from app import app
        
        print(f"Starting dashboard on http://{args.host}:{args.port}")
        print("Press Ctrl+C to stop")
        print("=" * 50)
        
        app.run(
            host=args.host,
            port=args.port,
            debug=args.debug,
            use_reloader=args.debug
        )
        
    except KeyboardInterrupt:
        print("\nDashboard stopped by user")
        return 0
    except Exception as e:
        print(f"Failed to start dashboard: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
