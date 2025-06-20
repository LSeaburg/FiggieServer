import os
import sqlite3
import threading
import json
from datetime import datetime

# Path to the SQLite DB from environment variable
DB_PATH = os.getenv("DB_PATH", "data/figgie.db")

# Ensure thread-safe DB access
_db_lock = threading.Lock()

# Initialize connection
_conn = None

def get_connection():
    global _conn
    if _conn is None:
        # Create directory if needed
        db_dir = os.path.dirname(DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn

def init_db():
    conn = get_connection()
    with _db_lock:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players(
                player_id TEXT PRIMARY KEY,
                name TEXT,
                joined_at DATETIME
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rounds(
                round_id TEXT PRIMARY KEY,
                start_time DATETIME,
                end_time DATETIME
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS actions(
                action_id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id TEXT,
                player_id TEXT,
                action_type TEXT,
                order_id TEXT,
                order_type TEXT,
                suit TEXT,
                price INTEGER,
                time_remaining INTEGER,
                timestamp DATETIME
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades(
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id TEXT,
                buyer TEXT,
                seller TEXT,
                suit TEXT,
                price INTEGER,
                time_remaining INTEGER,
                timestamp DATETIME
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS results(
                round_id TEXT PRIMARY KEY,
                results TEXT,
                timestamp DATETIME
            )
        ''')
        conn.commit()

def log_player(player_id: str, name: str):
    conn = get_connection()
    with _db_lock:
        conn.execute(
            'INSERT OR IGNORE INTO players(player_id, name, joined_at) VALUES (?, ?, ?)',
            (player_id, name, datetime.utcnow())
        )
        conn.commit()

def log_round_start(round_id: str):
    conn = get_connection()
    with _db_lock:
        conn.execute(
            'INSERT OR REPLACE INTO rounds(round_id, start_time) VALUES (?, ?)',
            (round_id, datetime.utcnow())
        )
        conn.commit()

def log_order(round_id: str, order, time_remaining: int):
    conn = get_connection()
    with _db_lock:
        conn.execute(
            '''INSERT INTO actions
                (action_type, round_id, order_id, player_id, order_type, suit, price, time_remaining, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            ('order', round_id, order.order_id, order.player_id, order.type,
             order.suit, order.price, time_remaining, datetime.utcnow())
        )
        conn.commit()

def log_cancellation(round_id: str, order, time_remaining: int):
    conn = get_connection()
    with _db_lock:
        conn.execute(
            '''INSERT INTO actions
                (action_type, round_id, order_id, player_id, order_type, suit, price, time_remaining, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            ('cancellation', round_id, order.order_id, order.player_id, order.type,
             order.suit, order.price, time_remaining, datetime.utcnow())
        )
        conn.commit()

def log_trade(round_id: str, trade, time_remaining: int):
    conn = get_connection()
    with _db_lock:
        conn.execute(
            '''INSERT INTO trades
                (round_id, buyer, seller, suit, price, time_remaining, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (round_id, trade.buyer, trade.seller, trade.suit,
             trade.price, time_remaining, datetime.utcnow())
        )
        conn.commit()

def log_round_end(round_id: str, results: dict):
    conn = get_connection()
    with _db_lock:
        # Update end_time in rounds
        conn.execute(
            'UPDATE rounds SET end_time = ? WHERE round_id = ?',
            (datetime.utcnow(), round_id)
        )
        # Store results JSON
        conn.execute(
            'INSERT OR REPLACE INTO results(round_id, results, timestamp) VALUES (?, ?, ?)',
            (round_id, json.dumps(results), datetime.utcnow())
        )
        conn.commit()