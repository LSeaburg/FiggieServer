import os
import threading
import json
from datetime import datetime, timezone
import psycopg

# Database connection parameters from environment
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "figgie")
DB_USER = os.getenv("DB_USER", "figgie")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secret_password")
DB_PORT = os.getenv("DB_PORT", "5432")

# Ensure thread-safe DB access
_db_lock = threading.Lock()

# Singleton connection
_conn = None

def get_connection():
    global _conn
    if _conn is None:
        host = os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("DB_PORT", "5432"))
        dbname = os.getenv("DB_NAME", "figgie")
        user = os.getenv("DB_USER", "figgie")
        password = os.getenv("DB_PASSWORD", "secret_password")
        _conn = psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        )
    return _conn

def init_db():
    conn = get_connection()
    with _db_lock:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players(
                player_id TEXT PRIMARY KEY,
                name TEXT,
                joined_at TIMESTAMP WITH TIME ZONE
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rounds(
                round_id TEXT PRIMARY KEY,
                num_players INTEGER,
                round_duration INTEGER,
                start_time TIMESTAMP WITH TIME ZONE,
                end_time TIMESTAMP WITH TIME ZONE
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS actions(
                action_id SERIAL PRIMARY KEY,
                round_id TEXT,
                player_id TEXT,
                action_type TEXT,
                order_id TEXT,
                order_type TEXT,
                suit TEXT,
                price INTEGER,
                time_remaining INTEGER,
                timestamp TIMESTAMP WITH TIME ZONE
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades(
                trade_id SERIAL PRIMARY KEY,
                round_id TEXT,
                buyer TEXT,
                seller TEXT,
                suit TEXT,
                price INTEGER,
                time_remaining INTEGER,
                timestamp TIMESTAMP WITH TIME ZONE
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS results(
                round_id TEXT PRIMARY KEY,
                results TEXT,
                initial_balances TEXT,
                final_balances TEXT,
                initial_hands TEXT,
                final_hands TEXT,
                timestamp TIMESTAMP WITH TIME ZONE
            );
        ''')
        conn.commit()

def log_player(player_id: str, name: str):
    conn = get_connection()
    with _db_lock:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO players(player_id, name, joined_at) 
               VALUES (%s, %s, %s) 
               ON CONFLICT (player_id) DO NOTHING''',
            (player_id, name, datetime.now(timezone.utc))
        )
        conn.commit()

def log_round_start(round_id: str, num_players: int, round_duration: int):
    conn = get_connection()
    with _db_lock:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO rounds
               (round_id, num_players, round_duration, start_time)
               VALUES (%s, %s, %s, %s) 
               ON CONFLICT (round_id) 
               DO UPDATE 
                 SET start_time = EXCLUDED.start_time,
                     num_players = EXCLUDED.num_players,
                     round_duration = EXCLUDED.round_duration
            ''',
            (round_id, num_players, round_duration, datetime.now(timezone.utc))
        )
        conn.commit()

def log_order(round_id: str, order, time_remaining: int):
    conn = get_connection()
    with _db_lock:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO actions
               (action_type, round_id, order_id, player_id, order_type, suit, price, time_remaining, timestamp)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            ('order', round_id, order.order_id, order.player_id, order.type,
             order.suit, order.price, time_remaining, datetime.now(timezone.utc))
        )
        conn.commit()

def log_cancellation(round_id: str, order, time_remaining: int):
    conn = get_connection()
    with _db_lock:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO actions
               (action_type, round_id, order_id, player_id, order_type, suit, price, time_remaining, timestamp)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            ('cancellation', round_id, order.order_id, order.player_id, order.type,
             order.suit, order.price, time_remaining, datetime.now(timezone.utc))
        )
        conn.commit()

def log_trade(round_id: str, trade, time_remaining: int):
    conn = get_connection()
    with _db_lock:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO trades
               (round_id, buyer, seller, suit, price, time_remaining, timestamp)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (round_id, trade.buyer, trade.seller, trade.suit,
             trade.price, time_remaining, datetime.now(timezone.utc))
        )
        conn.commit()

def log_round_end(round_id: str, results: dict, initial_balances: dict, final_balances: dict, initial_hands: dict, final_hands: dict):
    conn = get_connection()
    with _db_lock:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE rounds SET end_time = %s WHERE round_id = %s',
            (datetime.now(timezone.utc), round_id)
        )
        cursor.execute(
            '''INSERT INTO results
               (round_id, results, initial_balances, final_balances, initial_hands, final_hands, timestamp) 
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (round_id) DO UPDATE
                 SET results = EXCLUDED.results,
                     initial_balances = EXCLUDED.initial_balances,
                     final_balances = EXCLUDED.final_balances,
                     initial_hands = EXCLUDED.initial_hands,
                     final_hands = EXCLUDED.final_hands,
                     timestamp = EXCLUDED.timestamp
            ''',
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