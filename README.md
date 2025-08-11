# Figgie Agent Platform

This project makes it easy to create, run, and evaluate custom agents for the card game **Figgie**. It includes:

1. A Python Flask application serving the Figgie API
2. A PostgreSQL database for event logging and analytics
3. A dashboard for tracking performance
4. A modular interface + dispatcher for agent development

Official Figgie implementation: https://www.figgie.com

---

## Table of Contents

- [Requirements](#requirements)
- [Getting Started](#getting-started)
- [Using the Dashboard](#using-the-dashboard)
- [Configuration](#configuration)
- [Running & Testing](#running--testing)
- [Other Documentation](#other-documentation)
- [Creating Your Agent](#creating-your-agent)
- [Roadmap](#roadmap)

---

## Requirements

- Python 3.13
- Docker Desktop 27.5+
- Docker Compose (bundled with Docker Desktop)

---

## Getting Started

### For Users

1. Clone the repo
   ```shell
   git clone git@github.com:LSeaburg/FiggieServer.git
   cd FiggieServer
   ```

2. Build and start servers, DB, and dashboard
   ```shell
   docker compose up --build
   ```
   Add `-d` to start in the background

3. Go to `http://localhost:8050` to view the dashboard


### For developers

1. Clone the repo
   ```shell
   git clone git@github.com:LSeaburg/FiggieServer.git
   cd FiggieServer
   ```

2. (Optional) Create and activate a virtual environment
   ```shell
   python -m venv .venv && source .venv/bin/activate
   ```

3. Install Python dependencies
   ```shell
   pip install -r requirements-dev.txt
   ```

4. Build and start servers, DB, and dashboard
   ```shell
   docker compose up --build
   ```
   Add `-d` to start in the background

5. Configure and run games manually by editing `agents/examples/run_sample_agents.py`. Execute
   ```shell
   python agents/examples/run_sample_agents.py
   ```
   to simulate a game.

6. Follow the examples inside 'agents/traders/' and make your own agent profile.
   Add an entry to  `agents/traders.yaml` so it appears in the dashboard.

---

## Using the Dashboard

The dashboard is based around the idea of experiments - a set of agents to repeatedly play against each other.

4 or 5 players can be configured to play against each other.  
If they play against each other multiple times their average profits will be tracked and compared.

---

## Configuration

Environment variables can be set in your shell or by editing `docker-compose.yml`:

```yaml
services:
  server:
    environment:
      - TRADING_DURATION=240 # in seconds (default: 240)
```

Default ports:
- 4 Player Server → 5050
- 5 Player Server → 5051
- Database → 5432
- Dashboard → 8050

---

## Running & Testing

### Coverage report
```shell
python -m coverage run -m pytest
python -m coverage report -m
python -m coverage html
```

### Tear Down

```shell
docker compose down -v
```

---

## Other Documentation

See [figgie_server/README.md](figgie_server/README.md) for full API spec and server internals.

See [dasshboard/README.md](dasshboard/README.md) for full specs and dashboard internals.

---

## Creating Your Agent

Examples: `agents/noise_trader.py`, `agents/fundamentalist.py`. Both follow the design in [this paper](https://arxiv.org/pdf/2110.00879).

### FiggieInterface

`agents/figgie_interface.py` exposes minimal hooks and actions so you can swap in different server implementations.

### Agent Capabilities
**Actions**:
- `interface.bid(price: int, suit: str)`: Place a buy order.
- `interface.offer(price: int, suit: str)`: Place a sell order.
- `interface.buy(suit: str)`: Instantly buy one unit at the current best ask.
- `interface.sell(suit: str)`: Instantly sell one unit at the current best bid.
- `interface.cancel_bids_and_offers(suit: str)`: Cancel all your orders for a given suit.

**Event hooks**:
- `on_start(hand: Dict[str, Any], opponent_ids: Set[str])`: Fired once when trading begins, with your initial hand and polling ids.
- `on_tick(remaining_time: int)`: Fired every polling cycle with remaining time (seconds).
- `on_bid(player_id: str, price: int, suit: str)`: Fired on new highest bids by any player.
- `on_offer(player_id: str, price: int, suit: str)`: Fired on new lowest asks by any player.
- `on_cancel(order_type: str, old_pid: str, old_price: int, new_pid: Optional[str], new_price: Optional[int], suit: str)`: Fired when orders are canceled or outbid.
- `on_transaction(buyer_id: str, seller_id: str, price: int, suit: str)`: Fired on each completed trade.

**Attributes**:
- `player_id`: ID of the agent.

### Dispatcher

Configure your agents in `agents/dispatcher.py` by editing the `AGENTS` list:

```python
AGENTS = [
    ("noise_trader.py", "NoiseTrader", {"aggression": 0.5}),
    ("fundamentalist.py", "Fundamentalist", {"buy_ratio": 1.2}),
]
```

Run them:

```shell
python agents/dispatcher.py
```

Results are logged to PostgreSQL for later analysis or to view in the dashboard (once available).

---

## Roadmap

### Planned

- Fundamentalist agent incorporating inference based on opponent bids
- Additional agents based on documented strategies
- Reinforcement-learning for building agents
- Better dashboard insights

### Backlog

- WebSocket server support
- Multiple rooms with per-room config
- Persistent rooms (cumulative balances)
- GUI for live game visualization
