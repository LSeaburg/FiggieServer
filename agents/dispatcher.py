import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import importlib
import time
import logging
from typing import List, Tuple, Dict, Any

from agents.figgie_interface import FiggieInterface
import figgie_server.db as db

def make_agent(
    agent_config: Tuple[str, str, Dict[str, Any]],
    name: str,
    server_url: str,
    default_polling_rate: float
) -> FiggieInterface:
    """
    Dynamically import and instantiate an agent with extra kwargs.
    agent_config: (module_name, attribute_name, extra_kwargs)
    """
    module_name, attr_name, extra_kwargs = agent_config

    module = importlib.import_module(f"agents.traders.{module_name}")
    factory = getattr(module, attr_name)

    pr = extra_kwargs.pop("polling_rate", default_polling_rate)

    # Base init kwargs
    init_kwargs = {
        "server_url": server_url,
        "name": name,
        "polling_rate": pr,
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

    raise ValueError(f"Cannot instantiate agent from entry {agent_config}")


def run_game(
    agents: List[Tuple[str, str, Dict[str, Any]]],
    server_url: str,
    experiment_id: int = 0, 
    polling_rate: float = 0.25,
) -> None:
    logging.basicConfig(level=logging.INFO)

    num_players = len(agents)
    if num_players not in {4, 5}:
        raise RuntimeError(f"Number of players must be 4 or 5.")

    logging.info(f"Spawning {num_players} agents...")
    clients = []

    for idx, agent_config in enumerate(agents):
        module_name, attr_name, extra_kwargs = agent_config
        player_name = f"{attr_name}{idx}"
        logging.info(f"Starting agent {player_name} ({module_name}.{attr_name})")
        client = make_agent(agent_config, player_name, server_url, polling_rate)
        # Log agent registration
        db.log_agent(client.player_id, module_name, attr_name, extra_kwargs, client.polling_rate, experiment_id)
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
