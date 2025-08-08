import importlib
import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any

from agents.figgie_interface import FiggieInterface
import figgie_server.db as db
import requests

@dataclass
class AgentConfig:
    module_name: str
    attribute_name: str
    polling_rate: float = 1.0
    extra_kwargs: Dict[str, Any] = field(default_factory=dict)

def make_agent(
    agent_config: AgentConfig,
    name: str,
    server_url: str,
    trading_duration: int,
) -> FiggieInterface:
    """
    Dynamically import and instantiate an agent with extra kwargs.
    agent_config holds: module_name, attribute_name, polling_rate, extra_kwargs
    """
    module_name = agent_config.module_name
    attr_name = agent_config.attribute_name
    effective_polling_rate = agent_config.polling_rate
    extra_kwargs = agent_config.extra_kwargs

    true_polling_rate = effective_polling_rate * trading_duration / 240

    module = importlib.import_module(f"agents.traders.{module_name}")
    factory = getattr(module, attr_name)

    # Base init kwargs
    init_kwargs = {
        "name": name,
        "server_url": server_url,
        "polling_rate": true_polling_rate,
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
            return factory(name, server_url, true_polling_rate)

    raise ValueError(f"Cannot instantiate agent from entry {agent_config}")


def run_game(
    agents: List[AgentConfig],
    server_url: str,
    experiment_id: int = 0,
) -> None:
    logging.basicConfig(level=logging.INFO)

    num_players = len(agents)
    if num_players not in {4, 5}:
        raise RuntimeError(f"Number of players must be 4 or 5.")

    # Pre-flight: check server status and queue
    try:
        status_resp = requests.get(f"{server_url}/status", timeout=5)
        status_resp.raise_for_status()
        status_data = status_resp.json()
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch server status from {server_url}/status: {exc}")

    server_state = status_data.get("state")
    current_players = int(status_data.get("current_players"))
    trading_duration = int(status_data.get("trading_duration"))

    if server_state == "trading":
        raise RuntimeError("Server is busy: current status is 'trading'.")

    if server_state == "waiting" and current_players != 0:
        raise RuntimeError("Players already queued: server is in 'waiting' with non-empty queue.")

    logging.info(f"Spawning {num_players} agents...")
    clients = []

    for idx, agent_config in enumerate(agents):
        module_name = agent_config.module_name
        attr_name = agent_config.attribute_name
        extra_kwargs = agent_config.extra_kwargs
        player_name = f"{attr_name}{idx}"
        logging.info(f"Starting agent {player_name} ({module_name}.{attr_name})")
        client = make_agent(agent_config, player_name, server_url, trading_duration)
        # Log agent registration
        db.log_agent(
            client.player_id,
            module_name,
            attr_name,
            extra_kwargs,
            client.polling_rate,
            experiment_id,
        )
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
