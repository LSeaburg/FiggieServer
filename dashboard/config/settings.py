import os

# Server URLs
FOUR_PLAYER_SERVER = os.getenv("FIGGIE_SERVER_4P_URL", "http://localhost:5050")
FIVE_PLAYER_SERVER = os.getenv("FIGGIE_SERVER_5P_URL", "http://localhost:5051")

# UI/config defaults
DEFAULT_POLLING_RATE = 0.25
MIN_POLLING_RATE = 0.01
REFRESH_INTERVAL = 5000  # milliseconds

# Dashboard behavior
MAX_PLAYERS = 5
EXPERIMENTS_CACHE_TTL = 5  # seconds
MESSAGE_HIDE_INTERVAL_MS = 3000


