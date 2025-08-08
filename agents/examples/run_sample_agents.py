from typing import List
from agents.dispatcher import AgentConfig, run_game

EXPERIMENT_ID = 0

FOUR_PLAYER_SERVER = "http://localhost:5050"
FIVE_PLAYER_SERVER = "http://localhost:5051"

# Configuration using AgentConfig dataclass
# module_name is the Python module (without .py) in the traders folder.
# attribute_name is the class name (subclass of FiggieInterface) or factory function name.
# extra_kwargs is a dict of additional parameters for that agent (empty if none).
AGENTS: List[AgentConfig] = [
    AgentConfig("fundamentalist", "Fundamentalist", 1.0, {"aggression": 0.5, "buy_ratio": 1.2}),
    AgentConfig("noise_trader", "NoiseTrader", 1.0, {"aggression": 0.6, "default_val": 5}),
    AgentConfig("noise_trader", "NoiseTrader", 1.0, {"aggression": 0.6, "default_val": 7}),
    AgentConfig("noise_trader", "NoiseTrader", 1.0, {"aggression": 0.6, "default_val": 9}),
    AgentConfig("noise_trader", "NoiseTrader", 1.0, {"aggression": 0.6, "default_val": 11}),
]

if __name__ == '__main__':
    if len(AGENTS) == 4:
        SERVER_URL = FOUR_PLAYER_SERVER
    elif len(AGENTS) == 5:
        SERVER_URL = FIVE_PLAYER_SERVER
    else:
        raise ValueError(f"Expected 4 or 5 agents, got {len(AGENTS)}")

    run_game(AGENTS, SERVER_URL, EXPERIMENT_ID)
