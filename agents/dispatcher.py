import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import importlib
import time
import logging
from typing import List, Tuple, Dict, Any

from agents.figgie_interface import FiggieInterface
import figgie_server.db as db

# Configuration: list of (module_name, attribute_name, extra_kwargs)
# module_name is the Python module (without .py) in this folder.
# attribute_name is the class name (subclass of FiggieInterface) or factory function name.
# extra_kwargs is a dict of additional parameters for that agent (empty if none).
AGENTS: List[Tuple[str, str, Dict[str, Any]]] = [
    ("fundamentalist", "Fundamentalist", {"aggression": 0.8, "buy_ratio": 1.7}),
    ("fundamentalist", "Fundamentalist", {"aggression": 0.6, "buy_ratio": 1.6}),
    ("noise_trader", "NoiseTrader", {"aggression": 0.6, "default_val": 7}),
    ("noise_trader", "NoiseTrader", {"aggression": 0.4, "default_val": 9})
]

def make_agent(
    entry: Tuple[str, str, Dict[str, Any]],
    name: str,
    server_url: str,
    polling_rate: float
) -> FiggieInterface:
    """
    Dynamically import and instantiate an agent with extra kwargs.
    entry: (module_name, attribute_name, extra_kwargs)
    """
    module_name, attr_name, extra_kwargs = entry

    module = importlib.import_module(f"agents.{module_name}")
    factory = getattr(module, attr_name)

    # Base init kwargs
    init_kwargs = {
        "server_url": server_url,
        "name": name,
        "polling_rate": polling_rate,
    }
    # Merge agent-specific overrides
    init_kwargs.update(extra_kwargs)

    # Class-based agent
    if isinstance(factory, type) and issubclass(factory, FiggieInterface):
        return factory(**init_kwargs)

    # Factory-based agent
    if callable(factory):
        try:
            return factory(**init_kwargs)
        except TypeError:
            # Fallback to positional signature
            return factory(name, server_url, polling_rate)

    raise ValueError(f"Cannot instantiate agent from entry {entry}")


def main():
    logging.basicConfig(level=logging.INFO)
    server_url = os.getenv("SERVER_URL", "http://localhost:8000")
    polling_rate = float(os.getenv("POLLING_RATE", "0.25"))
    num_players = int(os.getenv("NUM_PLAYERS", "4"))

    if num_players != len(AGENTS):
        raise RuntimeError(f"Requested {num_players} players but {len(AGENTS)} configured.")

    selected = AGENTS[:num_players]
    logging.info(f"Spawning {num_players} agents...")
    clients = []

    for idx, entry in enumerate(selected, start=1):
        module_name, attr_name, extra_kwargs = entry
        player_name = f"{attr_name}{idx}"
        logging.info(f"Starting agent {player_name} ({module_name}.{attr_name})")
        client = make_agent(entry, player_name, server_url, polling_rate)
        # Log agent registration
        db.log_agent(client.player_id, module_name, attr_name, extra_kwargs, polling_rate)
        clients.append(client)

    try:
        # Wait until any client sees the round complete
        while True:
            time.sleep(1)
            done = next(
                (c for c in clients if c._last_state and c._last_state.state == "completed"),
                None
            )
            if not done:
                continue
            logging.info("Detected round completion.")
            state = done._last_state

            players = getattr(state, 'players', None)
            if players:
                logging.info("--- Player Stats ---")
                for p in players:
                    logging.info(f"Hand: {p.get('hand')}  Money: {p.get('money')}")

            results = getattr(state, 'results', None)
            if results:
                logging.info("--- Round Results ---")
                logging.info(f"Goal suit: {results.get('goal_suit')}")
                logging.info(f"Counts: {results.get('counts')}")
                logging.info(f"Bonuses: {results.get('bonuses')}")
                logging.info(f"Winners: {results.get('winners')}")
                logging.info(f"Payout each: {results.get('share_each')}")
            break
    except KeyboardInterrupt:
        pass
    finally:
        logging.info("Shutting down agents...")
        for c in clients:
            try:
                c.stop()
            except Exception:
                logging.exception("Error stopping agent")


if __name__ == '__main__':
    main()
