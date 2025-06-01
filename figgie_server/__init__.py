# figgie_server/__init__.py

"""
figgie_server
=============

This package contains all the pieces of the Figgie trading game server.
"""

# expose the Flask app instance, so a top‐level import will just work:
from .api import app

# expose the Game orchestrator class
from .game import Game

__all__ = [
    "app",      # the Flask app you can run
    "Game",     # programmatic access to the core game logic
]