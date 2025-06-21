import os
import sqlite3
import threading
import json
from datetime import datetime, timezone

# Register adapter and converter for timezone-aware datetime
def _adapt_datetime(dt: datetime) -> bytes:
    return dt.isoformat().encode()

def _convert_datetime(b: bytes) -> datetime:
    return datetime.fromisoformat(b.decode())

sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_converter("DATETIME", _convert_datetime)

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
        _conn = sqlite3.connect(
            DB_PATH,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
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
                initial_balances TEXT,
                final_balances TEXT,
                initial_hands TEXT,
                final_hands TEXT,
                timestamp DATETIME
            )
        ''')
        conn.commit()

def log_player(player_id: str, name: str):
    conn = get_connection()
    with _db_lock:
        conn.execute(
            'INSERT OR IGNORE INTO players(player_id, name, joined_at) VALUES (?, ?, ?)',
            (player_id, name, datetime.now(timezone.utc))
        )
        conn.commit()

def log_round_start(round_id: str):
    conn = get_connection()
    with _db_lock:
        conn.execute(
            'INSERT OR REPLACE INTO rounds(round_id, start_time) VALUES (?, ?)',
            (round_id, datetime.now(timezone.utc))
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
             order.suit, order.price, time_remaining, datetime.now(timezone.utc))
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
             order.suit, order.price, time_remaining, datetime.now(timezone.utc))
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
             trade.price, time_remaining, datetime.now(timezone.utc))
        )
        conn.commit()

def log_round_end(round_id: str, results: dict, initial_balances: dict, final_balances: dict, initial_hands: dict, final_hands: dict):
    conn = get_connection()
    with _db_lock:
        # Update end_time in rounds
        conn.execute(
            'UPDATE rounds SET end_time = ? WHERE round_id = ?',
            (datetime.now(timezone.utc), round_id)
        )
        # Store results and state snapshots as JSON
        conn.execute(
            '''INSERT OR REPLACE INTO results
                (round_id, results, initial_balances, final_balances, initial_hands, final_hands, timestamp) 
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (
                round_id,
                json.dumps(results),
                json.dumps(initial_balances),
                json.dumps(final_balances),
                json.dumps(initial_hands),
                json.dumps(final_hands),
                datetime.now(timezone.utc)
            )
        )
        conn.commit()