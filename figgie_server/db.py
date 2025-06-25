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
                goal_suit TEXT,
                small_suit TEXT,
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
            CREATE TABLE IF NOT EXISTS agents(
                id SERIAL PRIMARY KEY,
                player_id TEXT UNIQUE,
                module_name TEXT,
                attr_name TEXT,
                extra_kwargs JSONB,
                polling_rate REAL,
                created_at TIMESTAMP WITH TIME ZONE
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS results(
                round_id         TEXT    NOT NULL,
                player_id        TEXT    NOT NULL,
                initial_balance  INTEGER NOT NULL,
                final_balance    INTEGER NOT NULL,
                initial_spades   INTEGER NOT NULL,
                initial_clubs    INTEGER NOT NULL,
                initial_hearts   INTEGER NOT NULL,
                initial_diamonds INTEGER NOT NULL,
                final_spades     INTEGER NOT NULL,
                final_clubs      INTEGER NOT NULL,
                final_hearts     INTEGER NOT NULL,
                final_diamonds   INTEGER NOT NULL,
                bonus            INTEGER NOT NULL,
                is_winner        BOOLEAN NOT NULL,
                share_each       INTEGER NOT NULL,
                PRIMARY KEY (round_id, player_id)
            );
        ''')
        conn.commit()

def log_player(player_id: str, name: str):
    conn = get_connection()
    with _db_lock:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO players(player_id, name, joined_at) 
            VALUES (%s, %s, %s) 
            ON CONFLICT (player_id) DO NOTHING''',
            (player_id, name, datetime.now(timezone.utc))
        )
        conn.commit()

def log_round_start(round_id: str, num_players: int, round_duration: int, goal_suit: str, small_suit: str):
    conn = get_connection()
    with _db_lock:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO rounds
            (round_id, num_players, round_duration, goal_suit, small_suit, start_time)
            VALUES (%s, %s, %s, %s, %s, %s) 
            ON CONFLICT (round_id) 
            DO UPDATE 
                SET start_time = EXCLUDED.start_time,
                    num_players = EXCLUDED.num_players,
                    round_duration = EXCLUDED.round_duration,
                    goal_suit = EXCLUDED.goal_suit,
                    small_suit = EXCLUDED.small_suit
            ''',
            (round_id, num_players, round_duration, goal_suit, small_suit, datetime.now(timezone.utc))
        )
        conn.commit()

def log_order(round_id: str, order, time_remaining: int):
    conn = get_connection()
    with _db_lock:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO actions
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
        cursor.execute('''
            INSERT INTO actions
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
        cursor.execute('''
            INSERT INTO trades
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
        cursor.execute('''
            UPDATE rounds SET end_time = %s WHERE round_id = %s''',
            (datetime.now(timezone.utc), round_id)
        )
        for pid, init_bal in initial_balances.items():
            final_bal = final_balances.get(pid, 0)
            init_hand = initial_hands.get(pid, {})
            final_hand = final_hands.get(pid, {})
            cursor.execute('''
                INSERT INTO results
                (round_id, player_id,
                 initial_balance, final_balance,
                 initial_spades, initial_clubs, initial_hearts, initial_diamonds,
                 final_spades, final_clubs, final_hearts, final_diamonds,
                 bonus, is_winner, share_each)
                    VALUES (%s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s)
                ON CONFLICT (round_id, player_id) DO UPDATE SET
                    initial_balance = EXCLUDED.initial_balance,
                    final_balance   = EXCLUDED.final_balance,
                    initial_spades  = EXCLUDED.initial_spades,
                    initial_clubs   = EXCLUDED.initial_clubs,
                    initial_hearts  = EXCLUDED.initial_hearts,
                    initial_diamonds= EXCLUDED.initial_diamonds,
                    final_spades    = EXCLUDED.final_spades,
                    final_clubs     = EXCLUDED.final_clubs,
                    final_hearts    = EXCLUDED.final_hearts,
                    final_diamonds  = EXCLUDED.final_diamonds,
                    bonus           = EXCLUDED.bonus,
                    is_winner       = EXCLUDED.is_winner,
                    share_each      = EXCLUDED.share_each
                ''',
                (
                    round_id, pid,
                    init_bal, final_bal,
                    init_hand.get('spades', 0), init_hand.get('clubs', 0),
                    init_hand.get('hearts', 0), init_hand.get('diamonds', 0),
                    final_hand.get('spades', 0), final_hand.get('clubs', 0),
                    final_hand.get('hearts', 0), final_hand.get('diamonds', 0),
                    results.get('bonuses', {}).get(pid, 0),
                    pid in results.get('winners', []),
                    results.get('share_each', 0)
                )
            )
        conn.commit()

def log_agent(player_id: str, module_name: str, attr_name: str, extra_kwargs: dict, polling_rate: float):
    conn = get_connection()
    with _db_lock:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO agents (player_id, module_name, attr_name, extra_kwargs, polling_rate, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (player_id) DO NOTHING
        ''',
        (player_id, module_name, attr_name, json.dumps(extra_kwargs), polling_rate, datetime.now(timezone.utc))
        )
        conn.commit()
